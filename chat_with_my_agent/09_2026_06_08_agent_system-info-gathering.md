---
created: 2026-06-08
author: Agent
type: agent
status: final
tags: [system-info, gpu, environment-audit]
---

# 系統環境資訊彙整

## What

收集並整理 Video2Text 專案執行環境的完整系統資訊，包括作業系統、硬體、框架版本與資源使用狀況。

## Why

專案處於推論框架選型完成（vLLM + Gemma-4-12B-qat-w4a16-ct）後的首次環境稽核階段，確認：

1. GPU 硬體規格是否足以執行量化多模態模型（12GB × 2 雙卡）
2. 各依賴框架版本是否相容
3. 系統資源是否足夠（特別是磁碟空間）
4. 為後續效能最佳化（CUDA graph、TRITON_ATTN）提供基準資料

## How

執行多項系統偵測命令：

| 專案 | 工具/命令 |
|------|-----------|
| 作業系統 | `uname -a` + `/etc/os-release` |
| Python | `python --version` |
| PyTorch | `python -c "import torch; print(...)"` |
| CUDA | `nvidia-smi` + `nvcc --version` |
| vLLM | `python -c "import vllm; print(...)"` |
| transformers | `python -c "import transformers; print(...)"` |
| 磁碟/記憶體 | `df -h` + `free -h` |

### 關鍵發現

**GPU 雙卡異質配置：**

| GPU | 型號 | VRAM | 特性 |
|-----|------|------|------|
| GPU 0 | RTX A2000 12GB | 12 GB | P0 21W / 70W，61°C |
| GPU 1 | RTX 4070 12GB | 12 GB | P8 6W / 220W，48°C |

→ 兩卡 VRAM 相同（12GB），模型量化後 ~6-8GB，TP=2 可分配。

**框架相容：**

| 套件 | 版本 | 備註 |
|------|------|------|
| Python | 3.12.10 | 專案統一版本 |
| PyTorch | 2.11.0 + cu129 | CUDA 12.9 |
| vLLM | 0.22.1 | 與 Gemma-4-12B-qat-w4a16-ct 相容 |
| transformers | 5.10.2 | 最新穩定版 |
| CUDA Toolkit | 13.0 | 驅動支援至 13.0 |

**⚠️ 磁碟空間警報：**

| 磁碟 | 總容量 | 已用 | 可用 | 使用率 |
|------|--------|------|------|--------|
| `/` (NVMe) | 467 GB | 415 GB | 29 GB | **94%** |

29GB 剩餘空間，安裝大模型權重或 uv 快取時可能再度遇到 `No space left on device`。建議定期執行 `uv cache clean`。

## Follow-up

- [ ] 監控磁碟使用率，必要時清理 uv cache 或舊專案
- [ ] 雙卡異質（A2000 + 4070）在 TP=2 時的推論效能差異需要實際測量化
- [ ] P8 狀態的 4070 效能可能被限制，確認 `nvidia-smi pstate` 設定

## References

- [08_2026_06_08_agent_gemma4-vllm-inference-fixes.md](./08_2026_06_08_agent_gemma4-vllm-inference-fixes.md) — 上一次推論修復記錄
- [pyproject.toml](../../pyproject.toml) — 依賴版本定義
- [try_video.py](08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py) — 當前可用推論指令碼
