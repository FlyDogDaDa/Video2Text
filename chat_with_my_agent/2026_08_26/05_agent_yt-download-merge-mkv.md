---
created: 2026-08-26
author: agent
type: agent
tags: [video2text, yt-dlp, ffmpeg, av1, opus, mkv, 實驗]
---

# 重下載 N9boWvU-KkA + AV1/Opus 複製封裝成 MKV

## What

- 依使用者指示刪掉整個 `exp/N9boWvU-KkA/download/`，重新下載 YouTube `N9boWvU-KkA`：
  format 399（AV1 1080p30，1.03GiB）＋ format 251（Opus 48kHz，85.4MB）兩路分流，
  檔案為 `download/N9boWvU-KkA_video.mp4` 與 `download/N9boWvU-KkA_audio.webm`。
- yt-dlp 自動合併（webm 目標）前輪失敗後，改用 ffmpeg `-c copy` 手動複製封裝：
  **MKV 一次成功** → `exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv`。
- `ffprobe` 驗證：matroska 容器、AV1 Main 1920x1080 ＋ Opus 48000Hz/2ch、
  時長 5667.048 秒（≈94 分 27 秒）、1.05GB，音畫無重編碼。
- MP4 / WebM 依「哪個成功用哪個」原則未再試。
- `TODO.md` 步驟 1 勾選完成，並記入 ffprobe 備查。

## Why

- 前輪 yt-dlp 下載完但 post-merge 成 `.webm` 失敗（`Postprocessing: Conversion failed!`），
  使用者手動合併也失敗；指示重下載並自行用 `-c copy` 試 MKV/MP4/WebM。
- 改分別下載兩路流（不用 `bv*+ba/b`），合併完全交給 ffmpeg，容器可自由選；
  MKV 對 AV1+Opus 最寬容，一次過。
- yt-dlp 加 `--js-runtimes node`（環境無 deno，node 在 `/home/freespace/.local/bin/node`），
  消解 YouTube 抽取 warning。

## How

- 新增 `exp/N9boWvU-KkA/scripts/download_streams.sh`：venv python + yt-dlp，
  兩筆單格式下載（399、251）、`--no-playlist --js-runtimes node`，不含合併。
- tmux 本環境無法存活（`no server running on /tmp/tmux-1000/default`），
  改 `nohup` 背景跑＋輸出寫 `download/download.log`（非阻塞效果同等）。
- 合併指令：
  `ffmpeg -hide_banner -loglevel error -y -i ..._video.mp4 -i ..._audio.webm -map 0:v:0 -map 1:a:0 -c copy ..._composite.mkv`
  （exit 0，僅 MKV 音訊時長未定的常見警告，封裝結束時自動補齊）。
- `ffprobe` 驗證 composite 通過；驗證 JSON 與 download.log 已歸檔至 assets。

## Follow-up

- 步驟 2：從 `N9boWvU-KkA_composite.mkv`（或直接原始 `_audio.webm`）抽音訊、
  等分 4 段 → `audio_part_0..3`，記錄各段 offset。
- 若後續剪輯工具不支援 AV1，後路：改 format 137（H.264, 1.27GiB）重下載再合併。

## Uncertainty

- 前輪 yt-dlp 自動合併失敗的根因未定：可能是舊檔下載中斷損毀，
  或系統 ffmpeg 6.1.1 對 AV1-in-MP4 的解析問題。新檔已驗證無誤，暫不深究。
- MKV＋AV1 的播放/剪輯相容性未實測（VLC/mpv 應可；某些 NLE 可能不支援 AV1），
  若出問題走 H.264 後路。

## References

- [討論細節](references/05_agent_yt-download-merge-mkv.md)
- [腳本歸檔：download-streams](scripts/download-streams/README.md)
- [驗證證據歸檔](assets/yt-download-merge-mkv/README.md)
- [ffprobe 驗證 JSON](assets/yt-download-merge-mkv/ffprobe-composite.json)
- [下載 log 複本](assets/yt-download-merge-mkv/download.log)
