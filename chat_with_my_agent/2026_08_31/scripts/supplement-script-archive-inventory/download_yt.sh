#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
exp/N9boWvU-KkA/.venv/bin/python -m yt_dlp \
  --no-playlist \
  --js-runtimes node \
  -f "bv*+ba/b" \
  -o "exp/N9boWvU-KkA/download/N9boWvU-KkA.%(ext)s" \
  "https://www.youtube.com/watch?v=N9boWvU-KkA"
