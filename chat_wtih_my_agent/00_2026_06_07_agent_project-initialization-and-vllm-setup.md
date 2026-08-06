---
created: 2026-06-07
author: Zed Agent
type: agent
status: final
tags: [project-setup, vllm, dependency-management]
---

# Project Initialization and vLLM Setup

## What

- 使用 `uv init` 初始化 Python 專案
- 新增 `vllm` 套件作為主要依賴
- 建立 `.agent` 資料夾並加入 `.gitignore`
- 撰寫專案描述檔案 `DESCRIPTION.md`

## Why

專案需要高吞吐量的 LLM 推論能力，vLLM 提供 PagedAttention、continuous batching 及最佳化的 CUDA kernels，適合 Video2Text 應用的模型推理需求。`.agent` 資料夾用於存放 agent 相關配置，不應納入版本控制。

## How

1. **專案初始化**：執行 `uv init` 建立標準 uv 專案結構，產生 `pyproject.toml`、`main.py`、`README.md`、`.python-version` 等檔案。

2. **安裝 vLLM**：執行 `uv add vllm`，自動解析並安裝 189 個相依套件，包含：
   - PyTorch 系列 (`torch`, `torchvision`, `torchaudio`)
   - CUDA 相關套件 (`cuda-core`, `nvidia-cudnn-*`, `triton`)
   - LLM 工具鏈 (`transformers`, `tokenizers`, `huggingface-hub`)
   - 其他間接相依 (`fastapi`, `uvicorn` 等為 vLLM 的傳遞相依，尚未決定是否使用)

3. **建立 .agent 資料夾**：使用 `create_directory` 建立 `Video2Text/.agent/`，並在 `.gitignore` 末尾新增 `.agent/` 規則。

4. **撰寫描述檔案**：建立 `DESCRIPTION.md` 記錄專案結構、技術棧、相依性分類及使用範例。

## Follow-up

- 確認系統有 NVIDIA GPU 與 CUDA 12+ 環境
- 規劃 Video2Text 的具體實作路徑
- 考慮新增其他相依套件（如影像處理、視訊編碼等）

## References

- [pyproject.toml](../pyproject.toml)
- [DESCRIPTION.md](../DESCRIPTION.md)
- [main.py](../main.py)
