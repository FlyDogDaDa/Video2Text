# 步驟 6 追加：AV1（av1_nvenc）＋ MP4 重產 423 片——討論與決策細節

## 背景

- log 05（2026-08-27）定案 libx264 crf18（MKV），因為當時 GB10 被 sglang/vLLM 佔用
  ~71.5 GiB（util 94%），`av1_nvenc` 試編 `cuCtxCreate` OOM。
- 該 log 的 Follow-up 留了一項可選重試 av1_nvenc 的專案。
- 2026-08-31 使用者正式授權：輸出 **MP4 + av1_nvenc + AAC**，重產全部 423 片，
  輸出到獨立資料夾 **`clips_mp4/`**（不覆蓋既有 `clips/` H.264 產物）。

## GPU 復探（2026-08-31）

- `nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv`
  → `NVIDIA GB10`，util **0%**（GB10 為 unified memory，memory 欄位 N/A）。
  vLLM/sglang 服務閒置，NVENC session 可開。

## 試編驗證

指令（證據檔 `exp/N9boWvU-KkA/tmp/test_av1.mp4`，498,571 bytes）：

```
ffmpeg -hide_banner -loglevel error -ss 412.870 -i exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv \
  -t 0.5 -map 0:v:0 -map 0:a:0 \
  -c:v av1_nvenc -preset p5 -rc vbr -cq 24 -b:v 0 \
  -c:a aac -b:a 192k -avoid_negative_ts make_zero -y exp/N9boWvU-KkA/tmp/test_av1.mp4
```

ffprobe 結果：`av1`（video）＋ `aac`（audio），duration 0.521333s → **通過**。
試編點選 412.870s（clip_0001 起點，p0_s21「對」）。

## 編碼引數決策

| 引數 | 值 | 理由 |
|------|----|------|
| `-preset p5` | 中高速檔 | NVENC 通用 preset（p1 最快、p7 最慢），p5 為速度/品質平衡點 |
| `-rc vbr -cq 24 -b:v 0` | 固定 QP 恆品質 | `-b:v 0` + `-cq` 讓 NVENC 走 CQ 模式，語義對齊 libx264 的 crf；cq24 ≈ x264 crf18 的視覺近似（AV1 壓縮增益下同 QP 更省） |
| 容器 MP4 | `.mp4` | AV1 in MP4（FourCC `av01`）為 ISOBMFF 正式支援；使用者指定 |
| AAC 192k | 不變 | 與 H.264 版一致 |

## 指令碼改裝設計（edit_video.py）

不另開新指令碼，在原指令碼加 CLI 引數，預設行為完全不變（x264→`clips/`、
`clips_manifest.json`）：

- `--encoder {x264,av1_nvenc}`（預設 `x264`）
- `--outdir clips`（輸出資料夾；`clips_mp4` 時 manifest 改為 `clips_mp4_manifest.json`）
- `ENCODERS` 對照表：vcodec／vargs／副檔名（x264→mkv、av1_nvenc→mp4）／標籤
- encoder 寫入每個 job dict（`job["encoder"]`），`cut_one()` 逐 job 取用，
  與 `ProcessPoolExecutor` fork 模型相容
- 其餘邏輯（視窗解析、合併、去重、最小時長、碰撞封頂、manifest 欄位）完全不動

## 併發與相容性考量（規畫）

- 原規畫 18 並行不變。**此假設已被實測推翻**，見下「序列限制（實測）」。
- AV1 MP4 在剪輯軟體的支援度不如 H.264（DaVinci Resolve 需硬體/版本支援、
  Premiere 較晚支援）；兩套產出並存，`clips/` H.264 版仍是最大相容選項。

## 序列限制（實測，推翻 18 並行規畫）

- 試點 `--limit 2 --workers 2`：clip_0001 成功、clip_0002 失敗，stderr 報
  `cuCtxCreate CUDA_ERROR_OUT_OF_MEMORY`，殘留 `clip_0002.mp4` 0 bytes。
- 根因排查：`free` 顯示系統可用僅 ~1 GiB；`sglang serve
  --mem-fraction-static 0.97`（port 8744）佔 GB10 統一記憶體 ~114 GiB。
  該服務即本 agent 自己的推論後端，**絕對不可停**。
- 單一 NVENC context（序列）可正常建立；多 context 同時建立必 OOM。
- 定案解：`--workers 1 --retries 3`（每失敗一次 backoff sleep 2×attempt，
  讓暫時性視訊記憶體波動自行緩解）。產物完全相同，僅 wall time 拉長（估 ~10 分鐘）。
- 教訓：GB10 上「GPU util 0%」不等於「視訊記憶體可用」；NVENC 工作規畫前應先看
  `free`/`nvidia-smi` 的記憶體餘量，而非僅看利用率。

## 執行紀錄

- 指令碼改裝完成＋dry-run 雙模式驗證通過；單程式試編通過；並行試點失敗 →
  定案序列（見上節）。序列全量與 `--verify` 結果待補（見主檔 Execution Results）。
