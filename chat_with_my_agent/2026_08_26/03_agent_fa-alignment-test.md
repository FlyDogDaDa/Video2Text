---
created: 2026-08-26
author: agent
type: agent
tags: [fa-aligner, vllm, forced-alignment, 實驗]
---

# 支線：測試 Qwen3-ForcedAligner 對齊 + 字幕預覽規劃

## What

- 為「肯定單字剪輯」實驗（exp/N9boWvU-KkA）先打通 ForcedAligner：
  寫 `exp/N9boWvU-KkA/scripts/test_fa.py`，用 `output/是我用AI跑出來的.aac`
  （2.02s，轉錄稿「是我用AI跑出來的」）測試逐字對齊。
- 探測 FA 伺服器（10.46.219.5:8755）API：只有 pooling 類端點，對齊走
  `POST /pooling` + `task=token_classify`。
- 尚未產出字幕預覽影片——對齊測試卡在伺服器配置（見 Uncertainty / Follow-up）。

## Why

主流程步驟 5（過濾肯定詞 + 精準對齊）依賴 FA，先在小音檔上驗證端點用法、
token 對齊邏輯（`<timestamp>` 位置 + audio pad 偏移），再套用到 4 份切分音訊。

## How

- curl `/openapi.json` 確認端點：`/pooling`、`/tokenize`、`/tokenize`（messages 形式可用）等；
  模型 `Qwen/Qwen3-ForcedAligner-0.6B`，`max_model_len=8192`。
- 模型 config：`timestamp_token_id=151705`、`timestamp_segment_time=80ms`、`classify_num=5000`。
- 照 vLLM 官方範例（`examples/pooling/token_classify/forced_alignment_online.py`）寫 test_fa.py：
  音訊轉 16k mono wav → base64 data-uri → messages(text+audio_url) → `/pooling`
  → 每個 `<timestamp>` 位置 argmax(5000 bins)×80ms。
- 用伺服器 `/tokenize`（同 messages）取代本地 AutoTokenizer，避免本地裝 HF 依賴。
- 第一次跑：自訂 `chat_template` 被拒（400，未開 `--trust-request-chat-template`）。
  去掉後 200，但 `/tokenize` 顯示預設模板**只保留音訊、丟掉文字部分**
  （42 tokens 全是模板 + 28 個 audio_pad，無 `<timestamp>`）→ 對齊結果不可信。

## Follow-up

- 需使用者決策（暫停中）：
  1. 重啟 FA 伺服器加 `--trust-request-chat-template`（官方範例做法，推薦）；或
  2. 告知現行 `vllm serve` 啟動參數，確認是否已帶正確 `--chat-template`；或
  3. 改本地 `qwen_asr.Qwen3ForcedAligner`（需 GPU）。
- 對齊跑通後：ffmpeg 產黑底白字字幕預覽（`output/`，檔名含 2026-08-26），
  注意中文字體（待 `fc-list :lang=zh` 確認）與置中（ASS `Alignment=2`）。

## Uncertainty

- 伺服器預設 chat template 實際行為：`/tokenize` 結果顯示 text part 被丟掉，
  但尚未確認是模板缺 audio-aware 邏輯還是 `messages` 多模態處理 bug。
- FA 對 2 秒短音 + 短句的精度未經實測驗證（目前連基本對齊都未跑通）。

## References

- [討論細節](references/03_agent_fa-alignment-test.md)
- [程式歸檔](scripts/fa-pooling-test/README.md)
- [FA 伺服器 OpenAPI spec](assets/fa-openapi-spec/fa_openapi.json)
- [模型卡](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B)
