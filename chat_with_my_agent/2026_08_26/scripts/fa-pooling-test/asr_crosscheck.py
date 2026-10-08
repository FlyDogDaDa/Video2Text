#!/usr/bin/env python3
"""交叉驗證：用 MOSS-Transcribe-Diarize ASR 獨立轉錄同一段音訊，
對照 Qwen3-ForcedAligner 給出的逐字時間戳是否合理。

用法:
    .venv/bin/python scripts/asr_crosscheck.py [音訊檔路徑]
"""

from __future__ import annotations

import glob
import json
import re
import time
from pathlib import Path

import httpx

VLLM_BASE_URL = "http://10.46.219.5:8750"
MODEL_ID = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
TRANSCRIBE_URL = f"{VLLM_BASE_URL}/v1/audio/transcriptions"

SEGMENT_RE = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]",
    re.DOTALL,
)


def main() -> None:
    import sys

    if len(sys.argv) > 1:
        audio_path = Path(sys.argv[1])
    else:
        matches = sorted(glob.glob("output/*.opus"))
        if not matches:
            raise SystemExit("找不到 output/*.opus")
        audio_path = Path(matches[0])

    mime = "audio/opus"
    t0 = time.monotonic()
    with open(audio_path, "rb") as f:
        resp = httpx.post(
            TRANSCRIBE_URL,
            data={"model": MODEL_ID, "response_format": "json"},
            files={"file": (audio_path.name, f, mime)},
            timeout=600,
        )
    elapsed = time.monotonic() - t0
    if resp.status_code != 200:
        raise SystemExit(f"vLLM 回傳 {resp.status_code}：{resp.text[:500]}")

    body = resp.json()
    raw = body.get("text", "")
    print(f"檔案: {audio_path}")
    print(f"延遲: {elapsed:.1f}s")
    print(f"原始輸出: {raw}")

    segments = [
        {"start": float(a), "speaker": b, "text": c.strip(), "end": float(d)}
        for a, b, c, d in SEGMENT_RE.findall(raw)
    ]
    if segments:
        print("segments:")
        for seg in segments:
            print(
                f"  {seg['start']:8.3f} - {seg['end']:8.3f}  [{seg['speaker']}] {seg['text']}"
            )
    else:
        print("⚠ 未解析到 [start][Sxx]...[end] 區段")

    out = Path("exp/N9boWvU-KkA/asr_crosscheck_result.json")
    out.write_text(
        json.dumps(
            {
                "audio": str(audio_path),
                "raw": raw,
                "segments": segments,
                "latency_s": round(elapsed, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"存檔: {out}")


if __name__ == "__main__":
    main()
