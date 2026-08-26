---
created: 2026-06-07
author: Agent
type: agent
status: final
tags: [sglang, gemma4, python-version, dependency-management]
---

# SGLang Installation for Gemma 4 Support

## What

- 安裝 SGLang（main branch）至 Video2Text 專案
- 設定 Python 版本為 3.12
- 移除 vLLM 依賴（與 SGLang 的 flashinfer-cubin 版本衝突）
- 建立測試環境確認 SGLang 和 Transformers 是否正常

## Why

SGLang 提供 Gemma 4 的完整支援，包括：
- 原生 encoder-free unified 12B 模型（PR #27167）
- 內建 reasoning/thinking mode
- 多模態輸入（text + image + video + audio）
- 與 Transformers main branch 的 Gemma 4 支援相容

專案選擇 SGLang 作為主要 LLM 推論框架，取代 vLLM（兩者因 flashinfer-cubin 版本衝突無法並存）。

## How

### 1. 環境清理

- 刪除舊 `.venv`
- 刪除 `.python-version`（原 3.12，但之前有人嘗試 pin 3.14）

### 2. Python 版本選擇

**Python 3.14 嘗試：** 設定 `requires-python = ">=3.14"` 並 `uv python pin 3.14`，但遇到：
- `cuda-tile` 無 cp314 wheel，SGLang 依賴無法解析

**Python 3.13 嘗試：** `uv python pin 3.13`，但 `outlines-core==0.1.26` 的 Rust 編譯失敗（`can't find Rust compiler`）。

**最終選擇 Python 3.12：** 所有依賴（cuda-tile、outlines-core）均有 cp312 wheel 可安裝。

### 3. 移除 vLLM

```bash
uv remove vllm
```

### 4. 安裝 SGLang

```bash
uv add 'sglang @ git+https://github.com/sgl-project/sglang.git#subdirectory=python'
```

安裝過程需要 Rust 編譯器（`outlines-core` 依賴 Rust crate）。系統已有 rustc 1.96.0，無需額外安裝。

### 5. 驗證

```
SGLang 0.5.6.post3.dev5962+ga07d813ec
PyTorch 2.11.0+cu130
Transformers 5.8.1
```

Transformers 5.8.1 已由 SGLang 依賴解析為 compatible version（與 main branch commit 1423d22f 相容），無需手動安裝 git version。

### 6. 檔案變更

- `pyproject.toml`：移除 `vllm>=0.22.1`，新增 `sglang` 至 `dependencies`，新增 `[tool.uv.sources]` 區段
- `.python-version`：更新為 `3.12`

## Results

### 安裝的套件（184 packages）

核心依賴：
| 套件 | 版本 | 說明 |
|------|------|------|
| sglang | 0.5.6.post3.dev5962+ga07d813ec | 從 main branch 建置 |
| sglang-kernel | 0.4.3 | SGLang 核心 kernel |
| torch | 2.11.0 | CUDA 13.0 |
| transformers | 5.8.1 | 與 Gemma 4 main 相容 |
| tokenizers | 0.22.2 | 支援 Gemma tokenizer |
| flashinfer-python | 0.6.12 | 推理加速 |
| compressed-tensors | 0.17.0 | 量化模型支援 |

### 與 vLLM 的版本衝突記錄

| 套件 | vllm==0.22.1 | sglang==0.5.6 |
|------|--------------|---------------|
| flashinfer-cubin | 0.6.11.post2 | 0.6.12 |
| 結果 | ❌ 衝突，無法並存 | |

## Follow-up

- [ ] 測試 SGLang 能否成功 load Gemma 4 12B 模型
- [ ] 驗證多模態輸入（image + audio）是否正常工作
- [ ] 測試 thinking mode 輸出格式
- [ ] 更新 system design 檔案中的推論框架說明

## References

- [pyproject.toml](../pyproject.toml)
- [01_2026_06_07_human_video2text-system-design.md](./01_2026_06_07_human_video2text-system-design.md)
- [04_2026_06_07_docs_gemma4-12b-qat-w4a16.md](./04_2026_06_07_docs_gemma4-12b-qat-w4a16.md)
- [sgl-project/sglang#27167](https://github.com/sgl-project/sglang/pull/27167)
