#!/usr/bin/env bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}")" && pwd )"

# enter virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# load .env for HF_TOKEN, etc.
set -a; source "$SCRIPT_DIR/.env"; set +a

export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

# Default values
PORT="${PORT:-8750}"
TP_SIZE="${TP_SIZE:-1}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.035}"

echo "=== Breeze-ASR-26 vLLM Launch ==="
echo "Port: $PORT"
echo "TP_SIZE: $TP_SIZE"
echo "GPU_MEM_UTIL: $GPU_MEM_UTIL"
echo "================================"

vllm serve "MediaTek-Research/Breeze-ASR-26" \
  --max-model-len 448 \
  --max-num-batched-tokens 1500 \
  --tensor-parallel-size "$TP_SIZE" \
  --gpu-memory-utilization "$GPU_MEM_UTIL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --trust-remote-code \
  --async-scheduling \
  --max-num-seqs 8 \
  --enforce-eager
