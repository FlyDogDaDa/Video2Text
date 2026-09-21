#!/usr/bin/env python3
"""步驟 6：從 composite.mkv 切出所有肯定詞片段（重編碼、幀精確）。

用法（在專案根目錄執行）：
    uv run exp/N9boWvU-KkA/scripts/edit_video.py --dry-run
    uv run exp/N9boWvU-KkA/scripts/edit_video.py --limit 2
    uv run exp/N9boWvU-KkA/scripts/edit_video.py
    uv run exp/N9boWvU-KkA/scripts/edit_video.py --verify

    # AV1 + MP4 版（輸出 clips_mp4/ + clips_mp4_manifest.json）
    uv run exp/N9boWvU-KkA/scripts/edit_video.py --encoder av1_nvenc --outdir clips_mp4
    uv run exp/N9boWvU-KkA/scripts/edit_video.py --encoder av1_nvenc --outdir clips_mp4 --verify
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

# ── 路徑 ─────────────────────────────────────────────────────────────────────
EXP_DIR = Path(__file__).resolve().parent.parent  # exp/N9boWvU-KkA
SOURCE = EXP_DIR / "download" / "N9boWvU-KkA_composite.mkv"
ALIGNED = EXP_DIR / "filtered_aligned.json"
OUT_DIR = EXP_DIR / "clips"
MANIFEST = EXP_DIR / "clips_manifest.json"

# ── 切片策略引數 ────────────────────────────────────────────────────────────
MERGE_GAP_S = 0.05  # 同段落內兩詞間距 ≤ 此值 → 合併為同一 clip
MIN_CLIP_DUR_S = 0.30  # 最短片長；不足時向 end 延伸
MAX_RAW_SPAN_S = 0.60  # 零長 raw 視窗可用上限（超過視為異常）
T_PAD_S = 0.20  # zero-length fallback：T ± 0.2s

# ── 編碼引數 ─────────────────────────────────────────────────────────────────
CRF = 18
PRESET = "fast"
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

# 每種 encoder 對應的 ffmpeg 引數、副檔名與 manifest 標籤
ENCODERS: dict[str, dict] = {
    "x264": {
        "vcodec": "libx264",
        "vargs": ["-crf", str(CRF), "-preset", PRESET],
        "ext": "mkv",
        "label": f"libx264 crf{CRF} preset={PRESET}",
    },
    "av1_nvenc": {
        # CQ 恆品質（-b:v 0 + -cq），語義對齊 crf；p5 為速度/品質平衡
        "vcodec": "av1_nvenc",
        "vargs": ["-preset", "p5", "-rc", "vbr", "-cq", "24", "-b:v", "0"],
        "ext": "mp4",
        "label": "av1_nvenc p5 vbr cq24",
    },
    "svt_av1": {
        # CPU AV1（libsvtav1）：NVENC 視訊記憶體不可用時的替代，容器同 mp4
        # preset 5 速度/品質平衡；crf 24 對齊 av1_nvenc 的 cq 24
        "vcodec": "libsvtav1",
        "vargs": ["-preset", "5", "-crf", "24", "-b:v", "0"],
        "ext": "mp4",
        "label": "libsvtav1 preset5 crf24",
    },
    "av1_mkv": {
        # 同 svt_av1 引數，但容器改 MKV：實測 DaVinci Resolve 讀得到
        # （MP4+AV1 會黑幀）
        "vcodec": "libsvtav1",
        "vargs": ["-preset", "5", "-crf", "24", "-b:v", "0"],
        "ext": "mkv",
        "label": "libsvtav1 preset5 crf24 (mkv)",
    },
}

# ── 平行化 ──────────────────────────────────────────────────────────────────
MAX_WORKERS = 18

# ── 驗證 ────────────────────────────────────────────────────────────────────
DUR_TOL_S = 0.15  # 驗證時長容差（秒）


# ────────────────────────────────────────────────────────────────────────────
# 工具函式
# ────────────────────────────────────────────────────────────────────────────


def fmt_tc(t: float) -> str:
    """HH:MM:SS.mmm"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000:
        ms -= 1000
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def resolve_window(match: dict) -> tuple[float, float, str]:
    """回傳 (start, end, source_label)；處理零長 / raw / fallback。"""
    s = match.get("start_s")
    e = match.get("end_s")
    if s is None or e is None:
        # 無有效時間 → 跳過（呼叫端會略過）
        return (float("nan"), float("nan"), "invalid")

    if e - s > 0:
        return (s, e, "fixed")

    # 零長：嘗試 raw
    rs = match.get("start_s_raw")
    re_ = match.get("end_s_raw")
    if rs is not None and re_ is not None:
        raw_dur = re_ - rs
        if 0 < raw_dur <= MAX_RAW_SPAN_S:
            return (rs, re_, "raw_window")
        # raw 反轉或異常
    # fallback: T ± 0.2s
    t = s
    return (t - T_PAD_S, t + T_PAD_S, "t_pad")


# ────────────────────────────────────────────────────────────────────────────
# 建立 clip plan
# ────────────────────────────────────────────────────────────────────────────


def build_clips(data: dict, outdir: str = "clips", ext: str = "mkv") -> list[dict]:
    """從 filtered_aligned.json 建立全量 clip 清單（絕對時間、已排序）。"""
    clips: list[dict] = []

    for seg in data["segments"]:
        if not seg.get("ok", True):
            continue

        matches = seg.get("word_matches", [])
        # 只取 valid 樣本（防守性檢查）
        matches = [m for m in matches if m.get("valid", True) is not False]
        if not matches:
            continue

        # 解析每個 match 的視窗
        windows: list[tuple[float, float, str, str]] = []
        for m in matches:
            s, e, src = resolve_window(m)
            if s != s:  # NaN check
                continue
            windows.append((s, e, src, m.get("word", "?")))

        if not windows:
            continue

        # 同段落內合併：間距 ≤ MERGE_GAP_S
        merged: list[dict] = []
        for s, e, src, word in windows:
            if merged and s - merged[-1]["end_s"] <= MERGE_GAP_S:
                c = merged[-1]
                c["end_s"] = max(c["end_s"], e)
                c["words"].append(word)
                c["sources"].append(src)
            else:
                merged.append(
                    {
                        "start_s": s,
                        "end_s": e,
                        "words": [word],
                        "sources": [src],
                    }
                )

        for c in merged:
            c["seg_id"] = seg["seg_id"]
            c["part"] = seg.get("part", 0)

        clips.extend(merged)

    # 依絕對時間排序
    clips.sort(key=lambda c: c["start_s"])

    # 跨 segment 去重：間距 ≤ MERGE_GAP_S 的相鄰 clip 合併
    # （處理段邊界同一個「對」被兩個 segment 都記錄的情況）
    i = 0
    while i < len(clips) - 1:
        if clips[i + 1]["start_s"] - clips[i]["end_s"] <= MERGE_GAP_S:
            clips[i]["end_s"] = max(clips[i]["end_s"], clips[i + 1]["end_s"])
            clips[i]["words"].extend(clips[i + 1]["words"])
            clips[i]["sources"].extend(clips[i + 1]["sources"])
            del clips[i + 1]
        else:
            i += 1

    # 最小時長保護 + 全域碰撞上限
    source_dur = data["meta"].get("total_duration_s", 5667.0)
    for i, c in enumerate(clips):
        dur = c["end_s"] - c["start_s"]
        if dur < MIN_CLIP_DUR_S:
            c["end_s"] = c["start_s"] + MIN_CLIP_DUR_S
        # 不超過影片總長
        c["end_s"] = min(c["end_s"], source_dur - 0.033)
        # 不侵入下一個 clip
        if i + 1 < len(clips):
            cap = clips[i + 1]["start_s"] - 0.01
            if c["end_s"] > cap:
                c["end_s"] = cap

    # 編號
    for idx, c in enumerate(clips, 1):
        c["index"] = idx
        c["file"] = f"{outdir}/clip_{idx:04d}.{ext}"
        c["duration_s"] = round(c["end_s"] - c["start_s"], 4)
        c["timecode"] = fmt_tc(c["start_s"])

    return clips


# ────────────────────────────────────────────────────────────────────────────
# 切片
# ────────────────────────────────────────────────────────────────────────────


def _ffmpeg_cmd(start: float, dur: float, out_path: Path, encoder: str) -> list[str]:
    enc = ENCODERS[encoder]
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(SOURCE),
        "-t",
        f"{dur:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        enc["vcodec"],
        *enc["vargs"],
        "-threads",
        "2",
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        AUDIO_BITRATE,
        "-avoid_negative_ts",
        "make_zero",
        "-y",
        str(out_path),
    ]


def cut_one(job: dict) -> dict:
    """worker：切一個 clip（含重試，應付 NVENC CUDA context 瞬間資源不足）。"""
    out_path = EXP_DIR / job["file"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = _ffmpeg_cmd(job["start_s"], job["duration_s"], out_path, job["encoder"])
    retries = job.get("retries", 1)
    last_err = ""
    for attempt in range(retries):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                return {"index": job["index"], "ok": True, "err": ""}
            last_err = (r.stderr or r.stdout or f"rc={r.returncode}")[:500]
        except subprocess.TimeoutExpired:
            last_err = "timeout 300s"
        except Exception as ex:
            last_err = str(ex)[:500]
        if attempt + 1 < retries:
            time.sleep(2.0 * (attempt + 1))
    return {"index": job["index"], "ok": False, "err": last_err}


def run_cuts(clips: list[dict], limit: int | None, workers: int) -> list[dict]:
    """執行切片，回傳結果列表。"""
    jobs = clips[:limit] if limit else clips
    print(f"切片 {len(jobs)} / {len(clips)}（workers={workers}）…")
    t0 = time.time()

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(cut_one, j): j for j in jobs}
        done = 0
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}")

    elapsed = time.time() - t0
    ok = sum(1 for r in results if r["ok"])
    print(
        f"完成：{ok}/{len(results)} 成功，{len(results) - ok} 失敗，耗時 {elapsed:.1f}s"
    )
    if len(results) - ok:
        print("失敗清單：")
        for r in results:
            if not r["ok"]:
                print(f"  #{r['index']}: {r['err'][:120]}")
    return results


def run_verify(manifest: dict) -> None:
    """驗證所有 clip 存在且時長正確。"""
    clips = manifest["clips"]
    print(f"驗證 {len(clips)} 個 clip …")
    bad = 0
    for c in clips:
        p = EXP_DIR / c["file"]
        if not p.exists() or p.stat().st_size == 0:
            print(f"  MISSING: {c['file']}")
            bad += 1
            continue
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(p),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            print(f"  PROBE FAIL: {c['file']}")
            bad += 1
            continue
        dur = float(r.stdout.strip())
        expected = c["duration_s"]
        if abs(dur - expected) > DUR_TOL_S:
            print(
                f"  DUR MISMATCH: {c['file']} expected {expected:.3f}s got {dur:.3f}s"
            )
            bad += 1
    if bad:
        print(f"驗證失敗：{bad}/{len(clips)}")
    else:
        print(f"驗證通過：{len(clips)}/{len(clips)} 全部 OK")


# ────────────────────────────────────────────────────────────────────────────
# dry-run
# ────────────────────────────────────────────────────────────────────────────


def dry_run(clips: list[dict], data: dict, encoder: str, outdir: str) -> None:
    """印出 plan 統計，不切任何檔案。"""
    n = len(clips)
    total_dur = sum(c["duration_s"] for c in clips)
    durs = [c["duration_s"] for c in clips]
    durs_sorted = sorted(durs)
    median = durs_sorted[n // 2] if n else 0

    # 零長處理分佈
    src_counts: dict[str, int] = {}
    for c in clips:
        for s in c["sources"]:
            src_counts[s] = src_counts.get(s, 0) + 1

    # 詞分佈
    word_counts: dict[str, int] = {}
    for c in clips:
        for w in c["words"]:
            word_counts[w] = word_counts.get(w, 0) + 1

    print("═══ DRY-RUN 統計 ═══")
    print(f"影片總長：{data['meta'].get('total_duration_s', '?')}s")
    print(f"段落數：{len(data['segments'])}")
    print(f"Clip 總數：{n}")
    print(f"總影片秒數：{total_dur:.1f}s")
    print(
        f"單片時長：min {durs_sorted[0]:.3f}s / median {median:.3f}s / max {durs_sorted[-1]:.3f}s"
    )
    print(f"視窗來源分佈：{src_counts}")
    print(f"詞彙分佈：{word_counts}")
    ext = ENCODERS[encoder]["ext"]
    print(f"編號範圍：{outdir}/clip_0001.{ext} … {outdir}/clip_{n:04d}.{ext}")
    print(f"編碼：{ENCODERS[encoder]['label']} / {AUDIO_CODEC} {AUDIO_BITRATE}")
    print(f"平行：ProcessPoolExecutor max_workers={MAX_WORKERS}")
    print("══════════════════════")


# ────────────────────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description="步驟 6 切片")
    ap.add_argument("--dry-run", action="store_true", help="只印 plan，不切片")
    ap.add_argument("--limit", type=int, default=None, help="只切前 N 個（目檢用）")
    ap.add_argument("--verify", action="store_true", help="驗證已有 manifest 的 clips")
    ap.add_argument(
        "--encoder", choices=sorted(ENCODERS), default="x264", help="影片編碼器"
    )
    ap.add_argument(
        "--outdir", default="clips", help="輸出資料夾（EXP_DIR 下相對路徑）"
    )
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help="並行程式數上限")
    ap.add_argument("--retries", type=int, default=1, help="每個 clip 的最大嘗試次數")
    args = ap.parse_args()

    ext = ENCODERS[args.encoder]["ext"]
    # 預設 outdir 沿用原 manifest 檔名；其他 outdir 用 {outdir}_manifest.json
    manifest_path = (
        MANIFEST if args.outdir == "clips" else EXP_DIR / f"{args.outdir}_manifest.json"
    )

    if args.verify:
        if not manifest_path.exists():
            print(f"找不到 {manifest_path}，先跑切片。")
            sys.exit(1)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_verify(manifest)
        return

    # 讀 aligned data
    if not ALIGNED.exists():
        print(f"找不到 {ALIGNED}")
        sys.exit(1)
    data = json.loads(ALIGNED.read_text(encoding="utf-8"))
    clips = build_clips(data, args.outdir, ext)
    for c in clips:
        c["encoder"] = args.encoder
        c["retries"] = args.retries

    if not clips:
        print("無任何 clip 可切。")
        sys.exit(0)

    if args.dry_run:
        dry_run(clips, data, args.encoder, args.outdir)
        return

    # 切片
    results = run_cuts(clips, args.limit, args.workers)

    # 寫 manifest
    ok_indices = {r["index"] for r in results if r["ok"]}
    manifest_clips = []
    for c in clips:
        if c["index"] not in ok_indices:
            continue
        manifest_clips.append(
            {
                "index": c["index"],
                "file": c["file"],
                "start_s": round(c["start_s"], 3),
                "end_s": round(c["end_s"], 3),
                "duration_s": c["duration_s"],
                "timecode": c["timecode"],
                "seg_id": c["seg_id"],
                "part": c["part"],
                "words": c["words"],
                "window_sources": c["sources"],
            }
        )

    manifest = {
        "video_id": data["meta"]["video_id"],
        "source": "download/N9boWvU-KkA_composite.mkv",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "encoder": {
            "video": ENCODERS[args.encoder]["label"],
            "audio": f"{AUDIO_CODEC} {AUDIO_BITRATE}",
            "container": ext,
        },
        "policy": {
            "merge_gap_s": MERGE_GAP_S,
            "min_clip_dur_s": MIN_CLIP_DUR_S,
            "max_raw_span_s": MAX_RAW_SPAN_S,
            "t_pad_s": T_PAD_S,
        },
        "clip_count": len(manifest_clips),
        "clips": manifest_clips,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Manifest 已寫入：{manifest_path}（{len(manifest_clips)} clips）")

    # 自動驗證
    run_verify(manifest)


if __name__ == "__main__":
    main()
