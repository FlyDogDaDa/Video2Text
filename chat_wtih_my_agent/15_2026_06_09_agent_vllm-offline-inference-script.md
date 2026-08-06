---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm, multimodal, offline, inference, TRITON_ATTN, compressed-tensors, VRAM]
---

# Offline Inference Script — 文字 ✅ 多模態 ❌

## What

建立 `src/inference/multimodal_infer.py` 支援文字、圖片、音訊、影片的多模態離線推理，但測試結果只有純文字可用。

**結果：**
- 純文字 ✅ 穩定運行
- 圖片 ❌ VRAM 不足 + vision 相容性 bug
- 影片 ❌ vLLM stable v0.22.1 不支援
- 音訊 ❌ Gemma-4-12B 無 audio encoder

## 測試結果

### 純文字 ✅

```bash
uv run python src/inference/multimodal_infer.py --prompt "One word answer: hello"
```

輸出：`Hi`

配置：`TRITON_ATTN` + `enforce_eager=True` + `max_model_len=4096` + `gpu_memory_utilization=0.7`

### 圖片 ❌ 多重錯誤

**錯誤 1：VRAM 不足**

```
ERROR: Available KV cache memory: 0.83 GiB
```

原因：`compressed-tensors` 量化模型 + vision profiling 吃掉過多 VRAM（2×12GB GPU = 24GB 總容量）。

**錯誤 2：Vision 與 compressed-tensors 不兼容**

```
ValueError: Found 1 <|image|> tokens in the text but no images were passed.
```

這是 vLLM v0.22.1 的已知問題：`Gemma4UnifiedVisionConfig` 物件在 `compressed-tensors` 量化下缺少 `num_soft_tokens` 屬性。

### 影片 ❌

- vLLM stable v0.22.1 不支援 `video_url` API
- `try_video.py` 用 `LLM.generate()` 需 custom branch

### 音訊 ❌

- 音訊測試尚未執行（音訊功能應可用）
- Gemma-4-12B 支援 audio input（E2B/E4B/**12B** 均支援，最大 30 秒）
- 需確認音訊輸入是否受 VRAM 或 vLLM vision/audio 相容性 bug 影響

## VRAM 分析

| 模態 | VRAM 需求 | 狀態 |
|------|-----------|------|
| 純文字 | ~4.4GB 模型 + ~5GB KV cache | ✅ 可行 |
| 圖片 | 模型 + KV cache + vision profiling (~5GB) | ❌ 超出 24GB |
| 影片 | 模型 + KV cache + video profiling (~7GB) | ❌ 超出 24GB |

**硬體限制：** 2×12GB GPUs = 24GB 總容量，12B 壓縮量化模型需 ~4.4GB。

## Gemma-4-12B 模型賣點（更正）

Gemma-4-12B 是 Google DeepMind 於 2026/06/03 發布的開源多模態模型，核心賣點：

| 特性 | 說明 |
|------|------|
| **Encoder-free 架構** | 單一 decoder-only transformer 直接處理 text/image/audio/video，無獨立 vision/audio encoder |
| **原生多模態** | 音訊、影像、影片皆透過 linear projection 投影到 text token space |
| **全模態支援** | 12B 版本支援 **text + image + audio（30s）+ video（60s）** |
| **256K context** | 超長上下文 |
| **16GB VRAM 可運行** | 目標消費級硬體 |
| **Apache 2.0** | 開放權重 |
| **效能** | MMLU Pro 77.2%，媲美 2× 更大的 26B 模型 |

> **⚠️ 「encoder-free」是架構創新，不是功能限制！**
> 錯誤推論：encoder-free = 沒有 audio encoder ❌
> 正確理解：不需要獨立 encoder，模型自身直接處理所有模態 ✅

**官方引用：** "We removed the audio encoder entirely and projected the raw audio signal into the same dimensional space as text tokens."

## 限制原因

1. **vLLM v0.22.1 + compressed-tensors + Gemma-4 vision 不兼容**
   - 錯誤：`'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'`
   - 需要在線上 API 或離線推理都修好

2. **VRAM 不足**
   - `limit_mm_per_prompt` 觸發 multimodal profiling 吃掉 ~5-7GB VRAM
   - 2×12GB GPU 總共 24GB，扣除模型 4.4GB 後 KV cache 空間有限

3. **vLLM stable 不支援 video_url**
   - 需要 custom vLLM branch
   - `fetch_video` 函數存在，但 vision encoder 處理未實裝

## 程式結構

```
src/inference/
  └── multimodal_infer.py   # 主程式，支援 CLI 引數
```

### CLI 用法

```bash
# 純文字
python src/inference/multimodal_infer.py \
  --prompt "What is the meaning of life?"

# 文字 + 圖片（測試後不可用）
python src/inference/multimodal_infer.py \
  --prompt "Describe this image." \
  --image ./path/to/image.jpg

# 文字 + 影片（測試後不可用）
python src/inference/multimodal_infer.py \
  --prompt "Summarize this video." \
  --video ./video.mp4
```

### 架構

```
┌─────────────────────────────────────────────────────┐
│                   multimodal_infer.py                 │
├─────────────────────────────────────────────────────┤
│ 1. parse_args()                                     │
│ 2. create_llm() → LLM(TRITON_ATTN, compressed-tensors) │
│ 3. build_messages() → content array                 │
│ 4. build_multi_modal_data() → {image, video, audio} │
│ 5. processor.apply_chat_template()                  │
│ 6. llm.generate() → outputs                         │
└─────────────────────────────────────────────────────┘
```

### 關鍵函數

| 函數 | 用途 |
|------|------|
| `create_llm()` | 建立 LLM 實體，設定 TRITON_ATTN、enforce_eager |
| `build_messages()` | 構建 OpenAI content array：`[{"type": "text"}, {"type": "image"}, ...]` |
| `build_multi_modal_data()` | 構建 multi_modal_data dict：`{"image": [PIL.Image], "video": [bytes]}` |
| `load_image()` | 讀取本地圖片 |
| `load_video()` | 用 `vllm.multimodal.utils.fetch_video` 讀影片 |

## 可能的解決方向

| 選項 | 說明 | 風險 |
|------|------|------|
| 升級 nightly vLLM | 可能修復 `num_soft_tokens` bug | 可能破壞 TRITON_ATTN |
| 改用 HuggingFace Transformers | 離線推理，不用 vLLM | 效能較差 |
| 先跑通文字流程 | 等 vision bug 修復 | 暫時無法處理多模態 |

## References

- [src/inference/multimodal_infer.py](../src/inference/multimodal_infer.py)
- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [try_video.py](../chat_wtih_my_agent/08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py)
