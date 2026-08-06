---
created: 2026-07-29
author: agent
type: agent
status: final
tags: [speaker-diarization, voiceprint, voicetag, resemblyzer, pyannote]
---

# Speaker Diarization 聲紋識別工具鏈调研

## What

針對「使用參考音訊（聲紋）分離特定人聲音、建立人聲館偵測誰在何時說話」的需求，蒐集 pyannote 生態圈的完整工具鏈資訊，評估商用可行性。

## Why

專案需要 Speaker Identification 能力（不僅是匿名標籤 SPEAKER_00/01，而是能匹配已知說話人身份），且需確保所有依賴元件可商用。

## How

### 兩種實現途徑

| 途徑 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **pyannoteAI 雲端 API** | 官方提供的 Voiceprint → Identification 雲端流程 | 完整支援、簡單上線 | 需 API Key、付費計費、離線不可用 |
| **voicetag 本地方案** | 開源 Python 庫，包裝 pyannote.audio + resemblyzer | 完全離線、免費、CLI 支援 | 需自行維護 |

### 本地 Pipeline 架構

1. **voicetag** 呼叫 pyannote.audio 做語音分段與匿名標籤
2. **resemblyzer** 對每個分段提取 256 維 voice embedding
3. **Cosine Similarity** 比對區段 embedding 與已註冊的聲紋資料庫
4. 可選：搭配 Whisper / OpenAI / Groq 做語音轉文字，輸出「誰說了什麼」

### 進階擴充（社群實踐）

- **FAISS 向量搜尋**：當人聲館規模擴大時，用 FAISS 加速相似度比對（1M 向量 0.05 秒）
- **Retrieve & Rerank 模式**：第一層 FAISS 粗檢 → 第二層 cross-encoder 精排 → 第三層文字融合驗證
- **SpeechBrain ECAPA** 模型作為替代嵌入提取方案

### 許可證彙整

| 元件 | 許可證 | 商用 | 條件 |
|------|--------|:----:|------|
| voicetag | MIT | ✅ | 保留版權聲明 |
| Resemblyzer | Apache 2.0 | ✅ | 保留版權與許可證 |
| SpeechBrain ECAPA | Apache 2.0 | ✅ | 同上 |
| pyannote 模型 | CC-BY-4.0 | ✅ | 需適當歸 Attribution |

**結論：所有元件均可商用，無限制性授權。**

## Follow-up

- 決定採用雲端 API 還是本地 voicetag 方案
- 若選 voicetag，需安裝並測試實際效能
- 評估參考音訊的收集策略與數量需求

## References

- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)
- [pyannote 聲紋識別教學](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- [pyannote Identify API](https://docs.pyannote.ai/api-reference/identify)
- [Resemblyzer GitHub](https://github.com/resemble-ai/Resemblyzer)
- [SpeechBrain ECAPA 模型](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- [Speaker Diarization of Known Speakers Discussion](https://github.com/pyannote/pyannote-audio/discussions/1667)
- [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)