# FA 對齊測試討論細節（支線任務）

## 目標

- 驗證 vLLM 部署的 `Qwen/Qwen3-ForcedAligner-0.6B`（`http://10.46.219.5:8755`）能否對
  `output/是我用AI跑出來的.aac`（2.02s）+ 轉錄稿「是我用AI跑出來的」產出逐字時間戳。
- 成功後用 ffmpeg 產出黑底白字字幕預覽片，放 `output/`，檔名含今日日期（2026-08-26）。
- 注意字幕置中與中文字體支援。

## 探索過程

### 1. 端點探測（curl /openapi.json）

FA 伺服器只有 pooling 類端點，**沒有** `/v1/chat/completions` 或 `/v1/audio/transcriptions`：

```
/load /version /health /metrics /tokenize /detokenize /v1/models /ping /invocations /pooling
```

- 模型名：`Qwen/Qwen3-ForcedAligner-0.6B`，`max_model_len=8192`。
- 推論：這是 vLLM 的 **pooling server**（非 LLM chat server），對齊走 `/pooling` + `task=token_classify`。

### 2. 模型 config（HF raw main 拉取）

- `timestamp_token_id = 151705`（即 `<timestamp>`）
- `timestamp_segment_time = 80`（ms/桶）
- `classify_num = 5000`（5000 × 80ms = 400s 最大對齊範圍）
- 音訊特殊 token：`audio_start=151669`（`|audio_start|>`）、`audio_pad=151676`（`|audio_pad|>`）、`audio_end=151670`（`|audio_end|>`）

### 3. 模型卡官方 online 範例（vLLM 倉庫 `examples/pooling/token_classify/forced_alignment_online.py`）

關鍵請求格式（`/pooling`）：

```json
{
  "model": "Qwen/Qwen3-ForcedAligner-0.6B",
  "messages": [{"role":"user","content":[
      {"type":"text","text":"<prefix + word<timestamp><timestamp>...>"},
      {"type":"audio_url","audio_url":{"url":"data:audio/wav;base64,..."}}
  ]}],
  "task": "token_classify",
  "chat_template": "{{ messages[0]['content'] }}"
}
```

- prefix = `|audio_start|>|audio_pad|>|audio_end|>`
- 每兩枚 `<timestamp>`（token id 151705）包一個 word/字，取 argmax(bin)×80ms → start/end。
- 範例要求伺服器帶 `--trust-request-chat-template` 才會接受自訂 chat_template。
- 本地範例用 `AutoTokenizer` 定位 audio pad；本專案改用**伺服器端 `/tokenize`（同 messages）** 取 token 序列，避免本地裝 HF tokenizer。
- 偏移公式：`pred_idx = i + (len(preds) - len(tokens))`（僅當 i > audio_pad_index）。

## 關鍵發現（卡點）

- 第一版（prompt 前綴含 audio token 文字 + 自訂 chat_template）→ 400：
  `Chat template is passed with request, but --trust-request-chat-template is not set.`
- 第二版（去掉 chat_template，messages 形式）→ 200 但 `/tokenize` 回傳的 42 個 token 中**沒有 151705（<timestamp>）也沒有中文文字**；
  序列為 `im_start user \n im_end \n im_start assistant \n audio_start, 28×audio_pad, audio_end, im_end, \n im_start, 77091, \n`。
  → 伺服器的預設模板似乎**丟掉了 text part**，只渲染了音訊。
- 結論：目前無法在不改伺服器啟動參數的前提下拿到有效對齊。

## 待決策（與使用者討論中）

1. 重啟 FA 伺服器加 `--trust-request-chat-template`（與官方範例一致，最穩）；或
2. 確認 `vllm serve` 啟動指令是否已帶 `--chat-template`（若已提供正確 Qwen3 模板，改探測即可）；或
3. 改用 `qwen_asr.Qwen3ForcedAligner` 本地部署（需 GPU，較重）。
