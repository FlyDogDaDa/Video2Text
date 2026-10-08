# 05 討論細節：重下載 N9boWvU-KkA 與 AV1+Opus 複製封裝成 MKV

## 背景與使用者指示

- 實驗 `exp/N9boWvU-KkA` 主流程步驟 1：下載 YouTube 影片 `N9boWvU-KkA`（最高畫質＋音質），影音若分開則用 ffmpeg 另存 composite。
- 前輪執行結果：yt-dlp 以 `-f "bv*+ba/b"` 下載完成兩路流（`N9boWvU-KkA.f399.mp4` AV1 影片 1.03GiB、`N9boWvU-KkA.f251.webm` Opus 音訊 85.4MB），但 yt-dlp 自動後處理合併成 `.webm` 失敗（`ERROR: Postprocessing: Conversion failed!`），殘留 `N9boWvU-KkA.temp.webm`（418MB 中途檔）。
- 使用者表示自己手動合併也失敗，指示：
  1. 堅持嘗試 AV1+Opus，不降格格式。
  2. 刪除整個 `exp/N9boWvU-KkA/download` 資料夾，重新下載。
  3. 依序嘗試 `-c copy` 複製封裝成 MKV / MP4 / WebM，「哪個成功就用哪一個」。
  4. 下載指令要丟到另一個 screen 非阻塞執行；並提供 yt-dlp 的 JS runtime warning（預設要 deno，環境沒有）。

## 環境探測與決策

- 探測結果：`tmux` 可用（/usr/bin/tmux）、`deno` 未安裝、`node` 位於 `/home/freespace/.local/bin/node`。
- 決策 1：yt-dlp 加 `--js-runtimes node`，消解 YouTube 抽取的 JS runtime warning。
- 決策 2：tmux session 在本環境無法存活（`tmux list-sessions` 回報 `no server running on /tmp/tmux-1000/default`），改用 `nohup` 背景執行並把輸出寫入 `download/download.log`，達到同等的非阻塞效果。
- 決策 3：下載策略從 `-f "bv*+ba/b"`（會觸發 yt-dlp 自動合併，固定 webm 目標）改為分別下載兩路流：
  - format 399（AV1 1080p30，960.80MiB）→ `N9boWvU-KkA_video.mp4`
  - format 251（Opus 48kHz 雙聲道，85.40MiB）→ `N9boWvU-KkA_audio.webm`
  - 單一路由下載不觸發後處理合併，容器選擇完全交給 ffmpeg。
- 格式選擇依據：`--list-formats` 確認 1080p30 選項有 399（AV1, 960.8MB）、137（H.264, 1.27GiB）、248（VP9, 933MB）。選 399 符合使用者「嘗試 AV1+Opus」指示；137 留作後路（若後續播放/剪輯軟體不支援 AV1），已寫入 TODO 備註。

## 執行過程

1. `rm -rf exp/N9boWvU-KkA/download` 清空舊檔（含失敗中途產物 `.temp.webm`）。
2. 寫 `exp/N9boWvU-KkA/scripts/download_streams.sh`：venv python + yt-dlp、兩筆單格式下載（399、251）、`--no-playlist --js-runtimes node`，不含合併步驟。
3. `nohup` 背景執行，輸出寫 `download/download.log`；約 6 分鐘完成，使用者以 log 結尾「=== 全部下載完成 ===」確認。
4. `ls` 驗證：video 1,007,472,437 B（≈960.8MiB）、audio 89,547,256 B（≈85.4MiB），與 yt-dlp 報告一致，檔案完整。
5. 依使用者指定順序試複製封裝：
   ```
   ffmpeg -hide_banner -loglevel error -y \
     -i exp/N9boWvU-KkA/download/N9boWvU-KkA_video.mp4 \
     -i exp/N9boWvU-KkA/download/N9boWvU-KkA_audio.webm \
     -map 0:v:0 -map 1:a:0 -c copy \
     exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv
   ```
   - MKV 第一次即成功（exit 0），僅有「音訊串流時長未定」之 MKV 常見警告（封裝結束時補齊，不影響）。
   - 依「哪個成功用哪個」原則，MP4 / WebM 未再試。
6. `ffprobe` 驗證 composite（結果存 `assets/yt-download-merge-mkv/ffprobe-composite.json`）：matroska 容器、AV1 Main 1920x1080、Opus 48000Hz/2ch、時長 5667.048 秒、1,096,374,024 B（≈1.05GB）、整體 bit rate ≈1.55Mbps。

## 結果

- 產物：`exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv`（AV1+Opus 複製封裝，未重編碼）。
- 原始分流 `_video.mp4` / `_audio.webm` 保留，未覆蓋、未刪除（後續剪輯/抽音訊仍可直接用）。
- 影片時長 5667.048s（約 94 分 27 秒），與原始影片流 5667.0s 一致，音畫未漂移。
- `TODO.md` 步驟 1 已勾選並記入 ffprobe 備查。

## 不確定／注意

- 前輪 yt-dlp 自動合併失敗（webm 目標）的根因未能從 log 完全確認；可能為舊 `.f399.mp4` 下載中斷損毀，或系統 ffmpeg 6.1.1 對 AV1-in-MP4 封裝的解析問題。新檔 `-c copy` 合併 MKV 成功且 ffprobe 通過，不影響現況；若後續再出現 AV1 OBU parse 錯誤，優先懷疑檔案完整性。
- 重下載過程曾以舊檔名（`.f399.mp4` / `.f251.webm`）跑 ffprobe 得到 "No such file or directory"，係檔名改寫後的人為誤用，非檔案遺失。
- MKV+AV1 的播放相容性：VLC / mpv 無問題；若之後剪輯軟體（部分 NLE）不支援 AV1，後路是改 format 137（H.264 1.27GiB）重下載再合併（已寫入 TODO 備註）。
- 音訊抽 4 段時請注意：此 MKV 音訊是 Opus（有損）；若轉錄要最高音質，可改用原始 `_audio.webm` 或改抽 mp4/aac，視 MOSS ASR 的接受格式而定。
