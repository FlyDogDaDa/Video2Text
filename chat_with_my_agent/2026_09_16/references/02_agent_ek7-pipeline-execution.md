# Ek7qDwwXZ6A 新管線執行 — 討論細節（2026-09-16）

> 執行過程完整時間軸在 `exp/Ek7qDwwXZ6A/execution-log.md`（即時維護）。
> 本檔凍結執行當下的關鍵決策與煙霧測試數據。

## 執行中的三個決策

1. **ASR 伺服器自起**：health check 三次 connection refused → 發現 `10.46.219.5`
   就是本機 IP、伺服器沒在跑。專案內無 MOSS 啟動腳本（僅 Breeze 模板）→
   依 model card（`vllm serve OpenMOSS-Team/MOSS-Transcribe-Diarize --trust-remote-code`）
   寫 `serve/vllm/launch_MOSS_TD.sh`。
2. **max-model-len 修正**：預設 131072 需 14GiB KV cache、util=0.10 只剩 9.14GiB →
   壓到 81920（24min 音訊足容；vLLM 依可用記憶體估計上限 85600）。
3. **GPU 阻塞裁決**：SGLang qwen176b 佔 ~97GB／128GB（unified memory），
   新 CUDA 程序連 context 都建不起來（與 8/31 日誌 cuCtxCreate OOM 同因）。
   四次嘗試（#1 KV cache→修 len；#2/#3/#4 CUDA OOM）確認非參數問題 →
   停止重試，**不擅自停用使用者的 176B 服務**。

## 煙霧測試（speaker_unify.py × 舊資料 N9boWvU-KkA）

- 動機：ASR 受阻，先用舊資料（唯讀）驗證 embedding→矩陣→約束合併整條路。
  舊資料只是腳本 QA，非管線輸出（使用者已明確新實驗獨立）。
- 第一輪（τ=0.75，阻擋式 ambiguous）：8 組全被 flag → 0 全域語者。發現規則缺陷。
- 第二輪（τ=0.90，margin 審查不阻擋）：**G01/G02 兩個全域語者、963 段全指派、0 未定案**。

### 相似度矩陣（煙霧測試實試實測，凍結）

```
       p0S01  p0S02  p1S01  p1S02  p2S01  p2S02  p3S01  p3S02
p0S01  1.000  0.784  0.969  0.766  0.778  0.959  0.970  0.753
p0S02  0.784  1.000  0.812  0.961  0.965  0.800  0.804  0.953
p1S01  0.969  0.812  1.000  0.799  0.810  0.972  0.975  0.791
p1S02  0.766  0.961  0.799  1.000  0.985  0.779  0.791  0.978
p2S01  0.778  0.965  0.810  0.985  1.000  0.796  0.799  0.985
p2S02  0.959  0.800  0.972  0.779  0.796  1.000  0.974  0.776
p3S01  0.970  0.804  0.975  0.791  0.799  0.974  1.000  0.773
p3S02  0.753  0.953  0.791  0.978  0.985  0.776  0.773  1.000
```

- G01 = {p0S01, p1S01, p2S02, p3S01}：458 段／2050.68s，跨段相似 0.959–0.975
- G02 = {p0S02, p1S02, p2S01, p3S02}：505 段／2845.68s，跨段相似 0.953–0.985
- intra-cluster ≥ 0.953、inter-cluster ≤ 0.812 → τ=0.90 乾淨分隔
- low_margin_merges ×4 皆良性：次優替代即同一人的其他 part centroid，
  隨後仍併入同一叢集（transitivity 正確消化）

## 環境限制發現（重要，供未來排程）

- GB10（128GB unified memory）上，SGLang qwen176b（~97GB）運行期間，
  **任何新 CUDA 程序**（含 0.9B 小模型 vLLM）都會在 context 建立時 OOM。
- 排程含 GPU 的作業前先 `ss -tln | grep 8750`／`nvidia-smi` 確認資源，
  或直接詢問使用者 SGLang 是否可停。
