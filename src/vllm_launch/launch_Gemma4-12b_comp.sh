#!/usr/bin/env bash

# --- [關鍵修復] 限制 FlashInfer / Ninja JIT 編譯時的執行緒，避免 GB10 統一記憶體 OOM ---
export MAX_JOBS=12
export NINJAFLAGS="-j8"
export FLASHINFER_NVCC_THREADS=8

# load .env for HF_TOKEN, etc.
set -a; source .env; set +a

export CUDA_VISIBLE_DEVICES=0,1
uv run vllm serve "google/gemma-4-12B-it-qat-w4a16-ct" \
  --enforce-eager \
  --quantization compressed-tensors \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-auto-tool-choice \
  --attention-backend TRITON_ATTN \
  --max-model-len "${MAX_MODEL_LEN:-32768}" \
  --tensor-parallel-size "${TP_SIZE:-2}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL:-0.92}" \
  --host 0.0.0.0 \
  --port "${PORT:-65500}" \
  --trust-remote-code \
  --enable-prefix-caching \
  --async-scheduling \
  --max-num-seqs 21 \
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
