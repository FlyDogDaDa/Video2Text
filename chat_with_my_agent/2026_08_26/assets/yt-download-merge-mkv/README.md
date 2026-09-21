# yt-download-merge-mkv 歸檔

本資料夾存檔「重新下載 N9boWvU-KkA + AV1/Opus 複製封裝成 MKV」的驗證證據。

| 檔案 | 來源 | 用途 |
|------|------|------|
| `download.log` | `exp/N9boWvU-KkA/download/download.log`（複本） | yt-dlp 重下載紀錄：format 399（AV1 1080p30, 960.80MiB）與 251（Opus 48kHz, 85.40MiB）兩筆 100% 完成，及「全部下載完成」標記 |
| `ffprobe-composite.json` | `ffprobe -v error -show_entries format=...:stream=... -of json` 對 `exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv` 的輸出 | 驗證合流結果：matroska 容器、AV1 Main 1920x1080 + Opus 48000Hz/2ch、時長 5667.048 秒（約 94 分 27 秒）、1,096,374,024 bytes |

源檔（體積大，未歸檔，保留在 `exp/N9boWvU-KkA/download/`）：

- `N9boWvU-KkA_video.mp4`（AV1 影片流）
- `N9boWvU-KkA_audio.webm`（Opus 音訊流）
- `N9boWvU-KkA_composite.mkv`（複製封裝產物）
