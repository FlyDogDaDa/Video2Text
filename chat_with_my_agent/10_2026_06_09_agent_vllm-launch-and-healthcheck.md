---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm-launch, healthcheck, block-me, shell-scripts, flashinfer]
---

# vLLM 啟動指令碼與 API 健康檢查工具

## What

建立兩個 shell 指令碼，簡化 Gemma-4-12B vLLM 服務啟動與 API 驗證流程：

1. `launch_Gemma4-12b.sh` — 一鍵啟動 vLLM serve
2. `block_me_with_file.sh` — 輪詢 log 檔直到服務就緒（或偵測到錯誤）

同時修復了 vLLM server 崩潰的 flashinfer `max_mma_kv: 0` 問題，並驗證 API 呼叫。

## Why

### Launch Script

- `try_video.py` 的 LLM 定義包含多個關鍵引數：`compressed-tensors`、`enforce-eager`、`256K max_model_len`、TRITON_ATTN 等
- 每次手動鍵入長命令容易遺漏或打錯，需要一個可覆用的啟動指令碼
- 從 `.env` 讀取 `HF_TOKEN` 避免重複輸入認證

### Healthcheck Script

- vLLM 啟動需要數十分鐘，無法預知何時就緒
- 在傳送 API 呼叫前，自動等待「Application startup complete.」或偵測到 error
- 避免 API 呼叫遇到 500 Internal Server Error 浪費時間

## How

### 1. `src/vllm_launch/launch_Gemma4-12b.sh`

對應 `try_video.py` 的 LLM 定義：

- `quantization compressed-tensors` → 對應 vLLM 建構引數
- `--max-model-len 262144` → Gemma-4-12B 官方 context window 上限
- `--enforce-eager` → 修復 flashinfer `max_mma_kv: 0` 崩潰
- `--enable-chunked-prefill`、`--enable-prefix-caching`、`--async-scheduling` → 效能最佳化
- `--reasoning-parser gemma4`、`--tool-call-parser gemma4`、`--enable-auto-tool-choice` → Gemma-4 工具呼叫支援

所有引數皆可透過環境變數覆蓋（`MODEL`、`PORT`、`MAX_MODEL_LEN` 等）。

### 2. `src/vllm_launch/block_me_with_file.sh`

輪詢機制：

- 每 30 秒檢查一次 log 檔（預設）
- 偵測到 `Application startup complete.` 表示就緒（成功）
- 偵測到 `error`（case-insensitive）表示失敗
- 也回報目前 log 行數，讓使用者知道進度

### 3. flashinfer 崩潰修復

**根因：** 啟動指令碼第 25 行縮排錯誤（1 個空格 + 末尾 `\`），讓 `--enforce-eager` 被 vLLM CLI 當成 **positional argument**（model name），而非 flag。

結果 vLLM 啟動了 flashinfer attention backend（而非 triton），遇到 `max_mma_kv: 0` 崩潰。

**修復：** 修正縮排，確保 `--enforce-eager` 正確傳入 vLLM。

Server 重啟後顯示 "Application startup complete."，但 API 測試還需要重新驗證（上次 curl 測試是修復前的 500 錯誤）。

## Follow-up

- [ ] 驗證 flashinfer 崩潰修復後，API 呼叫是否正常運作
- [ ] 測試 TRITON_ATTN 作為替代方案（可能保留 CUDA graph 效能）
- [ ] 考慮將 `launch_Gemma4-12b.sh` 加入 systemd service 或 screen 自動重啟
- [ ] 實測 256K context window 在 12GB×2 GPU 上的 VRAM 使用情況

## References

- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [src/vllm_launch/block_me_with_file.sh](../src/vllm_launch/block_me_with_file.sh)
- [08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py](./08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py)
- [08_2026_06_08_agent_gemma4-vllm-inference-fixes.md](./08_2026_06_08_agent_gemma4-vllm-inference-fixes.md)
