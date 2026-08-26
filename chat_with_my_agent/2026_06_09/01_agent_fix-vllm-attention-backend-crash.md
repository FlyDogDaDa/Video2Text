---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm, attention-backend, triton, flashinfer, fix, crash]
---

# 修復 vLLM attention-backend 引數錯誤導致伺服器崩潰

## What

修復 vLLM server 啟動後無法處理 API 請求的崩潰問題，並修正 `launch_Gemma4-12b.sh` 中錯誤的 attention backend 設定方式。

**結果：** 修復後伺服器正常啟動，API 測試回傳 200 OK。

## Why

### 問題一：`VLLM_ATTENTION_BACKEND` 環境變數被忽略

啟動指令碼第 10 行設定 `export VLLM_ATTENTION_BACKEND=triton`，但 vLLM v0.22.1 **不支援** 這個環境變數，log 中出現警告：

```
WARNING ... Unknown vLLM environment variable: VLLM_ATTENTION_BACKEND
```

結果 vLLM 自動選擇 FlashAttention → FlashInfer backend，在 Gemma-4-12B 的 batch prefill 階段觸發：

```
RuntimeError: Unsupported max_mma_kv: 0
```

FlashInfer 的 MHA KV head 數為 0（Gemma-4 的注意力結構特性），導致崩潰。

### 問題二：舊 vLLM 例項佔滿 VRAM

系統中已有一個從 `screen -S run_vllm_gemma` 啟動的舊 vLLM 例項正在執行，兩張 GPU（A2000 + 4070 SUPER）各已使用約 11 GiB / 12 GiB。新例項啟動時偵測到 VRAM 不足：

```
ValueError: Free memory on device cuda:1 (0.54/11.59 GiB)
on startup is less than desired GPU memory utilization (0.9, 10.43 GiB).
```

### 1. 修正 `launch_Gemma4-12b.sh`

**移除** 不被支援的環境變數設定：

```diff
-export VLLM_ATTENTION_BACKEND=triton
```

**改為** 使用 vLLM CLI 的 `--attention-backend` 引數：

```diff
+  --attention-backend TRITON_ATTN \
```

經過三次嘗試確定正確值：

| 嘗試 | 引數值 | 結果 |
|------|--------|------|
| 1 | `triton` | `ValueError: Unknown attention backend: 'TRITON'` |
| 2 | `triton-attn` | `ValueError: Unknown attention backend: 'TRITON-ATTN'` |
| 3 | `TRITON_ATTN` | ✅ 成功 |

從 vLLM 原始碼 `vllm/v1/attention/backends/registry.py` 確認 `AttentionBackendEnum` 的成員為 `TRITON_ATTN`（大寫 + 底線）。

### 2. 清理舊 vLLM 例項

停掉舊 vLLM 例項並 kill 剩餘的 vllm processes，確認兩張 GPU VRAM 歸零（A2000: 1 MiB used, 4070 SUPER: 5 MiB used）。

### 3. 以 `screen` 啟動 + 外部阻塞等待 + API 測試

vLLM 放在 `screen -S run_vllm_gemma` 中執行，確保 SSH 斷線後服務不會消失。
外部執行串聯指令：

```bash
bash src/vllm_launch/block_me_with_file.sh vllm.log && bash src/vllm_launch/test_api.sh
```

阻塞程式輪詢 log 直到 `Application startup complete.`，然後自動接跑 API 測試。

結果：**HTTP 200 OK**，回應時間 88ms，回傳 `Hi`（正確回應測試訊息 "One word answer: hello"）。

## Follow-up

- [ ] 將修復後的啟動指令碼加入 `screen` 自動重啟機制（取代現有的 `run_vllm_gemma` screen session）
- [ ] 確認 Triton attention backend 的效能是否可接受（對比 FlashAttention）
- [ ] 測試 256K context window 在 TRITON_ATTN backend 上的 VRAM 使用

## References

- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [src/vllm_launch/block_me_with_file.sh](../src/vllm_launch/block_me_with_file.sh)
- [src/vllm_launch/test_api.sh](../src/vllm_launch/test_api.sh)
- [vLLM AttentionBackendEnum registry](https://github.com/vllm-project/vllm/blob/main/vllm/v1/attention/backends/registry.py)
- [vLLM AttentionConfig](https://github.com/vllm-project/vllm/blob/main/vllm/config/attention.py)
- [10_2026_06_09_agent_vllm-launch-and-healthcheck.md](./10_2026_06_09_agent_vllm-launch-and-healthcheck.md)
