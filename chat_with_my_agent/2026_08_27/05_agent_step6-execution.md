---
created: 2026-08-27
author: agent
type: agent
tags: [step6, edit-video, re-encode, parallel, nvenc, video2text]
---

# 步驟 6 切片執行：定案 B、NVENC 探測與 edit_video.py 計畫

## What

- 使用者定案步驟 6 **選項 B**（逐片重編碼、幀精確起點），並指定：
  - 編碼器：硬體支援時用 NVIDIA NVENC AV1，否則 fallback `libx264 -crf 18`；
  - 並行：clip 互相獨立，可用程式池並行；20 核機器，**上限 18**，避免卡死。
- 探測 NVENC AV1：GB10 GPU 被 sglang/vLLM 佔用 ~71.5 GiB（util 94%），`cuCtxCreate` OOM → **av1_nvenc 不可用** → 定案 `libx264 -crf 18 -preset fast` + `aac 192k`（0.5s 試編碼通過）。
- 寫 `exp/N9boWvU-KkA/scripts/edit_video.py`：`--dry-run`／`--limit N`／全量／`--verify` 四模式。
- dry-run 結果：**423 clips、總長 147.0s**，時長 0.23–1.04s；494 樣本 → fixed 451 / raw_window 25 / t_pad 18。
- 修復初版 dry-run 的負時長 bug（跨 segment 相同 T 的重複「對」在碰撞上限下 `end_s < start_s`）→ 加入跨 segment 去重合併，434 → 423。
- `exp/N9boWvU-KkA/TODO.md` 步驟 6 更新為 B 計畫。

## Why

- 本片 GOP 固定 6.0s（log 04），`-c copy` 起點最壞回退 6s，B 是唯一幀精確路徑。
- NVENC AV1 本是 GB10 最佳搭配，但視訊記憶體被模型服務佔滿；libx264 crf18 視覺近無損、剪輯軟體全支援。
- 18 並行 = 20 核留 2 核給系統與 AV1 解碼（dav1d），避免過額訂閱。

## How

- 探測：`nvidia-smi`（視訊記憶體／程式）、`ffmpeg -encoders`、av1_nvenc 與 libx264 各 0.5s 試編碼（證據在 `exp/N9boWvU-KkA/tmp/test_*.mkv`）。
- 指令碼：視窗解析（fixed / raw≤0.6s / T±0.2s）→ 同段落間距 ≤0.05s 合併 → 跨 segment 去重 → 最小時長 0.30s（碰撞封頂）→ `ProcessPoolExecutor(18)` 逐片 ffmpeg 重編 → `clips/clip_NNNN.mkv` + `clips_manifest.json`。
- 與 log 04 審計的零長分佈差異（25 vs 33 raw）逐個核對：差異 8 個 = 6 個 raw 零長 ＋ 2 個 0.64s 超上限，改走 t_pad；見 references。

## Execution Results（2026-08-27）

- 試切 `--limit 2`：2/2 成功，0.9s；ffprobe 確認 h264+aac、時長 0.374s（容差內）。
- 全量：423/423 成功、0 失敗，耗時 **47.3s**；`--verify` 全量通過（423/423）。
- 抽驗 clip_0001（0.374s）、clip_0100（0.388s）、clip_0423（0.354s）：h264+aac 流均在、時長合理。
- Manifest：`exp/N9boWvU-KkA/clips_manifest.json`（423 entries）。

## Follow-up

- [x] 先切前 2 片目檢音畫同步（ffprobe 客觀檢查通過；使用者可自行播放 `clips/clip_0001.mkv` 等確認）
- [x] 全量切 423 片 ＋ `--verify` 全量 ffprobe 驗證（423/423 通過）
- [ ] （可選）釋放 GPU 視訊記憶體後可重試 av1_nvenc：檔案更小、編碼更快

## Uncertainty

- 零長政策（25 raw_window ＋ 18 T±0.2s）為 log 04 暫定值，使用者未逐項確認，本次依此執行。
- 全量耗時實測 47.3s（遠低於估計 5–15 分鐘）。
- 若 GPU 視訊記憶體之後釋放，av1_nvenc 可能可用，屆時產物格式（H.264 vs AV1）會不一致。

## References

- [討論細節（編碼器探測、零長審計核對、dry-run 與執行資料）](references/05_agent_step6-execution.md)
- [程式歸檔](scripts/step6-edit-video/edit_video.py)
- [產出 Manifest 歸檔](assets/step6-execution/clips_manifest.json)
- [步驟 6 keyframe 偏離調查](04_agent_step6-keyframe-gop-deviation.md)
- [指令碼源檔](../../exp/N9boWvU-KkA/scripts/edit_video.py)（exp/ 下，不入 git）
