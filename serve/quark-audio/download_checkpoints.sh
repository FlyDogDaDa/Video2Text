#!/bin/bash
# download_checkpoints.sh — 下載 QuarkAudio-UniSE 推理所需權重
# 使用 hf (cli) 自動下載到指定位置

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECKPOINT_DIR="${SCRIPT_DIR}/checkpoints"

echo "=== QuarkAudio-UniSE Checkpoint 下載腳本 ==="
echo "目標目錄：${CHECKPOINT_DIR}"
echo ""

# 建立目錄
mkdir -p "${CHECKPOINT_DIR}"

# ============================================
# 1. BiCodec（從 Spark-TTS-0.5B）
# ============================================
echo "[1/3] 下載 BiCodec..."
cd "${CHECKPOINT_DIR}"

# hf 會自動建立 BiCodec/ 子目錄
hf download SparkAudio/Spark-TTS-0.5B BiCodec/config.yaml --local-dir .
hf download SparkAudio/Spark-TTS-0.5B BiCodec/model.safetensors --local-dir .

echo "  ✅ BiCodec 下載完成"
echo ""

# ============================================
# 2. UniSE 主 checkpoint
# ============================================
echo "[2/3] 下載 UniSE 主 checkpoint..."

hf download QuarkAudio/QuarkAudio-UniSE epoch=20-step=109367.ckpt --local-dir .

echo "  ✅ UniSE checkpoint 下載完成"
echo ""

# ============================================
# 3. wav2vec2（從 facebook）
# ============================================
echo "[3/3] 下載 wav2vec2-large-xlsr-53..."

hf download facebook/wav2vec2-large-xlsr-53 --local-dir wav2vec2-large-xlsr-53

echo "  ✅ wav2vec2 下載完成"
echo ""

# ============================================
# 4. 驗證
# ============================================
echo "=== 驗證權重結構 ==="
echo ""
find "${CHECKPOINT_DIR}" -type f | sort
echo ""

if [ -f "${CHECKPOINT_DIR}/BiCodec/config.yaml" ] && \
   [ -f "${CHECKPOINT_DIR}/BiCodec/model.safetensors" ] && \
   [ -f "${CHECKPOINT_DIR}/epoch=20-step=109367.ckpt" ] && \
   [ -d "${CHECKPOINT_DIR}/wav2vec2-large-xlsr-53" ]; then
    echo "✅ 所有權重下載完成！"
else
    echo "❌ 部分權重缺失，請檢查下載過程"
    exit 1
fi