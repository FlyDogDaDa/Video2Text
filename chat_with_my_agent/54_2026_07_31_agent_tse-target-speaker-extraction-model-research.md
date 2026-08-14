---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [tse, target-speaker-extraction, voiceprint, clearervoice, quarkaudio-unise, meanflow]
---

# TSE（Target Speaker Extraction）可商用模型調研

## What

系統性搜尋並比較可商用、本地執行的 Target Speaker Extraction 模型。採用「找到一個後再找更新更好的」策略，逐層遞進評估。

## Why

繼 Speaker Diarization（#53）之後，專案進一步需要「從多人混音中分離指定說話人」的能力——與 Diarization 的差異在於：Diarization 是識別「誰說了什麼」，TSE 是主動從混合音訊中提取特定說話人的完整音訊軌跡。

## How

### 搜尋方法論

每次找到一個候選模型後，主動搜尋「比它更新的」、「比它更好的」模型，確保不遺漏最新進展。

### 評估維度

| 維度 | 說明 |
|------|------|
| **授權** | 必須可商用（Apache 2.0 / MIT / BSD） |
| **本地執行** | 可離線部署，不需雲端 API |
| **TSE 支援** | 輸入參考音訊（enrollment），輸出目標說話人分離結果 |
| **預訓練權重** | 是否提供可直接使用的權重 |
| **成熟度** | 星數、commits、社群規模 |

### 搜尋軌跡

```
搜尋層級 1 → ClearerVoice-Studio（阿里, Apache 2.0, 4.3k⭐）
              ↓ 找更好的
搜尋層級 2 → QuarkAudio-UniSE（阿里通義, Apache 2.0, 484⭐, 2025.10）
              ↓ 找更新的
搜尋層級 3 → MeanFlow-TSE（哥倫比亞大學, MIT, Interspeech 2026, 26⭐）
              ↓ 找更新的
搜尋層級 4 → USEF-TSE（TASLP 2025, 無聲紋架構）
              ↓
搜尋層級 5 → WeSep（網易, MIT, 完整工具鏈）
```

### 排除專案（不可商用）

| 模型 | 排除原因 |
|------|----------|
| LauraTSE | CC BY-NC-SA 4.0（非商用） |
| FunCodec 權重 | CC-BY-NC-SA 4.0（非商用） |
| Amphion/Metis-TSE | 權重 CC-BY-NC-4.0（程式碼 MIT 但權重不可商用） |

### 最終候選比較

| 排名 | 模型 | 授權 | 發布 | 預訓練 | 成熟度 | 架構 |
|------|------|------|------|--------|--------|------|
| 🥇 | **ClearerVoice-Studio** | Apache 2.0 | 2024.11 | ✅ HuggingFace | 4.3k⭐, 332 commits | MossFormer / FRCRN |
| 🥈 | **QuarkAudio-UniSE** | Apache 2.0 | 2025.10 | ✅ HuggingFace | 484⭐, 92 commits | Decoder-only AR-LM + BiCodec |
| 🥉 | **MeanFlow-TSE** | MIT | 2025.12 | ❌ 需訓練 | 26⭐ | Flow Matching, One-Step |
| 4 | **WeSep** | MIT | 2024 | ⚠️ 需訓練 | 301⭐ | Conv-TASNet / Spex / tf-gridnet |
| 5 | **USEF-TSE** | — | 2024 | ❌ 需訓練 | 研究級 | Multi-head cross-attention |

### 技術細節彙整

#### ClearerVoice-Studio
- TSE 子任務：Audio-only（8kHz）、Audio-visual Face（16kHz）、Audio-visual Body（16kHz）、Neuro-steered EEG（16kHz）
- pip 安裝：`pip install clearvoice`
- 支援 Numpy 陣列輸入/輸出介面
- 內建 SpeechScore 評估工具

#### QuarkAudio-UniSE
- 兩階段推理：WavLM 特徵提取 → LM 自迴歸生成 token → BiCodec 重建波形
- 統一框架：一個模型處理 SE、SR、TSE、SS、VC、Audio Editing 等 8+ 任務
- 需手動下載 BiCodec（從 Spark-TTS-0.5B）+ WavLM-Large.pt
- 5 秒分段處理，enroll_duration 引數控制參考音訊長度

#### MeanFlow-TSE
- Flow Matching 生成式架構，單步推理（超低延遲）
- 在 Libri2Mix 上達到 SOTA SI-SDR/PESQ/eSTOI
- 支援 1-step / 5-step / 10-step 推理模式
- 無官方預訓練權重，需自行準備 Libri2Mix 資料訓練

## Follow-up

- 優先嘗試 QuarkAudio-UniSE 的 TSE 推理（若效果不佳則退回 ClearerVoice-Studio）
- QuarkAudio-UniSE 需先準備權重：
  1. 下載 BiCodec checkpoint（從 Spark-TTS-0.5B）
  2. 下載 WavLM-Large.pt
  3. 下載 UniSE pretrained weight（HuggingFace）
- 測試不同 enroll_duration 對分離品質的影響
- 比較兩者的 SI-SDR / PESQ 指標

## References

- [alibaba/unified-audio (QuarkAudio)](https://github.com/alibaba/unified-audio)
- [QuarkAudio-UniSE README](https://github.com/alibaba/unified-audio/blob/main/QuarkAudio-UniSE/README.md)
- [QuarkAudio/QuarkAudio-UniSE (HuggingFace)](https://huggingface.co/QuarkAudio/QuarkAudio-UniSE)
- [UniSE Paper (arXiv:2510.20441)](https://arxiv.org/abs/2510.20441)
- [DeepWiki: QuarkAudio-UniSE](https://deepwiki.com/alibaba/unified-audio/2-quarkaudio-unise)
- [DeepWiki: QuarkAudio-UniSE Inference](https://deepwiki.com/alibaba/unified-audio/2.4-inference)
- [rikishimizu/MeanFlow-TSE](https://github.com/rikishimizu/MeanFlow-TSE)
- [MeanFlow-TSE Paper (arXiv:2512.18572)](https://arxiv.org/abs/2512.18572)
- [wenet-e2e/wesep](https://github.com/wenet-e2e/wesep)
- [modelscope/ClearerVoice-Studio](https://github.com/modelscope/ClearerVoice-Studio)
- [USEF-TSE Paper (arXiv:2409.02615)](https://arxiv.org/abs/2409.02615)
- [AV_MossFormer2_TSE_16K (HuggingFace)](https://huggingface.co/alibabasglab/AV_MossFormer2_TSE_16K)