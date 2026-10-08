# vLLM token_classify 文件歸檔

- 來源：<https://docs.vllm.ai/en/latest/examples/pooling/token_classify/>（dev preview）
- 抓取時間：2026-08-27
- 用途：驗證 Qwen3-ForcedAligner 官方 FA 流程（Forced Alignment Offline / Online 範例），
  對照 `exp/N9boWvU-KkA/scripts/filter_align.py` 的請求與 token 位置對應邏輯。

## 檔案

- `token-classify-page.md`：該頁面的 markdown 快照（Forced Alignment 兩節完整保留；
  NER 兩節與本專案無關，以註記略過）。

## 關鍵要點（對照本專案用）

1. 官方 FA 單位是「呼叫者傳入的 words 清單」，prompt = 音訊前綴 +
   `word1<timestamp><timestamp>word2...` + 尾端 `<timestamp><timestamp>`。
2. 對齊讀點：token 序列中所有 `<timestamp>`（`timestamp_token_id`）位置的
   argmax(classify_num) × `timestamp_segment_time`。
3. 單位配對：word i 的 start/end = 第 2i / 2i+1 個 `<timestamp>` 預測。
4. **`audio_token_shift`**：pooling 回傳長度可能大於文字 token 數（音訊被展開成多 token），
   位於 `audio_pad_token_id` 之後的 `<timestamp>` 要加 `shift` 才對到正確 prediction 位置。
   本專案 `filter_align.py align_once` 已實作同邏輯。
