#!/usr/bin/env bash
# 重新下載 YouTube N9boWvU-KkA：AV1 影片與 Opus 音訊分開存檔，不做 yt-dlp 自動合併
set -euo pipefail
cd /home/freespace/文件/Video2Text
mkdir -p exp/N9boWvU-KkA/download
PY="exp/N9boWvU-KkA/.venv/bin/python"
URL="https://www.youtube.com/watch?v=N9boWvU-KkA"

echo "=== $(date) 開始下載影片 (format 399, AV1 1080p30) ==="
"$PY" -m yt_dlp --no-playlist --js-runtimes node -f 399 \
  -o "exp/N9boWvU-KkA/download/N9boWvU-KkA_video.%(ext)s" \
  "$URL"

echo "=== $(date) 開始下載音訊 (format 251, Opus 48kHz) ==="
"$PY" -m yt_dlp --no-playlist --js-runtimes node -f 251 \
  -o "exp/N9boWvU-KkA/download/N9boWvU-KkA_audio.%(ext)s" \
  "$URL"

echo "=== $(date) 全部下載完成 ==="
