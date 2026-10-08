#!/usr/bin/env python3
"""肯定詞上下文分析：盤點 對 / 沒錯 / 確實 在轉錄稿中的出現情境。

用途：決定步驟 5 過濾用的 regex（特別是「對」的複合詞排除，
如 對不起 / 面對 / 相對 / 絕對 / 對吧 …）。

用法:
    exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/inspect_words.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
COMBINED = BASE / "transcript_combined.json"
WORDS = ["對", "沒錯", "確實"]
CTX_BEFORE = 3
CTX_AFTER = 3


def analyze(word: str, segments: list[dict]) -> None:
    total = 0
    seg_hit = 0
    prev_c: Counter[str] = Counter()
    next_c: Counter[str] = Counter()
    ctx_c: Counter[str] = Counter()

    for seg in segments:
        text = seg["text"]
        if word not in text:
            continue
        seg_hit += 1
        i = 0
        while True:
            i = text.find(word, i)
            if i < 0:
                break
            total += 1
            prev = text[i - 1] if i > 0 else "⟦句首⟧"
            nxt = text[i + len(word)] if i + len(word) < len(text) else "⟦句尾⟧"
            prev_c[prev] += 1
            next_c[nxt] += 1
            ctx_c[
                f"{text[max(0, i - CTX_BEFORE):i]}▎{text[i:i + len(word)]}▎{text[i + len(word):i + len(word) + CTX_AFTER]}"
            ] += 1
            i += len(word)

    print(f"=== 「{word}」：共 {total} 次，於 {seg_hit} 段 ===")
    print(f"  前置字 Top15: {prev_c.most_common(15)}")
    print(f"  後置字 Top15: {next_c.most_common(15)}")
    print("  情境 Top40:")
    for ctx, count in ctx_c.most_common(40):
        print(f"    {count:4d}  {ctx}")
    print()


def main() -> None:
    data = json.loads(COMBINED.read_text(encoding="utf-8"))
    segments = data["segments"]
    print(f"轉錄稿共 {len(segments)} 段\n")
    for word in WORDS:
        analyze(word, segments)


if __name__ == "__main__":
    main()
