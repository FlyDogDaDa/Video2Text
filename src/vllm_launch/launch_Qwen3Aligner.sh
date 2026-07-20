#!/usr/bin/env bash

# enter virtual environment
source .venv/bin/activate

# load .env for HF_TOKEN, etc.
set -a; source .env; set +a

# export CUDA_VISIBLE_DEVICES=0
vllm serve Qwen/Qwen3-ForcedAligner-0.6B \
  --runner pooling \
  --hf-overrides '{"architectures": ["Qwen3ASRForcedAlignerForTokenClassification"]}' \
  --host 0.0.0.0 \
  --port 8752 \
  --trust-remote-code \
  --max-model-len 1024  \
  --enforce-eager \
  --gpu-memory-utilization 0.5 \
  --max-num-batched-tokens 1024  \
  --max-num-seqs 1 \
  --async-scheduling
