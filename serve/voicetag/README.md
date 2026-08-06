# VoiceTag 服務

Speaker identification service — 使用官方 [voicetag](https://github.com/Gr122lyBr/voicetag) 套件，回答「誰在何時說話」。

## 架構

```
serve/voicetag/
├── api/
│   ├── __init__.py
│   ├── main.py          # FastAPI app — /identify, /health
│   ├── models.py         # Pydantic request/response models
│   └── service.py        # Business logic layer
├── voicetag_core.py      # Core inference wrapper (model lifecycle)
├── server.py             # uvicorn entry point
├── pyproject.toml         # Dependencies
└── .venv/                # Virtual environment
```

## 前置條件

1. **HuggingFace Token**（用於 pyannote 語音分割模型）：

```bash
export HF_TOKEN="hf_your_token_here"
```

或建立於 [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)。

需接受以下模型授權：
- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
- [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)

2. **GPU（建議）**：CUDA 或 MPS 可顯著加速處理。

## 快速開始

### CLI 推理

```bash
# 基本推理（從專案根目錄執行）
serve/voicetag/.venv/bin/python workflows/voicetag.py test-audio/2026_07_21_test.mp3

# 儲存 JSON 輸出
serve/voicetag/.venv/bin/python workflows/voicetag.py test-audio/2026_07_21_test.mp3 -o output/voicetag/result.json

# 使用 CPU（較慢）
serve/voicetag/.venv/bin/python workflows/voicetag.py test-audio/2026_07_21_test.mp3 --device cpu

# 指定 speaker profiles
serve/voicetag/.venv/bin/python workflows/voicetag.py test-audio/2026_07_21_test.mp3 --profile output/voicetag/profiles.json
```

### HTTP API

```bash
# 啟動伺服器（從專案根目錄）
serve/voicetag/.venv/bin/python serve/voicetag/server.py
```

```bash
# 健康檢查
curl http://localhost:8001/health

# 推理
curl -X POST http://localhost:8001/identify \
  -H "Content-Type: application/json" \
  -d '{
    "audio_path": "/absolute/path/to/audio.mp3",
    "profile_path": "/path/to/profiles.json",
    "threshold": 0.75
  }'
```

### Python 程式碼

```python
from workflows.voicetag import identify_audio

result = identify_audio(
    audio_path="test-audio/2026_07_21_test.mp3",
    device="cuda:0",
    hf_token="hf_token_here",
    output_json="result.json",
)

for seg in result["segments"]:
    print(f"{seg['speaker']}: {seg['start']:.1f}s - {seg['end']:.1f}s (confidence: {seg['confidence']:.2f})")
```

## 輸出格式

```json
{
  "audio_path": "test-audio/2026_07_21_test.mp3",
  "audio_duration": 120.5,
  "num_speakers": 3,
  "processing_time": 45.2,
  "segments": [
    {
      "type": "SPEAKER",
      "start": 0.0,
      "end": 4.2,
      "duration": 4.2,
      "speaker": "Christie",
      "confidence": 0.92
    },
    {
      "type": "SPEAKER",
      "start": 4.5,
      "end": 8.1,
      "duration": 3.6,
      "speaker": "Mark",
      "confidence": 0.87
    },
    {
      "type": "OVERLAP",
      "start": 10.0,
      "end": 10.5,
      "duration": 0.5,
      "speakers": ["Christie", "Mark"],
      "speaker": "OVERLAP"
    }
  ]
}
```

## 依賴

| 元件 | 版本 | 用途 |
|------|------|------|
| voicetag | >=0.2.0 | 主庫（官方） |
| pyannote.audio | >=3.1 | 語音分割 |
| resemblyzer | >=0.1.3 | 聲紋 embedding |
| torch | >=2.0 | Deep learning 框架 |
| fastapi | >=0.115 | HTTP API |
| uvicorn | >=0.34 | ASGI server |

## 長音訊支援

VoiceTag 內建支援長音訊（數分鐘至數小時），不需要額外分塊。

- **底層機制**：`pyannote/speaker-diarization-3.1` 使用 30s sliding window with 15s stride
- **我們的實作**：直接傳檔案路徑給 voicetag，由 pyannote 自動處理分段
- **MP3 支援**：透過 librosa 轉 WAV（soundfile 無法解碼 MP3）
- **無需 padding**：不再需要手動對齊 chunk boundary
- **準確時間戳**：`audio_duration` 覆蓋為原始檔案實際長度

這表示你可以直接處理 5 分鐘、10 分鐘甚至更長的音訊檔案，voicetag 會自動處理所有分段與過渡。

## 與現有模組的關係

- **獨立模組**：`serve/voicetag` 與 `serve/sam-audio`、`serve/quark-audio` 完全獨立
- 無共享狀態、無 shared venv、無共享依賴
- 各模組可獨立啟動/停止