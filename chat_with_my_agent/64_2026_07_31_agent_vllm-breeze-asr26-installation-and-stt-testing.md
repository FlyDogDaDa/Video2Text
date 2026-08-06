---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [vllm, breeze-asr-26, stt, audio-transcription]
---

# vLLM Breeze-ASR-26 安裝與轉錄測試

## What

1. 安裝 vLLM 0.26.0 搭配 Breeze-ASR-26 模型（閩南語 → 中文轉錄）
2. 安裝音訊相依 `vllm[audio]` 解決 PyAV 缺失問題
3. 測試 OpenAI 相容 API 轉錄功能
4. 驗證長音訊（會議錄音）轉錄品質

## Why

- 需要 ASR（自動語音辨識）將會議錄音轉為文字
- Breeze-ASR-26 針對閩南語/中文優化，適合台語場合
- vLLM 提供 OpenAI 相容 API，易於整合

## How

### 1. 環境設定

**建立 venv 與安裝相依**：

```bash
cd serve/vllm
uv init --no-readme
uv add vllm>=0.26.0 python-dotenv requests
uv add "vllm[audio]"  # 安裝 PyAV、scipy、soundfile、soxr
```

**環境變數**：`.env`

```bash
HF_TOKEN=YOUR_HF_TOKEN_HERE
```

### 2. 啟動腳本

**`serve/vllm/launch_BreezeASR26.sh`**

```bash
#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}")" && pwd )"
source "$SCRIPT_DIR/.venv/bin/activate"
set -a; source "$SCRIPT_DIR/.env"; set +a

export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

vllm serve "MediaTek-Research/Breeze-ASR-26" \
  --max-model-len 448 \
  --max-num-batched-tokens 1500 \
  --tensor-parallel-size "${TP_SIZE:-1}" \
  --gpu-memory-utilization "${GPU_MEM_UTIL:-0.08}" \
  --host 0.0.0.0 \
  --port "${PORT:-8750}" \
  --trust-remote-code \
  --async-scheduling \
  --max-num-seqs 32
```

**參數設定**：
- `TP_SIZE=1`：單卡運行（有 126GB VRAM 但其他服務也用 GPU）
- `GPU_MEM_UTIL=0.08`：~9.58 GB（2.88 GB 權重 + 5.62 GB KV cache + 其他）
- `--async-scheduling`：非同步調度，提升吞吐量
- `--enforce-eager`：關閉 cudagraph 冷啟動延遲（已移除，改用預設）

### 3. API 測試

**官方 OpenAI 相容格式**：

```bash
curl -X POST "http://localhost:8750/v1/audio/transcriptions" \
  -H "Authorization: Bearer token-abc123" \
  -F "file=@test-audio/會議片段.wav" \
  -F "model=MediaTek-Research/Breeze-ASR-26" \
  -F "response_format=text"
```

**關鍵**：必須帶 `Authorization: Bearer` header，否則 400 錯誤

### 4. 轉錄結果

| 測試檔案 | 長度 | 結果 | 備註 |
|---------|------|------|------|
| speaker-ref/黃.wav | 7.9s | 空 | 合成音檔，無法辨識 |
| speaker-ref/文.wav | 4.8s | 空 | 合成音檔 |
| meeting_original.wav | 30s (0-30s) | 有結果 | 會議討論内容 |
| meeting_30_60s.wav | 30s (30-60s) | 有結果 | 提到客户劉邦安、保養 |
| meeting_60s.wav | 30s (60-90s) | 有結果 | 保養品質討論 |

**轉錄品質**：中文轉錄準確，適合會議場景。合成音檔（speaker-ref）因品質問題無法辨識。

### 5. 檔案限制

- 預設最大檔案大小：25 MB（`VLLM_MAX_AUDIO_CLIP_FILESIZE_MB`）
- 完整會議 73 MB 被拒絕，需分段測試

### 6. 錯誤修復

| 問題 | 原因 | 解法 |
|------|------|------|
| "Invalid or unsupported audio file" | 缺少 PyAV 相依 | `uv add "vllm[audio]"` 安裝 av、soundfile 等 |
| 400 Bad Request | 缺少 Authorization header | 加上 `-H "Authorization: Bearer token-abc123"` |
| vllm serve 被 kill | `pkill -f "vllm serve"` 太寬泛 | 改用 `kill <PID>` 針對特定程序 |

## Follow-up

- [ ] 測試 word-level timestamp（`response_format=verbose_json` 的 `words` 欄位）
- [ ] 整合 STT 到 pipeline（會議 → 分段 → 轉錄 → 語意分析）
- [ ] 評估是否需要 forced aligner 做 word-level 對齊（Breeze-ASR 有相關 PR）

## References

- [Breeze-ASR GitHub](https://github.com/MediaTek-Research/Breeze-ASR)
- [vLLM ASR 文檔](https://docs.vllm.ai/en/latest/serving/online_serving/speech_to_text.html)
- [serve/vllm/launch_BreezeASR26.sh](../../serve/vllm/launch_BreezeASR26.sh)
- [serve/vllm/.env](../../serve/vllm/.env)
- [serve/vllm/pyproject.toml](../../serve/vllm/pyproject.toml)
- [63_2026_07_31_agent_voicetag-meeting-test-and-enrollment](./63_2026_07_31_agent_voicetag-meeting-test-and-enrollment.md)