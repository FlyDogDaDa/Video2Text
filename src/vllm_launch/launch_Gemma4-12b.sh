#!/usr/bin/env bash

# enter virtual environment
source .venv/bin/activate

# load .env for HF_TOKEN, etc.
set -a; source .env; set +a

# Force Triton attention to bypass flashinfer max_mma_kv:0 bug with Gemma-4-MM
export VLLM_ATTENTION_BACKEND=triton

# Gemma-4-12B vLLM Launch
vllm serve "google/gemma-4-12B-it-qat-w4a16-ct" \
  --quantization compressed-tensors \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-auto-tool-choice \
  --max-model-len "${MAX_MODEL_LEN:-262144}" \
  --tensor-parallel-size "${TP_SIZE:-2}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL:-0.9}" \
  --host 0.0.0.0 \
  --port "${PORT:-8746}" \
  --trust-remote-code \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --async-scheduling \
  --max-num-seqs 16 \
  --enforce-eager
