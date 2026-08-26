---
date: 2026-08-14
topics: [target-diarization-research, stt-server-module, comparison]
status: research-complete
---

# TargetDiarization 研究與整合計畫

## 時間

2026-08-14

## 做了什麼

對外部專案 `jingzhunxue/TargetDiarization` 進行深度研究，與當前 Video2Text 專案進行全面比較，並評估將其作為 STT 伺服器模組整合進專案的可行性。

## 為什麼

Video2Text 目前的 `modules/` 目錄中，VAD、ASR、Clean、Summarize、VideoDesc 全部是 Stub，主流程 `workflow.py` 無法執行有意義的處理。需要一個成熟、完整的 STT 伺服器模組來填補這個缺口。

## 研究過程

使用 4 個 parallel sub-agents 從不同維度進行比較分析：

1. **架構分析**：TargetDiarization 整體架構、模組劃分、Pipeline 流程、設計模式
2. **Video2Text 深度分析**：microservice 結構、modules 實作狀態、voicetag 整合、配置管理
3. **音訊處理技術比較**：VAD、Diarization、Separation、ASR、Punctuation 各層面的技術選擇
4. **軟體工程實務比較**：程式碼風格、API 設計、Config 管理、Packaging、安全性

## 核心發現

### TargetDiarization 的優勢（Video2Text 欠缺的）

- **完整的音訊後處理管線**：MDX-Net 降噪 → MossFormer2 分離 → Apollo 修復 → Resemble 增強 → LUFS 標準化
- **VAD 實作**：FSMN-Monophone（中文最佳化）+ Silero VAD（streaming 用）
- **標點還原**：CT-Transformer 整合，ASR 後自動新增標點
- **Streaming 支援**：WebSocket 即時串流，VAD 緩衝 + 智慧觸發判斷
- **多 ASR 引擎**：Strategy Pattern 支援 6+ 引擎（Paraformer / Whisper / SenseVoice / 雲端 API）
- **雙層 Diarization**：CAM++ + Pyannote 3.1 + IoU 融合處理重疊區段
- **容錯設計**：多層 fallback，模型載入失敗不崩潰
- **即部署**：內建 FastAPI REST API + WebSocket + Gradio WebUI

### Video2Text 的優勢

- **Microservice 架構**：每個 AI 服務獨立（voicetag / sam-audio / vllm）
- **現代化工具鏈**：uv workspace + pyproject.toml + pydantic config
- **Type Hints 完整**：Python 3.12 現代化語法
- **多模態**：影片幀描述 + LLM 摘要（TargetDiarization 無此能力）
- **SAM-Audio**：Span Prompting 靈活性勝過 MossFormer2 固定 2-channel
- **vLLM 批次推理**：PagedAttention 高吞吐 ASR

### 完成度對比

| 面向 | TargetDiarization | Video2Text |
|---|---|---|
| 完整功能 | ✅ 可直接上線 | ⚠️ Microservices 完成，Modules 大部分 Stub |
| 架構成熟度 | 單一大類，緊密耦合 | Microservice 分離，易擴充套件 |
| 新手友好 | 快速上手 | 設定複雜 |

## 結論

TargetDiarization 是一個**功能完整、可直接部署的音訊處理工廠**，非常適合作為 Video2Text 的 STT 伺服器模組。

Video2Text 則是**架構優越但尚未蓋完的平臺**。兩者的技術棧有互補性——TargetDiarization 提供了 Video2Text 目前欠缺的所有核心音訊處理能力。

## 下一步

1. 切一個新分支 `feat/integrate-target-diarization`，專門負責整合
2. 將 TargetDiarization 作為 Video2Text 的 STT 微服務模組引入
3. 保留 Video2Text 的 microservice 架構優勢，同時補上音訊處理管線
4. 讓 `modules/asr.py`、`modules/vad.py` 等 stub 改用 TargetDiarization 的實作

## 參考

- [TargetDiarization GitHub](https://github.com/jingzhunxue/TargetDiarization)
- `modules/vad.py` — 目前 Stub，需改用 TargetDiarization FSMN-Monophone
- `modules/asr.py` — 目前 Stub，可改用 TargetDiarization Paraformer
- `workflow.py` — 目前空殼流程，整合後可完整運作
- [serve/voicetag/voicetag_core.py](../serve/voicetag/voicetag_core.py) — 目前唯一的完整 DIARIZATION 實作
