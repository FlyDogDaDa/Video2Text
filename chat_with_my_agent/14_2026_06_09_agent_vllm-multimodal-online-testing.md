---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm, multimodal, openai-sdk, compressed-tensors, bug, gemma4-vision]
---

# vLLM 多模態線上測試：文字 ✅ 圖片 ❌ 影片 ❌

## What

測試 vLLM server（OpenAI 相容 API）如何透過 OpenAI SDK 處理圖片、影片、音訊輸入。

**結論：**
- 純文字 ✅ 正常
- 圖片 ❌ 500 error：`'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'`
- 影片 ❌ vLLM stable 不支援

## 測試結果

### 純文字 ✅

```python
from openai import OpenAI
client = OpenAI(base_url='http://localhost:8746/v1', api_key='EMPTY')

r = client.chat.completions.create(
    model='google/gemma-4-12B-it-qat-w4a16-ct',
    messages=[{'role': 'user', 'content': 'say hi'}],
    max_tokens=8
)
# Output: "Hi there! How can I help you" ✅
```

### 圖片 ❌ 500 Internal Server Error

```python
import base64
from openai import OpenAI

client = OpenAI(base_url='http://localhost:8746/v1', api_key='EMPTY')

# 讀取本地圖片並 base64 encode
with open('test_image.jpg', 'rb') as f:
    base64_image = base64.b64encode(f.read()).decode('utf-8')

r = client.chat.completions.create(
    model='google/gemma-4-12B-it-qat-w4a16-ct',
    messages=[{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': 'describe this image in detail'},
            {'type': 'image_url', 'image_url': {
                'url': f'data:image/jpeg;base64,{base64_image}'
            }}
        ]
    }],
    max_tokens=64
)
# Error code: 500
# 'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'
```

### 影片 ❌

- OpenAI API `video_url` 格式在 vLLM stable v0.22.1 不支援
- 需要 custom vLLM branch

## 嘗試修復

### `--limit-mm-per-prompt` 重啟

嘗試加入 `--limit-mm-per-prompt '{"image": 4, "audio": 1, "video": 1}'` 重新啟動 vLLM server，但 **沒能解決 `num_soft_tokens` 錯誤**。

這錯誤是 vLLM 內部 `Gemma4UnifiedVisionConfig` 在 `compressed-tensors` 量化下的相容性問題，不在 `limit-mm-per-prompt` 的處理範圍內。

## 結論

| 模態 | 狀態 | 說明 |
|------|------|------|
| 純文字 | ✅ | 正常運作 |
| 圖片 | ❌ | `'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'` |
| 音訊 | ❌ | 未測試（Gemma-4 12B 無 audio encoder） |
| 影片 | ❌ | vLLM stable 不支援 |

**限制原因：** `compressed-tensors` 量化與 Gemma-4 vision 在 vLLM v0.22.1 不兼容。

## 可能的解決方向

1. **升級 vLLM nightly**：可能修復 `num_soft_tokens` bug，但可能破壞 `TRITON_ATTN`
2. **改用 HuggingFace Transformers**：離線推理，不用 vLLM
3. **先跑通文字流程**：用文字 API 做其他功能，等 vision bug 修復

## References

- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [vLLM Chat Completions API](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)
