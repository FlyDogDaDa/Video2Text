---
created: 2026-07-22
author: agent
type: agent
status: planning
tags: [execution-plan, microservice, fastapi, sam-audio, serve-folder]
---

# SAM-Audio 微服務執行計畫

## 概要

制定 SAM-Audio 分離模組的 FastAPI 微服務架構，採「預先存放 + URL」模式處理大檔案，原始模組保持無狀態、輸出路徑由使用者自定。

## 已完成事項

### 模組實作
- ✅ `modules/sam_audio.py` — 原始分離模組實作
  - `separate_by_anchor(audio, anchors, description="")` — 唯一公開函式
  - 模組級模型快取（一次性載入，長期佔用 GPU）
  - 回傳 `SeparationResult { speaker: Path, residual: Path }`

- ✅ 測試 `tests/test_layer3_sam_audio.py` — 15 項測試
  - 9 項通過（SeparationResult、SamAudioConfig、cfg 整合）
  - 6 項跳過（需要 GPU 環境，待就緒後執行）

- ✅ 設定 `profiles/default.yaml` — 新增 `sam_audio` section
  - `model_name`, `device` 欄位

### 依賴環境
- ✅ `torch`, `torchaudio` — 已安裝
- ✅ `sam-audio` — 從 GitHub 安裝成功
- ✅ GPU 環境 — 3 張 NVIDIA 卡（RTX A2000, 5070, 5060 Ti）
- ⚠️ `huggingface_hub` 版本相容性問題
  - v1.x 版 `from_pretrained()` 改變 API
  - 暫時降級到 `0.20.x` 版解決

## 待實作事項

### 1. 目錄結構建立

```
Video2Text/
├── serve/                # 微服務目錄（新增）
│   ├── sam-audio/        # SAM-Audio 獨立服務
│   │   ├── pyproject.toml
│   │   ├── server.py     # uvicorn 啟動點
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── main.py   # FastAPI app + 端點
│   │       ├── models.py # 請求/回應 Pydantic 模型
│   │       └── service.py  # 包裝原始模組
```

### 2. 修改原始模組 `modules/sam_audio.py`

新增輸出路徑參數，讓使用者自訂：

```python
def separate_by_anchor(
    audio: Path,                    # 輸入路徑（使用者提供）
    anchors: list[list],
    description: str = "",
    speaker_output: Path = None,    # 可選，使用者自定
    residual_output: Path = None,   # 可選，使用者自定
) -> SeparationResult:
    # 預設路徑：{audio.stem}_speaker.wav
    if speaker_output is None:
        speaker_output = audio.parent / f"{audio.stem}_speaker.wav"
    if residual_output is None:
        residual_output = audio.parent / f"{audio.stem}_residual.wav"
    
    # 執行分離，寫入指定路徑
    ...
    
    return SeparationResult(
        speaker=speaker_output,
        residual=residual_output,
    )
```

### 3. 建立服務層

#### `serve/sam-audio/api/models.py`

```python
from pydantic import BaseModel, Field
from typing import List

class SeparateRequest(BaseModel):
    audio_path: str             # 輸入音軌路徑（絕對）
    anchors: List[List]         # 時間區間
    description: str = ""       # 可選文字提示
    speaker_output: str = ""    # 可選，自定輸出
    residual_output: str = ""   # 可選，自定輸出

class SeparateResponse(BaseModel):
    speaker: str                # 回傳路徑
    residual: str               # 回傳路徑
    status: str = "done"        # 已完成

class HealthResponse(BaseModel):
    status: str = "ok"
    gpu_available: bool
    gpu_count: int
```

#### `serve/sam-audio/api/service.py`

```python
from pathlib import Path
from api.models import SeparateRequest, SeparateResponse
from modules.sam_audio import separate_by_anchor

class SamAudioService:
    def separate(self, req: SeparateRequest) -> SeparateResponse:
        audio = Path(req.audio_path)
        speaker_out = Path(req.speaker_output) if req.speaker_output else None
        residual_out = Path(req.residual_output) if req.residual_output else None
        
        result = separate_by_anchor(
            audio=audio,
            anchors=req.anchors,
            description=req.description or "",
            speaker_output=speaker_out,
            residual_output=residual_out,
        )
        
        return SeparateResponse(
            speaker=str(result.speaker),
            residual=str(result.residual),
            status="done",
        )
```

#### `serve/sam-audio/api/main.py`

```python
from fastapi import FastAPI, HTTPException
from api.models import SeparateResponse, HealthResponse
from api.service import SamAudioService

app = FastAPI(title="SAM-Audio Service", version="0.1.0")
service = SamAudioService()

@app.post("/separate", response_model=SeparateResponse)
async def separate(req: SeparateRequest):
    try:
        return service.separate(req)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Input audio not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", response_model=HealthResponse)
async def health():
    import torch
    return {
        "status": "ok",
        "gpu_available": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }
```

#### `serve/sam-audio/server.py`

```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
```

### 4. `pyproject.toml`

```toml
# serve/sam-audio/pyproject.toml
[project]
name = "sam-audio-server"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "pydantic",
    "torch",
    "torchaudio",
]
```

## 架構設計決策

### 檔案傳輸：預先存放 + URL

| 選項 | 選擇 | 原因 |
|------|------|------|
| 檔案上傳同步 | ❌ | 大檔案 timeout |
| **預先存放 + URL** | **✅** | 可斷點續傳、支援重試、API 只讀取 |
| 非同步任務 | ❌ | 複雜度高，暂時不需要 |

**客戶端流程：**
```bash
# 1. 上傳（可斷點續傳）
cp video.mp4 /data/audio/video.mp4

# 2. 呼叫 API
curl -X POST http://localhost:8000/separate \
  -H "Content-Type: application/json" \
  -d '{"audio_path": "/data/audio/video.mp4", ...}'

# 3. 回傳路徑，客戶端自己檢查檔案
ls -lh /data/output/video_speaker.wav
```

### 輸出路徑：使用者自定

- 不封裝輸出目錄管理
- 回傳路徑，由客戶端自己檢查檔案是否存在/完成
- 預設路徑：`{audio.stem}_speaker.wav`（可覆蓋）

### GPU 記憶體管理

- 服務啟動時載入一次（module-level cache）
- 長期佔用 GPU 記憶體（合理，因為服務會持續運行）
- 不支援按需卸載（未來可加）

### 原始模組：無狀態、獨立

- 原始 `modules/sam_audio.py` 保持純函式、無狀態
- 不處理上傳/下載/路徑管理
- 服務層包裝，處理外部交互

## 執行順序

1. **建立 `serve/sam-audio/` 目錄結構**
2. **修改 `modules/sam_audio.py`** — 加入 `speaker_output`, `residual_output` 參數
3. **建立 `serve/sam-audio/api/models.py`** — Pydantic 請求/回應模型
4. **建立 `serve/sam-audio/api/service.py`** — 服務層包裝
5. **建立 `serve/sam-audio/api/main.py`** — FastAPI 端點
6. **建立 `serve/sam-audio/server.py`** — uvicorn 啟動
7. **建立 `serve/sam-audio/pyproject.toml`** — 依賴管理
8. **測試** — 手動啟動 uvicorn，用 curl 測試端點

## 依賴安裝順序

```bash
# 在 serve/sam-audio/ 目錄下
uv add fastapi uvicorn[standard] pydantic torch torchaudio
```

## 啟動方式

```bash
# 手動啟動
cd serve/sam-audio
uv run python server.py

# 或直接 uvicorn
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 參考檔案

- `chat_with_my_agent/47_2026_07_21_agent_sam-audio-module-design.md` — 原始模組設計
- `modules/sam_audio.py` — 原始模組實作
- `tests/test_layer3_sam_audio.py` — 行為測試