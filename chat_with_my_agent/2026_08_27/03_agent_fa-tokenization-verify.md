---
created: 2026-08-27
author: agent
type: agent
tags: [fa-alignment, tokenization, qwen3-forcedaligner, video2text]
---

# FA 分詞驗證：token↔字元走伺服器 /tokenize，非手算

## What

- 回答使用者疑慮「token 對應字元是手算還是用 tokenizer」：實測確認
  `filter_align.py` 全程走 vLLM 伺服器 `/tokenize` 取**真實** token_ids，無任何手算。
- 新寫 `exp/N9boWvU-KkA/scripts/verify_tokenization.py` 實測 30 單位樣本句：
  - 自然 BPE 分詞：18 tokens（CJK 多字併 token）
  - 逐字 prompt（含 `<timestamp>` 標記）：94 tokens，其中 `<timestamp>`（151705）共 60 = 2×30，全部對位正確
- 結論三點：
  1. token 序列來自伺服器 `/tokenize`（同 messages + chat_template，與 FA 請求一致）
  2. 逐字切分＝官方 `Qwen3ForceAlignProcessor` 設計，與我們現有做法一致
  3. de-tokenizer 不需要：逐字方案下單位序列本來就已知，2N 個 bin 直接對回，
     vLLM 文件裡的 detokenize 步驟只適用於「模型自由分詞」場景

## Why

- 使用者發現撇除時間戳後單看 token 時機都準確，懷疑根因在分詞對應，
  建議研究官方流程 `tokenizer→IDs→FA→時間pool→classify_num+de-tokenizer→時間戳`。
- 必須用實測而非推斷回答：直接重放 `/tokenize` 對齊對照是最硬證據。

## How

- `verify_tokenization.py` 對同一句跑 A/B 兩組 `/tokenize`（`return_token_strs: true`），
  比對 token 數與 151705 出現位置；腳本與 `filter_align.py` 歸檔於
  `scripts/fa-tokenization-verify/`。
- 關鍵參數：`timestamp_token_id=151705`、`timestamp_segment_time=80ms`、
  `audio_pad_token_id=151676`。

## Follow-up

- 無。此問題已關閉；時間戳正確性由 log 02 的 fix + 目檢收尾。

## Uncertainty

- `/tokenize` 回傳的 CJK `token_strs` 是 latin1 解 UTF-8 的亂碼，
  但 token id 與數量正確可用；若要人讀需自行 re-encode。暫定不影響流程。

## References

- [討論細節](references/03_agent_fa-tokenization-verify.md)
- [腳本歸檔](scripts/fa-tokenization-verify/)（verify_tokenization.py、filter_align.py）
- [vLLM token_classify 文件](assets/vllm-token-classify-docs/README.md)
- [vLLM Forced Alignment 原始文件](https://docs.vllm.ai/en/latest/examples/pooling/token_classify/#forced-alignment-offline)
