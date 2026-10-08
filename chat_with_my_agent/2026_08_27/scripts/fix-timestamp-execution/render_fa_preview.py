#!/usr/bin/env python3
"""長句 FA 對齊預覽影片（真實影片 + 逐字高亮字幕），供肉眼檢查對齊精度。

用法:
    exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/render_fa_preview.py p0_s173

對 filtered_aligned.json 指定 seg_id：
- 從 download/N9boWvU-KkA_composite.mkv 以 ffmpeg 切片（chunk ±0.4s 邊距，
  重編碼確保起點幀精確，不受 keyframe 影響）
- 產生 ASS 字幕：baseline 事件顯示全句；每個 unit 在其 FA 時間區間顯示
  黃色高亮 + 第二行小字標註該 unit 的 FA 絕對時間（span 反轉會標註）
- 輸出: output/2026-08-27_FA長句預覽_<seg_id>.mp4
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
COMPOSITE = BASE / "download" / "N9boWvU-KkA_composite.mkv"
ALIGNED = BASE / "filtered_aligned.json"
TMP = BASE / "tmp"
OUT_DIR = BASE.parent.parent / "output"
MARGIN = 0.4
TODAY = "2026-08-27"

WHITE = "&H00FFFFFF&"
YELLOW = "&H00FFFF00&"
GRAY = "&H00C0C0C0&"


def ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def unit_spans(text: str, units: list[str]) -> list[tuple[int, int]]:
    """每個 unit 對應 text 的 (start, end) 字元區間（CJK 單字、ASCII 連續串）。"""
    spans: list[tuple[int, int]] = []
    i = 0
    for u in units:
        if len(u) > 1:
            spans.append((i, i + len(u)))
            i += len(u)
        else:
            spans.append((i, i + 1))
            i += 1
    return spans


def highlighted(text: str, spans: list[tuple[int, int]], hi: int) -> str:
    out = []
    for idx, (a, b) in enumerate(spans):
        chunk_text = text[a:b]
        if idx == hi:
            out.append(f"{{\\c{YELLOW}}}{chunk_text}{{\\c{WHITE}}}")
        else:
            out.append(chunk_text)
    return "".join(out)


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit(__doc__)
    seg_id = sys.argv[1].strip()

    data = json.loads(ALIGNED.read_text(encoding="utf-8"))
    seg = next((s for s in data["segments"] if s["seg_id"] == seg_id), None)
    if seg is None:
        raise SystemExit(f"filtered_aligned.json 找不到 seg_id={seg_id}")

    text = seg["text"]
    units = seg["units"]
    spans = unit_spans(text, units)
    if len(spans) != len(units):
        raise SystemExit("unit 數與文字不符，無法產生高亮")

    chunk_start = seg["chunk_abs_start_s"]
    chunk_dur = seg["chunk_dur_s"]
    clip_start = max(0.0, chunk_start - MARGIN)
    clip_dur = (chunk_start + chunk_dur + MARGIN) - clip_start

    ass_lines = [
        "[Script Info]",
        f"Title: FA alignment preview {seg_id}",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Noto Sans CJK TC,80,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,100,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # baseline 事件：全句白字 + 上下文小字
    info_base = (
        f"FA 對齊預覽 {seg_id}｜ASR {seg['start']:.2f}–{seg['end']:.2f}s"
        f"｜chunk {chunk_start:.2f}+{chunk_dur:.2f}s"
    )
    ass_lines.append(
        f"Dialogue: 0,{ts(0.0)},{ts(clip_dur)},Default,,0,0,0,,"
        f"{text}\\N{{\\fs40}}{{\\c{GRAY}}}{info_base}"
    )

    # 每個 unit 一個高亮事件（FA 時間區間）
    for i, u in enumerate(units):
        s_abs = u["start_s"]
        e_abs = u["end_s"]
        s_rel = s_abs - clip_start
        e_rel = max(e_abs, s_abs + 0.08) - clip_start
        s_rel = max(0.0, min(s_rel, clip_dur))
        e_rel = max(s_rel + 0.08, min(e_rel, clip_dur))
        note = f"FA: {u['unit']} {s_abs:.3f}→{e_abs:.3f}s"
        if e_abs < s_abs:
            note += "（span 反轉）"
        elif u.get("fixed"):
            note += "（補整）"
        line1 = highlighted(text, spans, i)
        ass_lines.append(
            f"Dialogue: 0,{ts(s_rel)},{ts(e_rel)},Default,,0,0,0,,"
            f"{line1}\\N{{\\fs40}}{{\\c{GRAY}}}{note}"
        )

    TMP.mkdir(exist_ok=True)
    ass_path = TMP / f"fa_preview_{seg_id}.ass"
    ass_path.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"{TODAY}_FA長句預覽_{seg_id}.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{clip_start:.3f}",
        "-i",
        str(COMPOSITE),
        "-t",
        f"{clip_dur:.3f}",
        "-vf",
        f"ass={ass_path}",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    print(
        f"OK {out_path}（{clip_dur:.2f}s，{len(units)} units，clip {clip_start:.3f} 起）"
    )


if __name__ == "__main__":
    main()
