#!/usr/bin/env python3
"""步驟 3（新版）：逐字稿驅動的迭代切分轉錄。

與舊版（exp/N9boWvU-KkA，等分 4 段盲切）的差異：
- 每段先轉錄，再從「倒數第二句」往回掃，取第一個 end <= 時長-margin 的完整句，
  以其結束點（絕對時間）作為下一段切點 → 句子永不腰斬
- 本段只保留切點前的句子；切點後殘句丟棄（下一段從切點重轉，自動補全）
- 段 N>0 的音訊從「切點 − guard」開始（多含上一段錨點句尾音，保護下段首字）；
  組裝時丟棄絕對 end <= 上一段切點的碎段
- 無輸出：接近片尾視為完成；離片尾遠 → 前進 NOMINAL 並記 warning
- 回掃無候選（尾端長獨白）→ fallback 盲切 NOMINAL，記 warning（接受腰斬）
- 可續跑：audio_parts.json / transcript_part_N.json 已存在者跳過

僅用標準庫 + httpx；音訊切分用 wave 模組直接切 PCM（樣本精確）。
"""

from __future__ import annotations

import array
import json
import os
import re
import sys
import time
import wave
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
ASR_URL = os.environ.get(
    "EK7_ASR_URL", "http://10.46.219.5:8750/v1/audio/transcriptions"
)
MODEL_ID = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
AUDIO_FULL = BASE / "audio_full.wav"

SR = 16000
NOMINAL_S = 1440.0  # 單次 ASR 穩定上限（暫定 24min）
MARGIN_S = 2.0  # 錨點句 end 距音訊尾的安全距離
GUARD_S = 0.3  # 下一段音訊提早開始量
HEAD_TOL_S = 0.05  # 段頭碎段判定容差（時間戳抖動）
DONE_EPS = 1.0  # 切點距總長小於此視為到底

TIMEOUT_S = 1800.0  # 舊實驗 ~24min 音訊約 2.5min，給足餘裕
RETRY = 2  # 每段最多 3 次嘗試

# MOSS canonical 輸出：[start][Sxx]text[end]
SEGMENT_RE = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]",
    re.DOTALL,
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_full() -> array.array:
    with wave.open(str(AUDIO_FULL), "rb") as w:
        assert (
            w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
        ), f"{AUDIO_FULL.name}: 預期 16k/s16le/mono"
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
        return a


def write_part(path: Path, samples: array.array) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(samples.tobytes())


def parse_segments(text: str) -> list[dict]:
    return [
        {"start": float(a), "end": float(b), "speaker": spk, "text": body.strip()}
        for a, spk, body, b in SEGMENT_RE.findall(text)
    ]


def transcribe(part_file: Path) -> tuple[str, dict | None, float]:
    last_err: Exception | None = None
    for attempt in range(1, RETRY + 2):
        t0 = time.time()
        try:
            data = {"model": MODEL_ID, "response_format": "json"}
            with open(part_file, "rb") as f:
                resp = httpx.post(
                    ASR_URL,
                    data=data,
                    files={"file": (part_file.name, f, "audio/wav")},
                    timeout=TIMEOUT_S,
                )
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            body = resp.json()
            return body.get("text", ""), body.get("usage"), time.time() - t0
        except Exception as e:  # noqa: BLE001
            last_err = e
            log(f"  attempt #{attempt} 失敗：{e}")
            if attempt <= RETRY:
                time.sleep(15)
    raise RuntimeError(f"重試 {RETRY} 次後仍失敗：{last_err}")


def save_state(meta: dict, parts: list[dict]) -> None:
    (BASE / "audio_parts.json").write_text(
        json.dumps({**meta, "parts": parts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_part(rec: dict) -> None:
    (BASE / f"transcript_part_{rec['part']}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def assemble(meta: dict, parts: list[dict]) -> None:
    combined_segments: list[dict] = []
    for p in parts:
        for s in p.get("kept_segments", []):
            combined_segments.append(
                {
                    "start": round(p["start_abs_s"] + s["start"], 3),
                    "end": round(p["start_abs_s"] + s["end"], 3),
                    "speaker": s["speaker"],
                    "text": s["text"],
                    "part": p["part"],
                }
            )
    combined_segments.sort(key=lambda s: s["start"])
    combined = {
        "video_id": "Ek7qDwwXZ6A",
        "source": "download/Ek7qDwwXZ6A_composite.mkv",
        "total_duration_s": meta["total_duration_s"],
        "note": (
            "start/end 為影片絕對時間（秒）；text 為模型原始簡體輸出（尚未轉繁體）；"
            "speaker 為各 part 獨立 diarization 的原始標籤；"
            "speaker_global 由 speaker_unify.py 加入"
        ),
        "parts": [
            {
                "part": p["part"],
                "start_abs_s": p["start_abs_s"],
                "duration_s": p["duration_s"],
                "status": p["status"],
                "end_cut_abs_s": p["end_cut_abs_s"],
                "kept": len(p.get("kept_segments", [])),
            }
            for p in parts
        ],
        "segments": combined_segments,
    }
    out = BASE / "transcript_combined.json"
    out.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"組裝完成：共 {len(combined_segments)} segments → {out.name}")


def main() -> int:
    full = load_full()
    total_s = len(full) / SR
    log(f"audio_full: {len(full)} samples = {total_s:.6f}s")

    parts_meta_path = BASE / "audio_parts.json"
    if parts_meta_path.exists():
        meta = json.loads(parts_meta_path.read_text(encoding="utf-8"))
        parts: list[dict] = meta["parts"]
        if parts and str(parts[-1].get("status", "")).startswith("final"):
            log("所有段已完成（續跑模式）→ 直接重新組裝")
            assemble(meta, parts)
            return 0
        cut = float(parts[-1]["end_cut_abs_s"]) if parts else 0.0
        log(f"續跑模式：從切點 {cut:.3f}s 繼續")
    else:
        parts = []
        cut = 0.0
        meta = {
            "video_id": "Ek7qDwwXZ6A",
            "source": "download/Ek7qDwwXZ6A_composite.mkv",
            "audio_full": AUDIO_FULL.name,
            "format": "PCM s16le 16kHz mono",
            "total_duration_s": round(total_s, 6),
            "nominal_part_s": NOMINAL_S,
            "margin_s": MARGIN_S,
            "guard_s": GUARD_S,
            "cut_policy": (
                "transcript-driven iterative：每段轉錄後從倒數第二句往回掃，"
                "取第一個 end<=時長-margin 的完整句，其結束點為下一段切點；"
                "段 N>0 音訊從切點-guard 開始"
            ),
        }

    part_idx = len(parts)
    while cut < total_s - DONE_EPS:
        start_abs = max(0.0, cut - (GUARD_S if part_idx > 0 else 0.0))
        nominal_end = min(cut + NOMINAL_S, total_s)
        part_dur = nominal_end - start_abs
        is_final = nominal_end >= total_s - DONE_EPS
        part_file = BASE / f"audio_part_{part_idx}.wav"
        part_json = BASE / f"transcript_part_{part_idx}.json"

        if part_json.exists():
            prev = json.loads(part_json.read_text(encoding="utf-8"))
            parts.append(prev)
            cut = float(prev["end_cut_abs_s"])
            part_idx += 1
            log(f"[part {part_idx - 1}] 已存在 → 跳過（cut={cut:.3f}s）")
            continue

        write_part(
            part_file, full[int(round(start_abs * SR)) : int(round(nominal_end * SR))]
        )
        log(
            f"[part {part_idx}] 送轉錄（{part_file.name}, {part_dur:.1f}s, "
            f"abs {start_abs:.3f}~{nominal_end:.3f}s）…"
        )
        try:
            raw, usage, elapsed = transcribe(part_file)
        except Exception as e:  # noqa: BLE001
            log(f"[part {part_idx}] 停止等使用者裁決：{e}")
            save_state(meta, parts)
            return 1

        segments = parse_segments(raw)
        for s in segments:
            if s["end"] > part_dur + 5.0 or s["start"] < -5.0:
                log(f"[part {part_idx}] ⚠ segment 時間出界：{s}")

        record: dict = {
            "part": part_idx,
            "file": part_file.name,
            "start_abs_s": round(start_abs, 6),
            "duration_s": round(part_dur, 6),
            "elapsed_s": round(elapsed, 1),
            "usage": usage,
            "raw": raw,
            "segments": segments,  # 全部解析結果（part 相對時間）
            "kept_segments": [],
        }

        def advance(status: str, extra: dict | None = None) -> None:
            record.update(status=status, end_cut_abs_s=round(nominal_end, 6))
            if extra:
                record.update(extra)
            parts.append(record)
            save_part(record)
            save_state(meta, parts)

        if not segments:
            if is_final:
                record.update(status="final-empty", end_cut_abs_s=round(nominal_end, 6))
                parts.append(record)
                log(f"[part {part_idx}] 無輸出且已達片尾 → 完成")
                break
            log(
                f"[part {part_idx}] ⚠ 無輸出但離片尾尚遠"
                f"（切點 {cut:.1f}／總長 {total_s:.1f}）→ 前進 NOMINAL 繼續"
            )
            advance("empty-advance")
            cut = nominal_end
            part_idx += 1
            continue

        segments.sort(key=lambda s: s["start"])
        # 段 N>0：丟棄 guard 多含的上一段內容（絕對 end <= 起始切點 + 容差）
        if part_idx > 0:
            kept = [s for s in segments if start_abs + s["end"] > cut + HEAD_TOL_S]
        else:
            kept = segments
        n_dropped_head = len(segments) - len(kept)
        if n_dropped_head:
            log(f"[part {part_idx}] 丟棄段頭碎段 ×{n_dropped_head}（guard 重疊區）")

        if not kept:
            log(f"[part {part_idx}] ⚠ 全為段頭碎段、無新內容 → 前進 NOMINAL 繼續")
            advance("empty-advance", {"n_dropped_head": n_dropped_head})
            cut = nominal_end
            part_idx += 1
            continue

        anchor = None
        if not is_final:
            # 從倒數第二句往回掃（最後一句可能是被截斷的殘句，不用）
            for s in reversed(kept[:-1]):
                if s["end"] <= part_dur - MARGIN_S:
                    anchor = s
                    break

        if anchor is not None:
            cut_abs_new = start_abs + anchor["end"]
            final_kept = [s for s in kept if start_abs + s["end"] <= cut_abs_new + 1e-6]
            n_dropped_tail = len(kept) - len(final_kept)
            status = "ok"
            log(
                f"[part {part_idx}] 切點 = 錨點句尾 {cut_abs_new:.3f}s"
                f"（尾句「{anchor['text'][:20]}…」；丟棄尾端 ×{n_dropped_tail}）"
            )
        else:
            cut_abs_new = nominal_end
            final_kept = kept
            n_dropped_tail = 0
            status = "final" if is_final else "fallback-blind-cut"
            if is_final:
                log(f"[part {part_idx}] 已達片尾 → 完成")
            else:
                log(
                    f"[part {part_idx}] ⚠ 回掃無候選句 → fallback 盲切 "
                    f"{cut_abs_new:.3f}s（接受可能腰斬）"
                )

        record.update(
            status=status,
            end_cut_abs_s=round(cut_abs_new, 6),
            kept_segments=final_kept,
            n_dropped_head=n_dropped_head,
            n_dropped_tail=n_dropped_tail,
            cut_sentence=(
                {"text": anchor["text"], "end_rel": anchor["end"]} if anchor else None
            ),
        )
        parts.append(record)
        save_part(record)
        save_state(meta, parts)
        log(
            f"[part {part_idx}] 完成：解析 {len(segments)}、保留 {len(final_kept)}"
            f"（頭丟 {n_dropped_head}、尾丟 {n_dropped_tail}），耗時 {elapsed:.1f}s"
        )
        cut = cut_abs_new
        part_idx += 1

    save_state(meta, parts)
    assemble(meta, parts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
