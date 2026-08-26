---
date: 2026-08-07
topic: fix-pyannote-environment
tags:
  - pyannote.audio
  - torch
  - dependency
  - gradio
---

# Fix pyannote.audio + torch CUDA environment

## What was done

- Upgraded `pyannote.audio` from 3.3.2 to 4.0.7 (latest stable)
- Switched `torch` from CPU-only 2.8.0 to CUDA 2.13.0+cu130
- Added `torchcodec`, `torchvision` with CUDA support
- Added `gradio` dependency (was missing from pyproject.toml)
- Fixed `.env` loading in `webuis/speech-to-text.py`
- Successfully ran end-to-end pipeline (diarization + STT)

## Why

`pyannote.audio` 3.x 依賴 `huggingface-hub>=0.13.0` 與 `torch>=2.0`，只設下界沒設上界，讓 `uv` 自動安裝了：
- `huggingface-hub` v1.0+（`use_auth_token` → `token` breaking change）
- `torch` v2.6+（`torch.load(weights_only=True)` 預設值改變）

這兩個 breaking change 都讓 3.x 的 pyannote 無法正常運作。

`pyannote.audio` 4.x 已修正 API（改用 `token=` 引數），但需要：
- `torchcodec` 讀音訊檔（3.x 用 `torchaudio`）
- `torchcodec` 需要 CUDA 版 PyTorch

## How

### 1. 修改 `webuis/pyproject.toml`

```toml
dependencies = [
    "gradio>=6.0",
    "huggingface-hub>=1.0",
    "pyannote-audio>=4.0",
    "pyyaml>=6.0.3",
    "torch>=2.13",
    "torchvision>=0.23",
    "torchcodec>=0.15",
    "voicetag[openai]>=0.2.0",
]

[tool.uv.sources]
torch = { index = "pytorch-cuda" }
torchaudio = { index = "pytorch-cuda" }
torchvision = { index = "pytorch-cuda" }

[[tool.uv.index]]
name = "pytorch-cuda"
url = "https://download.pytorch.org/whl/cu130"
explicit = true
```

關鍵：`[tool.uv.sources]` 強制 `torch/torchaudio/torchvision` 從 CUDA index 下載，避免 uv 選到 CPU 版。

### 2. 修復 `.env` 讀取

`webuis/speech-to-text.py` 加入了 `python-dotenv` 讀取 `.env`：

```python
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
```

### 3. 安裝

```bash
uv add gradio --project webuis
uv add python-dotenv --project webuis
uv sync --project webuis
```

## Follow-up

- 測試結果：0 segments detected（音訊檔可能沒有語音/或 diarization 引數需調整）
- 後續需確認：
  - 音訊檔是否有語音內容？
  - 是否需要先註冊 speaker reference audio？
  - HF token 許可權是否足夠下載 diarization model？

## References

- [webuis/pyproject.toml](webuis/pyproject.toml)
- [webuis/speech-to-text.py](webuis/speech-to-text.py)
- [webuis/.env](webuis/.env)