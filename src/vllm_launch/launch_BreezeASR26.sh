#!/usr/bin/env bash

# enter virtual environment
source .venv/bin/activate

# load .env for HF_TOKEN, etc.
set -a; source .env; set +a

# Breeze-ASR-26 vLLM Launch
# ASR: Whisper-based automatic speech recognition (Taiwanese Hokkien)
# forced_aligner: Qwen3-ForcedAligner for word-level timestamp alignment
# Uses pooling runner + token classification for forced alignment

export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export CUDA_VISIBLE_DEVICES=0
vllm serve "MediaTek-Research/Breeze-ASR-26" \
  --max-model-len 1500 \
  --max-num-batched-tokens 1500 \
  --tensor-parallel-size "${TP_SIZE:-1}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL:-0.4}" \
  --host 0.0.0.0 \
  --port "${PORT:-8750}" \
  --trust-remote-code \
  --async-scheduling \
  --max-num-seqs 16 \
  # --max-model-len 1500 \
  # --max-num-batched-tokens 1500 \
  # --runner pooling \
  # --hf-overrides '{"architectures": ["Qwen3ASRForcedAlignerForTokenClassification"]}' \
  # --limit-mm-per-prompt '{"audio": 1}'
