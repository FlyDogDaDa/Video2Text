#!/usr/bin/env bash
# 下載 Ek7qDwwXZ6A：先音訊（轉錄急需）、後影片；不做 yt-dlp 自動合併
set -euo pipefail
cd /home/freespace/文件/Video2Text
PY="exp/Ek7qDwwXZ6A/.venv/bin/python"
URL="https://www.youtube.com/watch?v=Ek7qDwwXZ6A"
mkdir -p exp/Ek7qDwwXZ6A/download

echo "=== $(date) audio (251/140 fallback, Opus) ==="
"$PY" -m yt_dlp --no-playlist --js-runtimes node -f "251/140/ba*" \
  -o "exp/Ek7qDwwXZ6A/download/Ek7qDwwXZ6A_audio.%(ext)s" \
  "$URL"

echo "=== $(date) video (399/248 fallback) ==="
"$PY" -m yt_dlp --no-playlist --js-runtimes node -f "399/248/bv*" \
  -o "exp/Ek7qDwwXZ6A/download/Ek7qDwwXZ6A_video.%(ext)s" \
  "$URL"

echo "=== $(date) all downloads done ==="
