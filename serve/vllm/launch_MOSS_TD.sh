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
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.25}"
# 長音訊（24min 部分 ≈ 18000 audio tokens）：vLLM 預設 encoder cache =
# max_num_batched_tokens（2048）會拒收，故調大；音檔大小／解碼時長上限也同步放寬
MAX_BATCHED_TOKENS="${MAX_BATCHED_TOKENS:-24576}"
# 模型 generation_config.json 帶 max_new_tokens: 5120，24min 視窗約需 11k tokens，
# vLLM STT serving 層會拿它當生成上限而截斷 → 覆蓋拉高
OVERRIDE_GEN_CONFIG="${OVERRIDE_GEN_CONFIG:-{\"max_new_tokens\": 16384}}"
export VLLM_MAX_AUDIO_CLIP_FILESIZE_MB="${VLLM_MAX_AUDIO_CLIP_FILESIZE_MB:-64}"
export VLLM_MAX_AUDIO_DECODE_DURATION_S="${VLLM_MAX_AUDIO_DECODE_DURATION_S:-1800}"

echo "=== MOSS-Transcribe-Diarize vLLM Launch ==="
echo "Port: $PORT  GPU_MEM_UTIL: $GPU_MEM_UTIL  MAX_BATCHED_TOKENS: $MAX_BATCHED_TOKENS"
echo "==============================================="

uv run vllm serve "OpenMOSS-Team/MOSS-Transcribe-Diarize" \
  --trust-remote-code \
  --host 0.0.0.0 \
  --port "$PORT" \
  --max-model-len 81920 \
  --max-num-batched-tokens "$MAX_BATCHED_TOKENS" \
  --override-generation-config "$OVERRIDE_GEN_CONFIG" \
  --gpu-memory-utilization "$GPU_MEM_UTIL"
