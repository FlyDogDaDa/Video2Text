---
created: 2026-06-08
author: Agent
type: agent
status: final
tags: [vllm, flashinfer, cuda-graph, gemma4-mm, inference, video2text]
---

# Gemma 4 vLLM 推論 — 修復 flashinfer 崩潰與影片路徑

## What

- 修復 flashinfer `Unsupported max_mma_kv: 0` 導致 vLLM engine 啟動崩潰
- 修正 `try_video.py` 中影片路徑不正確的問題
- 成功完成 Gemma-4-12B 多模態影片摘要推論

## Why

### Flashinfer 崩潰

vLLM 在 CUDA graph profiling 階段（`profile_cudagraph_memory` → `_warmup_and_capture` → `_dummy_run`）呼叫 flashinfer 的 `BatchPrefillWithPagedKVCache` kernel 時，`gemma4_mm` 模型傳入了一個無效的 `max_mma_kv = 0` 參數，導致 flashinfer 拋出 `RuntimeError` 並使整個 engine 崩潰。

堆疊關鍵路徑：
```
gemma4_mm.forward → gemma4.forward → flashinfer.decode.run →
BatchPrefillWithPagedKVCacheDispatched → max_mma_kv: 0
```

這是 flashinfer 與 Gemma 4 多模態模型之間的已知相容性問題。

### 影片路徑錯誤

原始路徑 `2026_05_11-19_18_26.mp4` 不存在，實際檔案為 `2026_05_11-19_18_26_louder4x.mp4`。

## How

### 1. 啟用 `enforce_eager=True`

在 `try_video.py` 的 `LLM()` 建構子中加入 `enforce_eager=True`：

- `try_video.py` 第 22 行：加入 `enforce_eager=True` 參數
- 跳過 CUDA graph 的捕獲與記憶體配置，改用 eager mode 執行
- 代價：推理速度可能降低 10-30%（失去 CUDA graph 優化），但能正常運作

```python
llm = LLM(
    model=model_path,
    quantization=quantization,
    tensor_parallel_size=tp_size,
    max_model_len=8192,
    trust_remote_code=True,
    enforce_eager=True,           # ← 新增
    limit_mm_per_prompt={"image": 4, "video": 1},
)
```

### 2. 修正影片路徑

- `try_video.py` 第 27 行：路徑從 `2026_05_11-19_18_26.mp4` 改為 `2026_05_11-19_18_26_louder4x.mp4`
- 透過 `find_path` 搜尋專案中實際存在的 `.mp4` 檔案確認

### 3. 驗證成功

推論成功完成，輸出約 14 秒：

```
Processed prompts: 100% | 1/1 [00:14<00:00, 14.34s/it,
est. speed input: 168.73 toks/s, output: 23.36 toks/s]
```

模型成功摘要影片內容（Linux terminal 操作示範）。

### 4. NCCL 關閉雜訊

使用 `tensor_parallel_size=2` 時，engine 關閉後 worker 仍嘗試連線至 TCPStore，產生 NCCL recv error。這是正常清理行為，不影響結果。

## Key Learnings

1. **flashinfer + Gemma 4 多模態不相容** — `max_mma_kv: 0` 錯誤會觸發 CUDA graph profiling 崩潰，需以 `enforce_eager=True` 繞過
2. **`enforce_eager=True` 的權衡** — 犧牲效能換取相容性。若需最佳效能，可嘗試切換至 `TRITON_ATTN` 後端（已在程式碼中保留為可選）
3. **TP=2 的關閉雜訊** — 多 GPU 設定下 NCCL/TCPStore 關閉錯誤可安全忽略

## Follow-up

- [ ] 測試 `TRITON_ATTN` 後端能否在不用 `enforce_eager=True` 的情況下解決 flashinfer 問題（保留 CUDA graph 優化）
- [ ] 評估 `enforce_eager=True` 對推理速度的實際影響，若過慢可考慮調整 `max_model_len` 或增加 warmup
- [ ] 確認是否有其他多模態模型也會觸發此 flashinfer 相容性問題

## References

- [try_video.py](../try_video.py)
- [07_2026_06_07_agent_test-video-spec.md](./07_2026_06_07_agent_test-video-spec.md)
- [06_2026_06_07_agent_vllm-restore-for-gemma4.md](./06_2026_06_07_agent_vllm-restore-for-gemma4.md)
- [flashinfer prefills.cuh:2964 — max_mma_kv check](https://github.com/flashinfer-ai/flashinfer/blob/main/include/flashinfer/attention/prefill.cuh)
