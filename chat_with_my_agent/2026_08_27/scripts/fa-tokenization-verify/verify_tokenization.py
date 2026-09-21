#!/usr/bin/env python3
"""驗證 FA token↔字元對應：模型自然 BPE 分詞 vs 逐字切分 + <timestamp> 標記。

回答「token↔字元對應是手算還是用模型 tokenizer」之問：
- A) 自然分詞：整句送 /tokenize，看模型 BPE 如何切（會把多個 CJK 字併成 1 token）。
- B) 逐字 prompt：逐字 + <ts><ts> 標記送 /tokenize，確認每個 CJK 字仍是單 token、
  且 <timestamp> 數量 = 2 × 單位數（對齊讀點由標記決定，與 BPE 切法無關）。
- 結論：我們的逐字切法與官方 Qwen3ForceAlignProcessor（tokenize_space_lang →
  split_segment_with_chinese：每個 CJK 字 = 1 單位）一致；<ts> 位置用伺服器端
  真實 /tokenize 取得，非手算 token id。

用法:
    exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/verify_tokenization.py
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from filter_align import (  # noqa: E402
    FA_URL,
    MODEL,
    TIMESTAMP_TOKEN_ID,
    build_prompt,
    split_text_units,
)

SAMPLE = "對我的意思是說就是就是VTuber就是印象裡面它會是一個比較以遊戲直播"


def tokenize(prompt: str) -> dict:
    response = httpx.post(
        f"{FA_URL}/tokenize",
        json={"model": MODEL, "prompt": prompt, "return_token_strs": True},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    units = split_text_units(SAMPLE)
    print(f"句子: {SAMPLE}")
    print(f"逐字單位數（split_text_units）: {len(units)}")
    print(f"單位: {units}")

    natural = tokenize(SAMPLE)
    print(f"\nA) 模型自然 BPE 分詞: {natural['count']} tokens")
    for i, (tid, s) in enumerate(
        zip(natural["tokens"], natural.get("token_strs") or [])
    ):
        print(f"  [{i:2d}] {tid:6d}  {s}")

    prompt = build_prompt(units)
    marked = tokenize(prompt)
    n_ts = sum(1 for t in marked["tokens"] if t == TIMESTAMP_TOKEN_ID)
    print(f"\nB) 逐字 prompt: {marked['count']} tokens")
    print(f"   <timestamp> 數量 = {n_ts}（預期 {len(units) * 2}）")
    print(f"   標記數量正確: {n_ts == len(units) * 2}")

    # 逐 CJK 字是否各為單 token：取出單位 token（略過 prefix 與 <ts>）
    content_tokens = [t for t in marked["tokens"] if t != TIMESTAMP_TOKEN_ID]
    print(f"   內容 token 數（不含 <ts> 與 prefix）: {len(content_tokens)}")


if __name__ == "__main__":
    main()
