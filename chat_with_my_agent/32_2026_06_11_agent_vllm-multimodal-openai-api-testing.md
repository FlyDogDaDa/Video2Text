---
created: 2026-06-11
author: Human
type: agent
status: final
tags: [vllm, gemma4, multimodal, openai-api, guided-decoding, thinking-mode, structured-output]
---

# vLLM Server API 多模態實測：thinking + structured output bug 確認

## What

以 `how_to_use_vllm_multimodal_via_openai_api.py` 為示範腳本，全面測試 vLLM Server API 的多模態能力，並確認 `thinking mode` 與 `structured output` 並用時的 bug。

## Why

31 號定了 Server API 策略，現在要實際驗證 OpenAI SDK 呼叫 vLLM 的可行性。同時需要確認思考模式 + 結構化輸出（雙功能並用）是否可正常運作，這直接關係到後續 `main.py` 的重構方向。

## How

### 1. 測試準備

用 FFmpeg 從 `short_test.mp4` 抽取測試素材：

```bash
# 3 幀圖片（5s, 25s, 45s 各抽 1 幀）
runtime/ffmpeg -ss 5  -t 1 -i short_test.mp4 -update 1 -q:v 2 references/test_image_1.jpg
runtime/ffmpeg -ss 25 -t 1 -i short_test.mp4 -update 1 -q:v 2 references/test_image_2.jpg
runtime/ffmpeg -ss 45 -t 1 -i short_test.mp4 -update 1 -q:v 2 references/test_image_3.jpg
# 30 秒音訊（16kHz mono WAV）
runtime/ffmpeg -ss 5 -t 30 -i short_test.mp4 -vn -ac 1 -ar 16000 -y references/test_audio.wav
```

### 2. Server 啟動參數

```bash
vllm serve google/gemma-4-12B-it-qat-w4a16-ct \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-auto-tool-choice \
  --attention-backend TRITON_ATTN \
  --structured-outputs-config.enable_in_reasoning=True \
  --enforce-eager
```

`--structured-outputs-config.enable_in_reasoning=True` 是 vLLM 0.11.2+ 的 flag，讓 thinking mode 下仍能用 guided decoding。

### 3. 示範腳本結構

- `how_to_use_vllm_multimodal_via_openai_api.py` 內含四個 async task，用 `asyncio.gather` 並行執行
- Task 1: 純文字推論
- Task 2: 多圖片（3 張 base64 encoded）
- Task 3: 音訊（base64 encoded WAV）
- Task 4: 思考模式 + 結構化輸出（Pydantic → JSON Schema → guided decoding）

### 4. 測試結果

| Task | 模態 | 結果 | 說明 |
|------|------|------|------|
| Task 1 | 純文字 | ✅ 成功 | 寫出詩意的日落描述 |
| Task 2 | 圖片 | ✅ 成功 | 正確識別 Google Meet → IDE 的畫面轉換 |
| Task 3 | 音訊 | ✅ 成功 | 成功轉錄韓語 |
| Task 4 | 思考+JSON | ❌ 有 bug | reasoning 分離正常，但 thinking+structured output 並用時 JSON 被截斷 + 大量重複 `AI is a AI` |

### 5. Bug 診斷

做了三個控制變因測試：

| Test | 設定 | `reasoning` | `content` | 結果 |
|------|------|-----------|-----------|------|
| 1 | `response_format` only | `None` | ✅ JSON | 正常 |
| 2 | `enable_thinking` only | ✅ 有內容 | `None` | 正常 |
| 3 | **兩者並用** | `None` | ⚠️ JSON 截斷 + 重複 | **失敗** |

**診斷結論：**

- `enable_thinking=True` 單獨使用時，server 正確將 reasoning 放入 `message.reasoning`，`message.content` 為 `None`
- `response_format` 單獨使用時，server 正確導出 JSON 到 `message.content`
- 兩者並用時，vLLM server 沒有正確分離 reasoning。`reasoning` 是 `None`，`content` 包含 JSON 但被截斷且大量重複 `AI is a AI`，類似 guided decoding 崩潰

**可能原因：**
1. `--structured-outputs-config.enable_in_reasoning=True` flag 雖設了，但 vLLM nightly dev335 實作可能不穩
2. `max_tokens=256` 加上 thinking tokens 可能不夠用

## Follow-up

- [ ] 重啟 server 時確認 `--structured-outputs-config.enable_in_reasoning=True` 確實生效（用 `vllm serve --help` 確認參數名稱）
- [ ] 試 `max_tokens=1024` 看是否是 token 不夠的問題
- [ ] 確認 vLLM 版本是否有已知 bug（v0.22.1rc1.dev335）
- [ ] 如果 bug 無法解決，Task 4 可拆成兩階段：先 thinking，再用結果做 guided decoding

## References

- [how_to_use_vllm_multimodal_via_openai_api.py](./31_2026_06_11_human_strategy-vllm-server-api-pattern/how_to_use_vllm_multimodal_via_openai_api.py)
- [31_2026_06_11_human_strategy-vllm-server-api-pattern.md](./31_2026_06_11_human_strategy-vllm-server-api-pattern.md)（Server API 策略文件）
- [vLLM Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [vLLM Gemma 4 Usage Guide](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)

---

更新日期：2026-06-11
