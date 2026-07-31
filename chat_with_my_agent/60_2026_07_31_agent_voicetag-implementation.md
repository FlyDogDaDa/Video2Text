---
created: 2026-07-31
author: Vincent
type: agent
status: implemented
tags: [voicetag, speaker-diarization, identification, pyannote, resemblyzer, CUDA]
---

# 實作 VoiceTag 說話人識別模組

## What

建立獨立的 VoiceTag 說話人識別服務模組，包含：
- `serve/voicetag/` — FastAPI 伺服器與核心推理封裝
- `workflows/voicetag.py` — CLI/程式碼入口
- 使用官方 [voicetag](https://github.com/Gr122lyBr/voicetag) Python 套件（v0.2.0）

支援「誰在何時說話」的 JSON 輸出。

## Why

專案需要 Speaker Identification 能力（不僅是匿名標籤，而是匹配已知說話人身份）。`quark-audio` 做 TSE 後需要進一步識別說話人身份。

## How

### 1. 建立 `serve/voicetag/` 目錄結構

```
serve/voicetag/
├── api/
│   ├── __init__.py
│   ├── main.py          # FastAPI app — /identify + /health
│   ├── models.py         # Pydantic request/response models
│   └── service.py        # 商業邏輯層
├── voicetag_core.py      # 核心推理封裝（模型生命周期）
├── server.py             # uvicorn 進入點（port 8001）
├── pyproject.toml        # 依賴設定
├── .env                  # HF_TOKEN 設定
└── .venv/               # Python 3.12 虛擬環境
```

### 2. 安裝依賴

- `uv venv serve/voicetag/.venv` — 建立 Python 3.12 虛擬環境
- `uv pip install` voicetag[ml], fastapi, uvicorn, python-dotenv, librosa
- 修復 Python 3.12 相容性：`llvmlite>=0.42`, `numba>=0.58`

### 3. 核心實作

**`voicetag_core.py`**：
- `identify()` — 音訊檔案 → DiarizationResult
- `health()` — 服務健康檢查
- `.env` 自動載入（python-dotenv）
- 音訊 padding workaround：pyannote 要求 chunk 為 10s @48kHz 整數倍，自動補齊

**`api/models.py`**：
- `IdentifyRequest` / `IdentifyResponse` — API 請求/回應
- `SpeakerSegment` / `OverlapSegment` — 分段結果

**`api/service.py`**：
- `VoiceTagService.identify()` — 商業邏輯
- 轉換 voicetag 結果 → API 格式

**`workflows/voicetag.py`**：
- `identify_audio()` — 端到端推理
- CLI 入口 + JSON 輸出

### 4. 測試結果

**GPU (cuda:0) 測試：**
```
音訊：test-audio/2026_07_21_test.mp3（120s）
GPU: 成功，processing_time: 9.6s
輸出：3 個 overlap segments（未註冊 speaker profile）
```

**HF Token 流程：**
- `.env` 設定 `HF_TOKEN`
- 需接受 3 個 pyannote 模型授權：
  - pyannote/speaker-diarization-3.1
  - pyannote/segmentation-3.0
  - pyannote/speaker-diarization-community-1

## Follow-up

- [ ] 註冊 speaker profile 後測試完整 identification
- [ ] 測試 API endpoint（`python serve/voicetag/server.py`）
- [ ] 評估不同音訊長度的效能
- [ ] 整合到主 pipeline

## References

- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)
- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py)
- [serve/voicetag/api/main.py](../../serve/voicetag/api/main.py)
- [workflows/voicetag.py](../../workflows/voicetag.py)
- [pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://hf.co/pyannote/segmentation-3.0)