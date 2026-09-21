#!/usr/bin/env python3
"""逐句切片 v3：從 transcript_combined.json 抓出指定的 14 句，各切成獨立
MKV＋AV1（libsvtav1）＋AAC clip，輸出到 clips_intro/。

定位方式：時間順序遊標＋原文逐字匹配（清單本身即時間序，天然消解
「對」這類重複短句的歧義）。

用法：uv run exp/N9boWvU-KkA/scripts/cut_intro_sentences.py [--workers 8]
"""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
TRANSCRIPT = EXP / "transcript_combined.json"
SOURCE = EXP / "download" / "N9boWvU-KkA_composite.mkv"
OUTDIR = EXP / "clips_intro"

MAX_PAD = 0.15  # 每邊最大留白（秒）
PAD_GAP_RATIO = 0.4  # 留白不超過與相鄰段時間隙的這個比例

# (slug, 逐字原文)——順序即期望的時間順序
SENTENCES = [
    ("01_date_weekday", "今天是2026年7月7號禮拜二"),
    ("02_time_evening", "現在時間是晚上5:04"),
    ("03_channel_name", "大家在收聽的是宅宅軍團長的直播頻道"),
    ("04_interview_show", "我們今天是一個訪談型別的節目"),
    ("05_book_title", "我們今天因為有一本書叫做VTuber學"),
    ("06_japanese_edition", "我不知道大家以前就是有沒有看過日文版相關的內容"),
    ("07_chinese_edition", "他現在出了中文版"),
    ("08_invited_editor", "然後今天就邀請到他在中文版這邊出版的編輯"),
    ("09_chat_together", "來跟我們一起聊聊天"),
    ("10_invite_self_intro", "那我們開頭呢我想要請編輯自我介紹一下"),
    ("11_self_intro_name", "大家好我是貓頭鷹出版社的編輯王政偉"),
    ("12_editor_of_book", "對然後我也是這本書VTuber學的編輯"),
    ("13_right_dui", "對"),
    ("14_pretty_nice", "蠻棒的"),
]


def locate(segments):
    """時間順序遊標匹配，回傳 [(slug, seg, gap_before, gap_after), ...]；
    任一未命中即中止。間隙供護欄式 padding 用（相鄰句可能是不要的句子）。"""
    hits, cursor = [], 0
    for slug, text in SENTENCES:
        for i in range(cursor, len(segments)):
            if segments[i]["text"].strip() == text:
                gb = segments[i]["start"] - segments[i - 1]["end"] if i > 0 else MAX_PAD
                ga = (
                    segments[i + 1]["start"] - segments[i]["end"]
                    if i + 1 < len(segments)
                    else MAX_PAD
                )
                hits.append((slug, segments[i], gb, ga))
                cursor = i + 1
                break
        else:
            sys.exit(f"[FATAL] 遊標 {cursor} 之後找不到句子：{slug} 「{text}」")
    return hits


def cut(slug, seg, gap_before, gap_after):
    """單句切片：護欄式 padding＋ffmpeg 重編碼。回傳 (slug, 起, 迄, 實測時長)。"""
    start, end = seg["start"], seg["end"]
    pad_b = min(MAX_PAD, max(0.0, gap_before) * PAD_GAP_RATIO)
    pad_a = min(MAX_PAD, max(0.0, gap_after) * PAD_GAP_RATIO)
    t0, t1 = start - pad_b, end + pad_a
    out = OUTDIR / f"clip_{slug}.mkv"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{t0:.3f}",
        "-i",
        str(SOURCE),
        "-t",
        f"{t1 - t0:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "libsvtav1",
        "-preset",
        "5",
        "-crf",
        "24",
        "-b:v",
        "0",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-avoid_negative_ts",
        "make_zero",
        "-y",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return slug, t0, t1, float(probe.stdout.strip())


def _work(hit):
    """ProcessPoolExecutor 需模組級可 pickle 函式（lambda 不可）。"""
    return cut(*hit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    segments = json.loads(TRANSCRIPT.read_text())["segments"]
    hits = locate(segments)
    OUTDIR.mkdir(exist_ok=True)
    for old in OUTDIR.glob("*.mkv"):
        old.unlink()

    print(f"匹配 {len(hits)} 句，開始切片（workers={args.workers}）…")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_work, hits))

    ok = True
    for (slug, seg, _gb, _ga), (r_slug, t0, t1, dur) in zip(hits, results):
        dev = abs(dur - (t1 - t0))
        flag = "OK " if dev <= 0.06 else "!! "
        ok &= dev <= 0.06
        print(
            f"{flag}clip_{slug}.mkv  {t0:.3f}-{t1:.3f}s  實測 {dur:.3f}s  "
            f"| 原文「{seg['text']}」"
        )
    print("全部通過" if ok else "有片時長偏差過大，請檢查！")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
