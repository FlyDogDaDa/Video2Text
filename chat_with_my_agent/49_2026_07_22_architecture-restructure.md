---
created: 2026-07-22
author: agent
type: agent
status: architecture-change
tags: [architecture, decoupling, microservice, client-server, sam-audio]
---

# SAM-Audio 架構調整：模組與微服務解耦

## 概要

決定重構 SAM-Audio 模組的運作方式：
- **`modules/sam_audio.py`**：改為「輕量級 API 客戶端」（Client）。
- **`serve/sam-audio`**：改為「模型運算服務」（Server），負責載入模型與 GPU 管理。

## 架構決策

### 1. 模組端 (`modules/sam_audio.py`)
**職責**：無狀態，僅負責發送請求。

- 移除 `torch`, `torchaudio`, `sam-audio` 等重型依賴。
- 移除 `_model`, `_processor` 全域快取。
- 使用 `httpx` 呼叫 `localhost:8000`。
- 回傳 `SeparationResult` 實例（由 JSON 轉換）。

### 2. 服務端 (`serve/sam-audio`)
**職責**：重型運算，負責模型生命週期管理。

- 保留 `torch`, `sam-audio`, `huggingface-hub` 依賴。
- 使用 `FastAPI` 提供 `POST /separate` 端點。
- 使用 `start_server.py` 設定 `CUDA_VISIBLE_DEVICES` 與記憶體配置。
- 處理 `OOM` 與錯誤恢復。

## 實作摘要

### 已修改檔案

| 檔案 | 變更 |
|------|------|
| `modules/sam_audio.py` | 重寫為 HTTP Client（只依賴 `httpx` + `pydantic`） |
| `serve/sam-audio/sam_audio_core.py` | **新增**：獨立模型載入與分離邏輯（不依賴主專案） |
| `serve/sam-audio/api/service.py` | 改為呼叫 `sam_audio_core`，移除 `modules.sam_audio` import |
| `serve/sam-audio/api/main.py` | 將 `async def` 改為 `def`（FastAPI 會自動跑 threadpool，避免 PyTorch block event loop） |
| `pyproject.toml` | 移除 `torch`, `torchaudio`, `sam-audio`, `huggingface-hub`, `xformers`；新增 `httpx` |
| `tests/test_layer3_sam_audio.py` | 重寫為 mock httpx 請求，不再需要 GPU |
| `tests/test_sam_audio_integration.py` | **新增**：整合測試（實際啟動伺服器 + 驗證端點） |

### 測試結果

```
25 passed, 1 skipped in 1.76s
```

| 測試類別 | 狀態 | 說明 |
|----------|------|------|
| `TestSeparationResult`（5） | ✅ | Pydantic model 序列化測試 |
| `TestSeparateByAnchorClient`（6） | ✅ | mock httpx 請求測試 |
| `TestModuleImports`（7） | ✅ | 所有模組匯入測試 |
| `TestWorkflowCLI`（1） | ✅ | CLI 測試 |
| `TestProfileYAML`（3） | ✅ | YAML profile 測試 |
| `TestIntegration`（3+1） | ✅+⏭ | 實際伺服器測試（3 通過，1 跳過需 GPU） |

## 已知問題與修復紀錄

| 問題 | 修復 |
|------|------|
| `serve/sam-audio/api/service.py` 直接 import `modules.sam_audio`（循環依賴） | 改為呼叫獨立的 `sam_audio_core` |
| FastAPI `async def` 端點呼叫同步 PyTorch 推理 → event loop block | 改為 `def`（sync），FastAPI 自動 threadpool |
| `pyproject.toml` 仍依賴 torch/sam-audio | 移除，移至伺服器專案 |
| 測試需要 GPU 才能執行 | 改為 mock httpx，測試可在任何環境執行 |

## 優點
1. **解耦依賴**：主專案不需要安裝沉重的 PyTorch 生態系。
2. **資源隔離**：模型 crashes 不會導致主程序崩潰。
3. **靈活性**：日後可將微服務部署到另一台機器或 Docker Container。
4. **測試友善**：Client 測試不需要 GPU 也能執行。

## 待辦事項
- [x] 修改 `modules/sam_audio.py` 為 API Client
- [x] 調整 `Video2Text/pyproject.toml` 依賴
- [x] 測試跨進程呼叫（HTTP 端點驗證）
- [x] 確認 `serve/sam-audio` 能正確啟動並處理請求
- [ ] 完整流程測試（需 GPU + 下載 SAM-Audio 模型）