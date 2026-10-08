# 步驟 6 切片執行：定案 B、編碼器探測與 plan 細節

## 背景

2026-08-27 使用者對 log 04 的三個選項定案：

- **選項 B**：逐片重編碼、幀精確起點。
- 編碼器偏好：硬體支援時用 NVIDIA NVENC AV1，否則 fallback `libx264 -crf 18`。
- 並行：clip 互相獨立，可用程式池並行；機器 20 核，**上限 18**，避免卡死。

## 硬體與編碼器探測

### nvidia-smi

- GPU：NVIDIA **GB10**（Blackwell），driver 580.95.05，CUDA 13.0，GPU-Util 94%。
- 視訊記憶體主要被模型服務佔用（與 FA/ASR 伺服器同源）：
  - `sglang::scheduler` 49210 MiB
  - `VLLM::EngineCore` 10947 MiB
  - `asr.venv/bin/python3` 9669 MiB
  - `sglang/.venv/bin/python3` 1006 MiB
  - 合計 ≈ 71.5 GiB，無餘量再開 CUDA context。

### av1_nvenc 探測

- `ffmpeg -encoders` 列有 `av1_nvenc`（選項：`-preset p1..p7`、`-tune hq/ll/ull/lossless`、`-rc constqp/vbr/cbr`、`-cq 0-51`、`-gpu` 等）。
- 實測 0.5s 試編碼（`-ss 100 -t 0.5 -c:v av1_nvenc`）：
  - `dl_fn->cuda_dl->cuCtxCreate ... failed -> CUDA_ERROR_OUT_OF_MEMORY`
  - `No capable devices found` → **編碼失敗**。
- 結論：模型服務佔用期間 NVENC AV1 不可用 → 依使用者指示 fallback。

### AV1 解碼端

- 可用解碼器：`libdav1d`（軟體、快）、`av1_cuvid`（硬體）、native `av1`。
- ffmpeg 預設走 dav1d，與 GPU 佔用無衝突；重編碼時 AV1→H.264 解碼無阻。

### libx264 試編碼

- `ffmpeg -hide_banner -loglevel error -ss 100 -i .../N9boWvU-KkA_composite.mkv -t 0.5 -c:v libx264 -crf 18 -preset fast -c:a aac -y exp/N9boWvU-KkA/tmp/test_x264.mkv` → 成功。
- ffprobe 回讀：h264 + aac，duration 0.521s（請求 0.5s + 容器 overhead，正常）。

→ **編碼器定案：`libx264 -crf 18 -preset fast`（影片）＋ `aac -b:a 192k`（音訊）**。

## edit_video.py 設計

輸入：`exp/N9boWvU-KkA/filtered_aligned.json`（334 段、494 詞樣本、全部為影片絕對時間）。

- **視窗解析** `resolve_window()`：
  1. `end_s > start_s` → 用修補值，標 `fixed`；
  2. 零長且 `0 < raw_dur <= 0.6s` → 用 raw 視窗，標 `raw_window`；
  3. 其餘 → `T ± 0.2s`，標 `t_pad`。
- **同段落合併**：相鄰詞樣本間距 ≤ 0.05s 併成一個 clip（例如「對對對」）。
- **跨 segment 去重**：全域排序後，間距 ≤ 0.05s 的相鄰 clip 無論跨不跨 segment 都合併。
  - 資料事實：4 個零長「對」的 T 被兩個相鄰 segment 同時記錄（T=2514.454、2657.414、3286.728、3671.998）。
  - 不去重時，相同 start_s 會使碰撞上限把前一個 clip 的 `end_s` 壓到 `start_s` 之下（初版 dry-run 出現 min = -0.010s 負時長）。加入去重後 434 → 423 clips，負時長消失。
- **最小時長**：0.30s；不足向 `end_s` 延伸，再被「下一 clip start − 0.01」與「影片總長 − 0.033s」封頂（因此 min 實為 0.230s，屬碰撞封頂而非負值）。
- **切片指令**：
  `ffmpeg -hide_banner -loglevel error -ss <start> -i composite.mkv -t <dur> -map 0:v:0 -map 0:a:0 -c:v libx264 -crf 18 -preset fast -threads 2 -c:a aac -b:a 192k -avoid_negative_ts make_zero -y clips/clip_NNNN.mkv`
  - `-ss` 置於 input 前：重編碼模式下精確到幀（解碼自最近 keyframe 起丟幀至目標）。
  - 每 process `-threads 2`（x264 執行緒），避免 18 個 process × 20 核過額訂閱。
- **並行**：`concurrent.futures.ProcessPoolExecutor(max_workers=18)`，worker 為 module-level `cut_one()`（Linux fork 可直接 pickle）。
- **產出**：`clips/clip_0001.mkv … clip_0423.mkv` ＋ `clips_manifest.json`（index / file / start_s / end_s / duration_s / timecode / seg_id / part / words / window_sources）。
- **模式**：`--dry-run`（只印統計）、`--limit N`（前 N 片目檢）、預設全量、`--verify`（ffprobe 全量驗時長，容差 ±0.15s）。

## 與 log 04 零長審計的分歧（25 vs 33 raw）

log 04 對 43 個零長「對」的審計：33 個可用 raw（0.08–0.32s）／9 個 raw 反轉／1 個 raw 異常（1.44s）。本指令碼實跑分佈為 **25 raw_window／18 t_pad**。逐個比對 `raw_dur = end_s_raw − start_s_raw`：

| raw_dur 分組 | 數量 | 處理 |
|---|---|---|
| 0 < raw_dur ≤ 0.6s | 25 | raw_window |
| raw_dur = 0.0（raw 也是零長） | 6 | t_pad（raw 無法提供視窗） |
| 0.64s（同 T=2514.454，p1_s400「對對」重覆樣本 ×2） | 2 | t_pad（超 0.6s 上限） |
| 1.44s（p1_s262，離群） | 1 | t_pad |
| 負值（raw 反轉） | 9 | t_pad |
| 合計 | 43 | — |

log 04 把 raw 零長的 6 個與 0.64s 的 2 個歸入「可用 raw」；本指令碼以 `0 < raw_dur ≤ 0.6` 為準，差異 8 個改走 t_pad。對 6 個 raw 零長者，raw 本就無視窗可用；0.64s 兩例的 t_pad 視窗（0.4s）仍可覆蓋該字。切片可用性不受影響。

## Dry-run 結果（2026-08-27）

```
Clip 總數：423
總影片秒數：147.0s
單片時長：min 0.230s / median 0.300s / max 1.040s
視窗來源分佈：{'fixed': 451, 'raw_window': 25, 't_pad': 18}
詞彙分佈：{'對': 469, '沒錯': 20, '確實': 5}   （合計 494 樣本）
編號範圍：clip_0001.mkv … clip_0423.mkv
首片 412.870s（p0_s21「對」）／末片 end 5617.482s（p3_s959「對」）；全在總長 5667.016s 內
```

## 使用的指令

```
# dry-run
exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/edit_video.py --dry-run
# NVENC 試編碼（失敗，證據）
ffmpeg -hide_banner -loglevel error -ss 100 -i exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv -t 0.5 -c:v av1_nvenc -c:a aac -y exp/N9boWvU-KkA/tmp/test_av1_nvenc.mkv
# x264 試編碼（成功）
ffmpeg -hide_banner -loglevel error -ss 100 -i exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv -t 0.5 -c:v libx264 -crf 18 -preset fast -c:a aac -y exp/N9boWvU-KkA/tmp/test_x264.mkv
```
