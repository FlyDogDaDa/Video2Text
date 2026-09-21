#!/usr/bin/env bash
# 安裝語者 embedding 環境：CPU 版 torch + resemblyzer
set -euo pipefail
cd /home/freespace/文件/Video2Text
echo "=== $(date) torch (cpu) ==="
uv pip install --python exp/Ek7qDwwXZ6A/.venv/bin/python torch \
  --index-url https://download.pytorch.org/whl/cpu
echo "=== $(date) resemblyzer ==="
uv pip install --python exp/Ek7qDwwXZ6A/.venv/bin/python resemblyzer
echo "=== $(date) verify import ==="
exp/Ek7qDwwXZ6A/.venv/bin/python -c "import torch, resemblyzer; print('torch', torch.__version__, '| resemblyzer ok')"
echo "=== $(date) install done ==="
