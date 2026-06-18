#!/usr/bin/env bash

# 殺掉現有的vLLM
pkill -9 -f "VLLM::Worker_TP[01]"



# load .env for HF_TOKEN, etc.
set -a; source .env; set +a

# Gemma-4-12B vLLM Launch
# Multimodal: enable image + video inputs
# --limit-mm-per-prompt disables multimodal profiling to avoid
# GEMMA4_KV_SLOTS / num_soft_tokens 屬性錯誤
export CUDA_VISIBLE_DEVICES=0,1
uv run vllm serve "google/gemma-4-12B-it-qat-w4a16-ct" \
  --enforce-eager \
  --quantization compressed-tensors \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-auto-tool-choice \
  --attention-backend TRITON_ATTN \
  --max-model-len "${MAX_MODEL_LEN:-65536}" \
  --tensor-parallel-size "${TP_SIZE:-2}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL:-0.90}" \
  --host 0.0.0.0 \
  --port "${PORT:-65500}" \
  --trust-remote-code \
  --enable-prefix-caching \
  --async-scheduling \
  --max-num-seqs 20 \
  --structured-outputs-config.enable_in_reasoning=True \
  --structured-outputs-config.reasoning_parser=gemma4 \
  --limit-mm-per-prompt '{"image": 20, "audio": 0, "video": 0}' \
  --hf-overrides '{"vision_config": {"num_soft_tokens": 1120}}' \
  --mm-processor-kwargs '{"max_soft_tokens": 1120}' \
  --mm-processor-cache-gb 0 \
  # --enable-chunked-prefill \
  # --max-num-batched-tokens 1120

# 圖片 token 預算 70/140/280/560/1120
# 我拿掉了 --enable-chunked-prefill 是因為在多模態模式下 chunk 在平行環境下極易引發 Placeholder 數量計算錯誤
# 官方 262144
