---
created: 2026-06-09
author: Agent
type: agent
status: draft
tags: [vllm, gemma-4, multimodal, video, openai-api, research]
---

# vLLM + Gemma-4 + 影片處理研究

## What

研究 vLLM server（OpenAI 相容 API）如何處理 Gemma-4 的影片/圖片輸入格式，以及目前安裝版本（v0.22.1 stable）的支援狀態。

## Why

現有 `try_video.py` 使用離線推理 (`LLM.generate`) 處理影片，但專案主流程要透過 vLLM 的 `/v1/chat/completions` API 呼叫。需要確認影片功能是否可於 stable v0.22.1 上使用。

## 研究成果

### 1. OpenAI API 多模態 content 格式

vLLM 的 `/v1/chat/completions` 接受 `content` 為字串或陣列：

**文字：**
```json
{"role": "user", "content": "What is this?"}
```

**圖片/音訊：**
```json
{
  "role": "user",
  "content": [
    {"type": "image_url", "image_url": {"url": "https://.../cat.jpg"}},
    {"type": "audio_url", "audio_url": {"url": "https://.../audio.wav"}},
    {"type": "text", "text": "Describe this image."}
  ]
}
```

**影片（vLLM 開發 branch 支援）：**
```json
{
  "role": "user",
  "content": [
    {"type": "video_url", "video_url": {"url": "https://.../video.mp4"}},
    {"type": "text", "text": "Summarize what happens."}
  ]
}
```

### 2. vLLM Server 啟動影片支援

官方檔案建議啟動時加 `--limit-mm-per-prompt`：

```bash
vllm serve google/gemma-4-E2B-it \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image": 4, "video": 1}'
```

### 3. 動態視覺解析度 (Dynamic Vision Resolution)

Gemma-4 支援 per-request vision token budget（70/140/280/560/1120 tokens），server 層級可設預設值：

```bash
vllm serve ... --mm-processor-kwargs '{"max_soft_tokens": 560}'
```

### 4. 現有 `try_video.py` 狀態

| 專案 | 狀態 |
|------|------|
| `vllm.multimodal.utils.fetch_video` | ✅ 存在 |
| `limit_mm_per_prompt={"video": 1}` | ✅ API 接受 |
| `"type": "video"` | API 格式支援 |
| vLLM server 能處理 `video_url`？ | ❌ **stable v0.22.1 不支援** |
| `LLM.generate()` 離線推理？ | ❌ 需要 custom branch |

### 5. vLLM Server 確認

目前 server 在 port 8746 正常執行，API 測試 200 OK：

```json
{
  "id": "google/gemma-4-12B-it-qat-w4a16-ct",
  "max_model_len": 262144,
  ...
}
```

### 6. 結論

**影片功能在 v0.22.1 stable 不可用。** 檔案明確指出影片處理 pipeline 在 "custom vLLM branch" 中。

**可能的解決路徑：**

| 選項 | 說明 | 風險 |
|------|------|------|
| A: 升級 nightly vLLM | 取得影片支援 | 可能破壞現有的 TRITON_ATTN 修復 |
| B: 先跑通圖片 | 用 `image_url` 驗證端到端流程 | 需要改影片為圖片的處理邏輯 |
| C: 影片抽幀送圖片 | 從 mp4 抽幀 → 當多張 `image_url` 送進 API | 穩定但 token 使用量大 |

## References

- [Gemma 4 Usage Guide - vLLM Recipes](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
- [vLLM OpenAI Compatible Server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)
- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [try_video.py](../chat_wtih_my_agent/08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py)
