#!/usr/bin/env bash
# MOSS-Transcribe-Diarize vLLM 伺服器啟動（本機，與 SGLang qwen176b 共存）
# 依 model card：vllm serve OpenMOSS-Team/MOSS-Transcribe-Diarize --trust-remote-code
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/.venv/bin/activate"
export VIRTUAL_ENV="$SCRIPT_DIR/.venv"
set -a; source "$SCRIPT_DIR/.env"; set +a

export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
PORT="${PORT:-8750}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.12}"

echo "=== MOSS-Transcribe-Diarize vLLM Launch ==="
echo "Port: $PORT  GPU_MEM_UTIL: $GPU_MEM_UTIL"
echo "==============================================="

uv run vllm serve "OpenMOSS-Team/MOSS-Transcribe-Diarize" \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port "$PORT" \
  --max-model-len 81920 \
  --gpu-memory-utilization "$GPU_MEM_UTIL"
