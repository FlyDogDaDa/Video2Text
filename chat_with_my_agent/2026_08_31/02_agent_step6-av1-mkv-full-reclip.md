---
created: 2026-08-31
author: agent
type: agent
tags: [step6, edit-video, av1, mkv, libsvtav1, davinci-resolve, video2text]
---

# 步驟 6 再追加：MKV＋AV1（libsvtav1）全量重產 423 片到 clips_mkv/

## What

- 使用者目檢定案：**MP4＋AV1 在 DaVinci Resolve 黑幀**；**MKV＋AV1＋AAC 可讀、
  有聲、無黑幀**（測試片 `clips_mp4/clip_0001_test.mkv`）。
- `edit_video.py` 的 `ENCODERS` 新增 `av1_mkv`（libsvtav1 preset5 crf24，容器 mkv）。
- 全量重產 423 片 → `clips_mkv/`，**`--workers 8`**（使用者指定）。
- 完成後打包整夾供下載（zip 或 7z，執行後評估選定）。

## Why

- av1_nvenc（GPU）路線已死：sglang 佔 97% 統一記憶體，`cuCtxCreate` 必 OOM
  （log 00）。CPU `libsvtav1` 是唯一 AV1 路線。
- 容器決定相容性：AV1 in MP4 → Resolve 黑幀；AV1 in MKV → 正常。故放棄 log 00
  的 MP4 目標，改 MKV。
- 輸出到新夾 `clips_mkv/`：`clips_mp4/` 曾遭外部刪檔（來源未明），換路徑同時
  隔離舊殘局；`clips/`（H.264/MKV）與 `clips_mp4/` 均不動。
- 速度現實：libsvtav1 單片 ~6.7s（全執行緒）～4.6s（批次均攤），423 片 8 並行
  估 25–40 分鐘（vs x264 全量僅 47s）。AV1 體積/相容換來的代價。

## How

- `uv run exp/N9boWvU-KkA/scripts/edit_video.py --encoder av1_mkv --outdir
  clips_mkv --workers 8 --retries 3`（背景 nohup ＋ 輪詢）
- 自動 `--verify`（ffprobe 逐片，容差 0.15s）；完成後逐片計數＋抽驗 ffprobe。
- 打包：zip（建議，媒體檔壓縮率≈0，zip 免裝軟體、跨平臺解壓最無摩擦）。

## Execution Results

- 全量切片：**423/423 成功、 0 失敗**，耗時 1416.0s（~24 分鐘，workers=8）。
- `--verify`：**423/423 全部 OK**（ffprobe 逐片，容差 0.15s）。
- 整個執行期間檔案數單調遞增（20s→8、5min→83、6min→99 → 423），未再發生
  log 00 的外部刪檔事件。
- 總量：`clips_mkv/` 共 146 MB；打包 **`clips_mkv.zip`** 145 MB（424 files＝
  423 mkv ＋ manifest；deflate 僅省 ~1%，印證媒體檔壓縮無收益之預判）。
- 完成時間橫註：切片與驗證完成於 08-31；zip 產出於 09-01 11:12（跨日續行）。

## Follow-up

- [x] 全量 423 片 ＋ verify 通過（423/423）
- [x] 打包 zip 並回報路徑與大小（`exp/N9boWvU-KkA/clips_mkv.zip`，145 MB）
- [x] 歸檔改裝後指令碼與 manifest 至本資料夾
- [ ] `clips_mp4/` 殘局（clip_0001 h264 版、0404–0423、test 片）待使用者決定留刪

## Uncertainty

- **刪檔之謎未解**：log 00 執行期間 `clips_mp4/` 被外部持續清除（ffmpeg 寫檔當下
  路徑消失為直接旁證；非指令碼所為、非資源筒/同步層）。已換 `clips_mkv/` 迴避，
  執行中會監控檔案數是否異常下降。
- 8 並行下 20 核的實際吞吐量待實測回填。

## References

- [實測資料與設計細節](references/02_agent_step6-av1-mkv-full-reclip.md)
- [log 00：av1_nvenc 嘗試與序列定案（已被 CPU 路線取代）](00_agent_step6-av1-mp4-reclip.md)
