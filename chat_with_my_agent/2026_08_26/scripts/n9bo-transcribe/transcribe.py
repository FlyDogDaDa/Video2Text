#!/usr/bin/env python3
"""步驟 3：串行轉錄 4 份音訊，串接成完整轉錄稿。

- 依序 POST audio_part_0..3.wav 到 ASR 伺服器 /v1/audio/transcriptions
  （model OpenMOSS-Team/MOSS-Transcribe-Diarize，response_format=json，
  不送自訂 prompt → 用 server 端 default prompt；
  vLLM build 有併發回應錯位風險，嚴禁併發，本腳本串行）
- regex 解析 [start][Sxx]text[end] → segments（各份為該份相對時間）
- 各份存 transcript_part_N.json（保留原始簡體 raw＋解析後 segments）
- 串接：start/end 各加該份 offset_s → 影片絕對時間 → transcript_combined.json
- 可續跑：已存在 transcript_part_N.json 的部分直接跳過（中斷後重跑安全）
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
ASR_URL = "http://10.46.219.5:8750/v1/audio/transcriptions"
MODEL_ID = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
TIMEOUT_S = 1800.0  # 單份 ~24 分鐘音訊，給足 30 分鐘
RETRY = 2  # 每份最多 3 次嘗試（初次 + 2 次重試）

# MOSS canonical 輸出：[start][Sxx]text[end]
SEGMENT_RE = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]",
    re.DOTALL,
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_segments(text: str) -> list[dict]:
    return [
        {
            "start": float(start),
            "end": float(end),
            "speaker": speaker,
            "text": body.strip(),
        }
        for start, speaker, body, end in SEGMENT_RE.findall(text)
    ]


def transcribe_once(part_file: Path) -> tuple[str, dict | None]:
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
    return body.get("text", ""), body.get("usage")


def main() -> int:
    meta = json.loads((BASE / "audio_parts.json").read_text(encoding="utf-8"))
    parts = meta["parts"]

    part_results: list[dict] = []
    for p in parts:
        idx = p["index"]
        out_path = BASE / f"transcript_part_{idx}.json"
        if out_path.exists():
            log(f"[part {idx}] transcript_part_{idx}.json 已存在 → 跳過（續跑模式）")
            part_results.append(json.loads(out_path.read_text(encoding="utf-8")))
            continue

        part_file = BASE / p["file"]
        offset = float(p["offset_s"])
        duration = float(p["duration_s"])
        last_err: Exception | None = None
        for attempt in range(1, RETRY + 2):
            t0 = time.time()
            try:
                log(
                    f"[part {idx}] 送轉錄 attempt #{attempt} "
                    f"({part_file.name}, {duration:.1f}s, offset {offset:.3f}s)…"
                )
                raw, usage = transcribe_once(part_file)
                elapsed = time.time() - t0
                segments = parse_segments(raw)
                if not segments:
                    raise RuntimeError(
                        f"未解析到 [start][Sxx]…[end] 區段；raw 前 300 字：{raw[:300]!r}"
                    )
                # 出界檢查：端點超出該份時長太多代表 timestamp 異常（偏離信號）
                for seg in segments:
                    if seg["end"] > duration + 5.0 or seg["start"] < -5.0:
                        log(f"[part {idx}] ⚠ segment 時間出界：{seg}")
                out = {
                    "part": idx,
                    "file": p["file"],
                    "offset_s": offset,
                    "duration_s": duration,
                    "elapsed_s": round(elapsed, 1),
                    "usage": usage,
                    "raw": raw,
                    "segments": segments,  # 該份相對時間
                }
                out_path.write_text(
                    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log(f"[part {idx}] 完成：{len(segments)} segments，耗時 {elapsed:.1f}s")
                part_results.append(out)
                last_err = None
                break
            except Exception as e:
                last_err = e
                log(f"[part {idx}] attempt #{attempt} 失敗：{e}")
                if attempt <= RETRY:
                    time.sleep(15)
        if last_err is not None:
            log(
                f"[part {idx}] 重試 {RETRY} 次後仍失敗，停止等使用者裁決（其餘 part 不受影響）"
            )
            return 1

    # 串接：相對時間 + offset → 影片絕對時間
    combined_segments: list[dict] = []
    for out in part_results:
        offset = float(out["offset_s"])
        for seg in out["segments"]:
            combined_segments.append(
                {
                    "start": round(seg["start"] + offset, 3),
                    "end": round(seg["end"] + offset, 3),
                    "speaker": seg["speaker"],
                    "text": seg["text"],
                    "part": out["part"],
                }
            )
    combined_segments.sort(key=lambda s: s["start"])

    combined = {
        "video_id": "N9boWvU-KkA",
        "source": "N9boWvU-KkA_composite.mkv",
        "total_duration_s": meta["total_duration_s"],
        "note": (
            "start/end 為影片絕對時間（秒）；text 為模型原始簡體輸出；"
            "speaker 編號為各 part 獨立 diarization，跨 part 不具同一性"
        ),
        "parts": [
            {
                "part": o["part"],
                "offset_s": o["offset_s"],
                "duration_s": o["duration_s"],
                "segments": len(o["segments"]),
            }
            for o in part_results
        ],
        "segments": combined_segments,
    }
    out_combined = BASE / "transcript_combined.json"
    out_combined.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"串接完成：共 {len(combined_segments)} segments → {out_combined.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
