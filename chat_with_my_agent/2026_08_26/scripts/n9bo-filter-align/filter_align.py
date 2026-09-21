#!/usr/bin/env python3
"""步驟 5：肯定詞過濾 + Qwen3-ForcedAligner-0.6B 精準時間對齊（batch=4 執行緒池）。

輸入:
- transcript_combined.json  （963 段，影片絕對時間，繁體 text）
- audio_parts.json          （4 份音訊之 offset/時長元數據）
- audio_part_0..3.wav       （16kHz mono PCM，用於轉錄的音訊）

輸出:
- filtered_aligned.json     （只含肯定詞段落 + 逐字精準時間戳 + 詞樣本時間）
- tmp/align_results/pN_sM.json  逐段檢查點（可重跑跳過已完成）
- tmp/align_failures/pN_sM.json 失敗記錄

肯定詞過濾（使用者 2026-08-26 定案三詞表：對 / 沒錯 / 確實）：
- 「對」排除複合詞：前置 不相互絕反派配視針（如 不對/相對/針對），
  後置 於不起象應吧（如 對於/對不起/對象/對應/對吧）。
- 「沒錯」「確實」無排除。

時間對齊：沿用 scripts/test_fa.py 已驗證之請求/對齊邏輯（日誌 04）：
- POST /pooling（task=token_classify、chat_template raw-content）
- POST /tokenize 取伺服器端 token 序列
- 各 <timestamp> 位置 argmax(5000 bins) × 80ms → 逐字相對時間
- 絕對時間 = part offset + chunk 起點（含兩側 200ms padding）+ 相對時間

用法:
    nohup exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/filter_align.py \
      > exp/N9boWvU-KkA/filter_align.log 2>&1 &
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
TMP = BASE / "tmp"
CHUNK_DIR = TMP / "align_chunks"
RESULT_DIR = TMP / "align_results"
FAIL_DIR = TMP / "align_failures"
OUT_PATH = BASE / "filtered_aligned.json"

FA_URL = "http://10.46.219.5:8755"
MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"
PAD_S = 0.2
WORKERS = 4
HTTP_TIMEOUT = 300
MAX_ATTEMPTS = 3

# 模型參數（config.json）
TIMESTAMP_TOKEN_ID = 151705
TIMESTAMP_SEGMENT_MS = 80
CLASSIFY_NUM = 5000
AUDIO_PAD_TOKEN_ID = 151676
# 官方 forced_alignment_online.py 前綴（< 與 > 用 unicode escape 避免寫入損毀）
PROMPT_PREFIX = (
    "\u003c|audio_start|\u003e\u003c|audio_pad|\u003e\u003c|audio_end|\u003e"
)
# raw-content 模板：讓伺服器把 messages[0].content 直接當 prompt。
# 伺服器需以 --trust-request-chat-template 啟動（日誌 04 已確認）。
RAW_CONTENT_CHAT_TEMPLATE = "{{ messages[0]['content'] }}"

AFFIRM_RE = re.compile(r"(?<![不相互絕反派配視針])對(?![於不起象應吧])|沒錯|確實")


def log(msg: str) -> None:
    # stdout 會被重定向到 filter_align.log，這裡只 print（勿雙重寫檔）
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def split_text_units(text: str) -> list[str]:
    """切成對齊單位：CJK 單字各算一個單位，連續 ASCII 字母/數字併成一個單位。"""
    units: list[str] = []
    buffer: list[str] = []

    def flush_ascii() -> None:
        if buffer:
            units.append("".join(buffer))
            buffer.clear()

    for char in text:
        if "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf":
            flush_ascii()
            units.append(char)
        elif char.isascii() and char.isalnum():
            buffer.append(char)
        else:
            flush_ascii()
    flush_ascii()
    return units


def char_unit_map(text: str) -> list:
    """回傳與 text 等長之列表：CJK 字元 -> 單位索引；其他 -> None。

    單位編號規則與 split_text_units 一致（CJK 單字一個單位、
    連續 ASCII 字母數字一個單位），故可按文字位置對回單位。
    """
    count = 0
    m: list = [None] * len(text)
    in_ascii = False
    for i, ch in enumerate(text):
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            m[i] = count
            count += 1
            in_ascii = False
        elif ch.isascii() and ch.isalnum():
            if not in_ascii:
                m[i] = count
                count += 1
                in_ascii = True
        else:
            in_ascii = False
    return m


def build_prompt(words: list[str]) -> str:
    body = "<timestamp><timestamp>".join(words)
    return f"{PROMPT_PREFIX}{body}<timestamp><timestamp>"


def data_uri(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def extract_chunk(
    part_file: Path, chunk_start: float, chunk_dur: float, out_wav: Path
) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{chunk_start:.3f}",
            "-i",
            str(part_file),
            "-t",
            f"{chunk_dur:.3f}",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            str(out_wav),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def tokenize_messages(
    client: httpx.Client, messages: list[dict], base_url: str, model: str
) -> list[int]:
    """用與 /pooling 相同的 messages + chat_template 讓伺服器端 tokenize。"""
    response = client.post(
        f"{base_url}/tokenize",
        json={
            "model": model,
            "messages": messages,
            "return_token_strs": True,
            "chat_template": RAW_CONTENT_CHAT_TEMPLATE,
        },
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    tokens = data.get("tokens", data)
    if isinstance(tokens, dict):
        for key in ("input_ids", "token_ids", "ids"):
            if key in tokens:
                return [int(x) for x in tokens[key]]
    if isinstance(tokens, list):
        return [int(x) for x in tokens]
    raise ValueError(
        f"不認識的 /tokenize 回應格式: {json.dumps(data, ensure_ascii=False)[:400]}"
    )


def parse_pooling_rows(raw: list, classify_num: int) -> list[list[float]]:
    if not raw:
        raise ValueError("pooling 回應沒有 data。")
    if isinstance(raw[0], list):
        return [[float(x) for x in row] for row in raw]
    flat = [float(x) for x in raw]
    if len(flat) % classify_num != 0:
        raise ValueError(
            f"flat pooling 長度 {len(flat)} 無法被 classify_num={classify_num} 整除。"
        )
    row_count = len(flat) // classify_num
    return [flat[i * classify_num : (i + 1) * classify_num] for i in range(row_count)]


def argmax(row: list[float]) -> int:
    best_index = 0
    best_value = -float("inf")
    for index, value in enumerate(row):
        if value > best_value:
            best_value = value
            best_index = index
    return best_index


def align_once(
    client: httpx.Client, wav_bytes: bytes, text: str, base_url: str, model: str
) -> dict:
    """對一段音訊 + 文字做逐字對齊，回傳相對該音訊起點的單位時間。"""
    words = split_text_units(text)
    prompt = build_prompt(words)
    audio_uri = data_uri(wav_bytes, "audio/wav")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "audio_url", "audio_url": {"url": audio_uri}},
            ],
        }
    ]

    token_ids = tokenize_messages(client, messages, base_url, model)
    payload = {
        "model": model,
        "messages": messages,
        "task": "token_classify",
        "chat_template": RAW_CONTENT_CHAT_TEMPLATE,
    }
    start = time.monotonic()
    response = client.post(f"{base_url}/pooling", json=payload, timeout=HTTP_TIMEOUT)
    latency = time.monotonic() - start
    if response.status_code != 200:
        raise RuntimeError(
            f"/pooling 回傳 {response.status_code}: {response.text[:300]}"
        )
    data = response.json()
    if "data" not in data or not data["data"]:
        raise ValueError(
            f"pooling 回應缺 data: {json.dumps(data, ensure_ascii=False)[:300]}"
        )

    rows = parse_pooling_rows(data["data"][0]["data"], CLASSIFY_NUM)
    predictions = [argmax(row) for row in rows]
    if len(predictions) < len(token_ids):
        raise ValueError(f"predictions {len(predictions)} < tokenize {len(token_ids)}")

    audio_token_shift = len(predictions) - len(token_ids)
    audio_pad_index = (
        token_ids.index(AUDIO_PAD_TOKEN_ID) if AUDIO_PAD_TOKEN_ID in token_ids else -1
    )
    timestamps_ms: list[float] = []
    for i, token_id in enumerate(token_ids):
        if token_id != TIMESTAMP_TOKEN_ID:
            continue
        prediction_index = (
            i + audio_token_shift
            if (audio_pad_index >= 0 and i > audio_pad_index)
            else i
        )
        if prediction_index >= len(predictions):
            raise ValueError(
                f"timestamp 位置 {i} (+shift={audio_token_shift}) 超出 predictions {len(predictions)}"
            )
        timestamps_ms.append(predictions[prediction_index] * TIMESTAMP_SEGMENT_MS)

    if len(timestamps_ms) < len(words) * 2:
        raise ValueError(
            f"預期 {len(words) * 2} 個 timestamp 預測，實際 {len(timestamps_ms)}"
        )

    units_rel = []
    for i, w in enumerate(words):
        units_rel.append(
            {
                "unit": w,
                "start_ms": timestamps_ms[i * 2],
                "end_ms": timestamps_ms[i * 2 + 1],
            }
        )
    return {
        "units_rel": units_rel,
        "latency_s": latency,
        "token_count": len(token_ids),
        "audio_pad_index": audio_pad_index,
        "audio_token_shift": audio_token_shift,
    }


def process_segment(
    part_index: int, seg_index: int, seg: dict, part_meta: dict, part_dur_actual: dict
) -> tuple[str, str]:
    seg_id = f"p{part_index}_s{seg_index}"
    out_path = RESULT_DIR / f"{seg_id}.json"

    # 檢查點：已完成就跳過（續跑）
    if out_path.exists():
        try:
            if json.loads(out_path.read_text(encoding="utf-8")).get("ok"):
                return seg_id, "skipped"
        except json.JSONDecodeError:
            pass

    text = seg["text"]
    offset = part_meta["offset_s"]
    part_dur = part_dur_actual[part_index]
    part_file = BASE / part_meta["file"]

    rel_start = max(0.0, seg["start"] - offset)
    rel_end = min(part_dur, seg["end"] - offset)
    chunk_start = max(0.0, rel_start - PAD_S)
    chunk_end = min(part_dur, rel_end + PAD_S)
    chunk_dur = chunk_end - chunk_start
    if chunk_dur <= 0.05:
        raise RuntimeError(
            f"chunk 太短 {chunk_dur:.3f}s（rel {rel_start:.3f}-{rel_end:.3f}）"
        )

    wav_path = CHUNK_DIR / f"{seg_id}.wav"
    extract_chunk(part_file, chunk_start, chunk_dur, wav_path)
    chunk_actual_dur = ffprobe_duration(wav_path)
    wav_bytes = wav_path.read_bytes()

    alignment = None
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with httpx.Client() as client:
                alignment = align_once(client, wav_bytes, text, FA_URL, MODEL)
            break
        except Exception as e:  # noqa: BLE001 - 記錄後重試
            last_err = e
            log(f"{seg_id} 第 {attempt}/{MAX_ATTEMPTS} 次對齊失敗: {e}")
            time.sleep(3 * attempt)

    if alignment is None:
        fail = {
            "seg_id": seg_id,
            "part": part_index,
            "seg_index": seg_index,
            "text": text,
            "error": str(last_err),
        }
        (FAIL_DIR / f"{seg_id}.json").write_text(
            json.dumps(fail, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return seg_id, f"failed: {last_err}"

    abs_base = offset + chunk_start
    issues: list[str] = []
    units_abs: list[dict] = []
    prev_end = -1e9
    for u in alignment["units_rel"]:
        s = round(u["start_ms"] / 1000 + abs_base, 3)
        e = round(u["end_ms"] / 1000 + abs_base, 3)
        if e < s:
            issues.append(f"unit '{u['unit']}' end<start ({s}-{e})")
        if s < abs_base - 0.02:
            issues.append(
                f"unit '{u['unit']}' start {s} 早於 chunk 起點 {abs_base:.3f}"
            )
        if e > abs_base + chunk_actual_dur + 0.02:
            issues.append(
                f"unit '{u['unit']}' end {e} 超出 chunk 尾 {abs_base + chunk_actual_dur:.3f}"
            )
        if s < prev_end - 0.08:
            issues.append(f"unit '{u['unit']}' 非單調（prev_end={prev_end:.3f}）")
        prev_end = max(prev_end, e)
        units_abs.append({"unit": u["unit"], "start_s": s, "end_s": e})

    cjk_map = char_unit_map(text)
    word_matches: list[dict] = []
    for m in AFFIRM_RE.finditer(text):
        ui = cjk_map[m.start()]
        uj = cjk_map[m.end() - 1]
        if ui is None or uj is None:
            issues.append(f"詞 '{m.group(0)}' 對不到單位")
            continue
        ws, we = units_abs[ui]["start_s"], units_abs[uj]["end_s"]
        if we <= ws:
            issues.append(f"詞 '{m.group(0)}' 時間區間異常 {ws}-{we}")
        word_matches.append(
            {
                "word": m.group(0),
                "text_span": [m.start(), m.end()],
                "start_s": ws,
                "end_s": we,
            }
        )

    result = {
        "ok": True,
        "seg_id": seg_id,
        "part": part_index,
        "seg_index": seg_index,
        "start": seg["start"],
        "end": seg["end"],
        "speaker": seg.get("speaker"),
        "text": text,
        "chunk_abs_start_s": round(abs_base, 3),
        "chunk_dur_s": round(chunk_actual_dur, 3),
        "word_matches": word_matches,
        "units": units_abs,
        "issues": issues,
        "fa": {
            "latency_s": round(alignment["latency_s"], 3),
            "token_count": alignment["token_count"],
            "audio_token_shift": alignment["audio_token_shift"],
        },
    }
    tmp_out = out_path.with_suffix(".tmp")
    tmp_out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_out.rename(out_path)
    try:
        wav_path.unlink()
    except OSError:
        pass
    return seg_id, "ok" if not issues else f"ok(issues={len(issues)})"


def main() -> None:
    t_start = time.monotonic()
    log("=== filter_align 開始 ===")
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    FAIL_DIR.mkdir(parents=True, exist_ok=True)

    combined = json.loads(
        (BASE / "transcript_combined.json").read_text(encoding="utf-8")
    )
    segments = combined["segments"]
    parts_meta = json.loads((BASE / "audio_parts.json").read_text(encoding="utf-8"))[
        "parts"
    ]

    part_dur_actual: dict[int, float] = {}
    for p in parts_meta:
        d = ffprobe_duration(BASE / p["file"])
        part_dur_actual[p["index"]] = d
        log(f"part {p['index']}: 名義 {p['duration_s']:.6f}s，實測 {d:.3f}s")

    # 探測 FA 伺服器
    with httpx.Client() as client:
        r = client.get(f"{FA_URL}/v1/models", timeout=15)
    if r.status_code != 200:
        raise SystemExit(f"FA 伺服器探測失敗: {r.status_code} {r.text[:200]}")
    log(f"FA 伺服器可達: {FA_URL}")

    work: list[tuple[int, int, dict]] = []
    for idx, seg in enumerate(segments):
        if AFFIRM_RE.search(seg["text"]):
            work.append((seg["part"], idx, seg))
    log(f"命中 {len(work)}/{len(segments)} 段，batch={WORKERS} 開始對齊")

    stats = {"ok": 0, "skipped": 0, "failed": 0, "with_issues": 0}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [
            pool.submit(process_segment, p, i, s, parts_meta[p], part_dur_actual)
            for p, i, s in work
        ]
        done = 0
        for f in as_completed(futures):
            seg_id, status = f.result()
            done += 1
            if status == "ok":
                stats["ok"] += 1
            elif status == "skipped":
                stats["skipped"] += 1
            elif status.startswith("ok"):
                stats["ok"] += 1
                stats["with_issues"] += 1
            else:
                stats["failed"] += 1
                log(f"{seg_id} 失敗: {status}")
            if done % 25 == 0 or done == len(futures):
                log(
                    f"進度 {done}/{len(futures)} ok={stats['ok']} skipped={stats['skipped']} "
                    f"failed={stats['failed']} with_issues={stats['with_issues']}"
                )

    # 合併檢查點 -> filtered_aligned.json
    merged: list[dict] = []
    for p, idx, _seg in work:
        rp = RESULT_DIR / f"p{p}_s{idx}.json"
        if rp.exists():
            merged.append(json.loads(rp.read_text(encoding="utf-8")))
    failures = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(FAIL_DIR.iterdir())
        if f.suffix == ".json"
    ]
    n_words = sum(len(r["word_matches"]) for r in merged)
    n_word_valid = 0
    for r in merged:
        for w in r["word_matches"]:
            # 品質旗標：時間倒置或超出段落範圍 ±0.5s 的樣本視為無效（步驟 6 只剪 valid）
            valid = (
                w["end_s"] > w["start_s"]
                and w["start_s"] >= r["start"] - 0.5
                and w["end_s"] <= r["end"] + 0.5
            )
            w["valid"] = valid
            n_word_valid += int(valid)
        r["n_word_valid"] = sum(1 for w in r["word_matches"] if w["valid"])
    n_issue_segs = sum(1 for r in merged if r["issues"])

    out = {
        "meta": {
            "video_id": combined.get("video_id"),
            "source": combined.get("source"),
            "total_duration_s": combined.get("total_duration_s"),
            "created": datetime.now().isoformat(timespec="seconds"),
            "filter": {
                "words": ["對", "沒錯", "確實"],
                "regex": r"(?<![不相互絕反派配視針])對(?![於不起象應吧])|沒錯|確實",
                "note": "使用者定案三詞表（2026-08-26）；「對」排除 對不起/對於/對象/對應/對吧/不對/相對/針對 等複合詞",
            },
            "padding_s": PAD_S,
            "fa_server": FA_URL,
            "fa_model": MODEL,
            "n_segments_total": len(segments),
            "n_segments_matched": len(work),
            "n_segments_aligned": len(merged),
            "n_segments_with_issues": n_issue_segs,
            "n_word_instances": n_words,
            "n_word_instances_valid": n_word_valid,
            "time_note": "所有 start_s/end_s 為影片絕對時間（秒）＝ part offset + chunk 起點（含兩側 200ms padding）+ FA 相對時間",
        },
        "failures": failures,
        "segments": merged,
    }
    tmp_out = OUT_PATH.with_suffix(".tmp")
    tmp_out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_out.rename(OUT_PATH)

    elapsed = time.monotonic() - t_start
    log(
        f"=== 完成: 對齊 {len(merged)}/{len(work)}，詞樣本 {n_words}（valid {n_word_valid}），"
        f"失敗 {len(failures)}，有 issue 段落 {n_issue_segs}，"
        f"耗時 {elapsed / 60:.1f} 分 -> {OUT_PATH.name} ==="
    )
    if failures:
        log(
            "WARNING: 存在失敗段落，詳見 filtered_aligned.json 之 meta.failures（可重跑補齊）"
        )


if __name__ == "__main__":
    main()
