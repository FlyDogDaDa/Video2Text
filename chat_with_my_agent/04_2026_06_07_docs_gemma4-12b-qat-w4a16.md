---
created: 2026-06-07
author: Human
type: docs
status: final
tags: [gemma4, vllm, quantization, video2text, inference]
---

# Gemma 4 12B IT QAT w4a16 — vLLM 最佳化權重模型評估

## What

研究並紀錄 `google/gemma-4-12B-it-qat-w4a16-ct` 模型規格、QAT 量化架構、以及對 Video2Text 專案的適配性分析。

## Why

Video2Text 系統需要一個能夠同時處理 **視覺** 與 **音訊** 輸入的 LLM。Gemma 4 12B 是 Google DeepMind 最新的 multimodal 模型家族成員，提供 QAT（Quantization-Aware Training）的 compressed-tensors 格式，可與 vLLM 原生整合。評估其是否適合部署於我們的推論環境。

## How

### 模型基本資訊

| 屬性 | 數值 |
|------|------|
| 模型名稱 | `google/gemma-4-12B-it` |
| 量化格式 | QAT w4a16（compressed-tensors） |
| 權重總引數 | 11.95B（Dense 架構） |
| 圖層數 | 48 |
| 上下文視窗 | 256K tokens |
| 詞彙表大小 | 262K |
| 支援語言 | 140+ 語言 |
| 支援模態 | **Text + Image + Audio**（音訊僅 E2B/E4B/12B 支援） |
| 授權 | Apache 2.0 |
| Hugging Face 下載量（月） | 77,487 |

### 量化格式：QAT w4a16（compressed-tensors）

此模型提供四種 QAT 檢查點格式：

| 格式 | 說明 | 適合場景 |
|------|------|---------|
| **Q4_0 非量化** | Half-precision weights from QAT pipeline | 自定義編譯與研究 |
| **GGUF（Q4_0）** | 免部署格式 | 廣泛生態系相容（llama.cpp 等） |
| **Mobile-optimized（wNa8o8）** | 自訂 schema，2-bit 解碼層 | 行動裝置部署 |
| **Compressed Tensors（w4a16）** | QAT checkpoints 序列化為 compressed-tensors | **vLLM 原生最佳化推論** |

w4a16 的含義：weights 4-bit、activations 16-bit。這種混合量化在維持接近 BF16 品質的同時，大幅降低 VRAM 需求。

**對 Video2Text 的意義：** vLLM 已原生支援 compressed-tensors 格式，意味著我們可以直接使用此模型，無需額外的格式轉換或後處理。

### 架構特色：Unified 解碼器

Gemma 4 12B Unified 的「Unified」指的是其 **encoder-free 架構**：

- 傳統模型使用專屬編碼器（encoder）處理多模態資料，再傳入 LLM
- Gemma 4 12B **完全移除了編碼器**，直接透過輕量級線性層將原始圖片 patch 與音訊波形投射到 LLM 的 embedding space
- 所有模態直接進入單一 decoder-only transformer
- 降低多模態延遲，允許整個模型一次訓練完畢

### 支援的模態與限制

| 模態 | 支援 | 限制 |
|------|------|------|
| Text | ✅ | 256K tokens |
| Image | ✅ | 任意寬高比與解析度，token budget 70-1120 |
| Video | ✅ | 最多 60 秒（1 FPS 抽幀） |
| **Audio** | ✅ | 最多 **30 秒**，僅 E2B/E4B/12B 支援 |

### Benchmark 表現

| Benchmark | Gemma 4 12B Unified | Gemma 4 31B | Gemma 3 27B |
|-----------|---------------------|-------------|-------------|
| MMLU Pro | 77.2% | 85.2% | 67.6% |
| AIME 2026 | 77.5% | 89.2% | 20.8% |
| LiveCodeBench v6 | 72.0% | 80.0% | 29.1% |
| GPQA Diamond | 78.8% | 84.3% | 42.4% |
| **MMMLU（多模態）** | **83.4%** | 88.4% | 70.7% |
| **Vision MMMU Pro** | **69.1%** | 76.9% | 49.7% |
| 音訊 CoVoST | 38.5%* | - | - |
| 音訊 FLEURS | 0.069* | - | - |

\* Excluding Chinese language

### vLLM 部署關鍵引數

| 引數 | 建議值 |
|------|--------|
| GPU | 1x H200 / A100 / MI300X |
| Tensor Parallel | TP=1 |
| 溫度 | 1.0 |
| top_p | 0.95 |
| top_k | 64 |
| 圖形 token budget | 280（影片理解推薦低值） |

### Thinking Mode（推理模式）

Gemma 4 內建 step-by-step 推理模式，透過控制 token 觸發：

- **啟用思考**：系統提示開頭加入 `<|think|>`
- **停用思考**：移除該 token
- 思考模式下的輸出結構：`<|channel>thought\n[Internal reasoning]<channel|>[Final answer]`

此功能對於 Video2Text 的 **複雜場景理解**（如因果分析、跨視窗事件關聯）尤其重要。

### 圖形 Token Budget

Gemma 4 支援視覺化 token 預算控制：

| Budget | 適用場景 |
|--------|---------|
| 70, 140 | 分類、標題、**影片理解（低解析度）** |
| 280, 560 | 一般視覺理解 |
| 1120 | OCR、檔案解析、小文字辨識 |

**對 Video2Text 的建議：** 影片理解場景應使用 **70-280** 的低 token budget，以平衡解析度與推理速度。

## Follow-up

- [ ] 評估我們的 GPU 硬體是否足以部署 12B QAT w4a16 模型（需約 6-8GB VRAM，量化後）
- [ ] 驗證 vLLM 版本是否支援 compressed-tensors 格式（目前 pyproject.toml 使用 vllm>=0.22.1）
- [ ] 測試 audio 30 秒限制是否足夠 Video2Text 的 slice 大小（目前設計 30 秒視窗，正好在邊緣）
- [ ] 考慮是否使用 thinking mode 來提升複雜場景的理解能力
- [ ] 比較 Gemma 4 12B 與更大模型（26B A4B、31B）在 VRAM vs 品質上的 trade-off

## References

- [Hugging Face — google/gemma-4-12B-it-qat-w4a16-ct](https://huggingface.co/google/gemma-4-12B-it-qat-w4a16-ct)
- [01_2026_06_07_human_video2text-system-design.md](./01_2026_06_07_human_video2text-system-design.md) — 系統設計（30 秒視窗、音訊 mono 混音）
- [pyproject.toml](../pyproject.toml) — vLLM 依賴版本
