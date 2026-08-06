---
created: 2026-06-07
author: Agent
type: agent
status: final
tags: [vllm, gemma4, compressed-tensors, video2text, gpu-restriction]
---

# vLLM Restore — Gemma 4 12B QAT w4a16-ct 推論

## What

- 移除 SGLang，重新安裝 vLLM 0.22.1
- 確立使用 `google/gemma-4-12B-it-qat-w4a16-ct` 模型
- 記錄 GPU 硬體限制與框架選擇的決策過程

## Why

### 框架選擇衝突

| 框架 | QAT w4a16-ct | QAT q4_0-unquantized | 12GB GPU 可用性 |
|------|:---:|:---:|:---:|
| **vLLM** | ✅ 原生設計 | ✅ 支援 | ✅ 量化後 ~6-8GB |
| **SGLang** | ❌ 不支援此格式 | ✅ 支援 | ❌ bf16 需 ~24GB |

SGLang 的 QAT 支援僅針對 `qat-q4_0-unquantized`（未量化 BF16，11.95B 參數全量載入），**無法使用壓縮格式**。

Gemma 4 12B QAT w4a16-ct 在 Hugging Face 上明確標註：
> *"QAT checkpoints serialized in the compressed-tensors format for native, optimized inference with vLLM."*

這是 Google 設計給 vLLM 的格式，壓縮後約 6-8GB VRAM，適合單卡 12GB。

### 硬體限制

| GPU | VRAM | 能跑？ |
|------|------|--------|
| RTX A2000 12GB | 12GB | ⚠️ **邊緣但可行動** — 量化模型 ~6-8GB + KV cache + 多模態 encoder |
| RTX 4070 SUPER 12GB | 12GB | ⚠️ 同上 |

SGLang unquantized（BF16）需要約 24GB，兩張卡都裝不下。

## How

### 1. 清理環境

SGLang 移除後，系統清理了 184 packages 的依賴。

```bash
uv remove sglang
```

### 2. 磁碟空間清理

安裝 vLLM 時遇到 `/` 磁碟滿（358MB 剩餘）：

```
Failed to write to file `/home/b11223209/.cache/uv/.tmpxSqmAR/torch/lib/libtorch_cpu.so`: No space left on device
```

清理 uv cache 釋放了 68.4GB：

```bash
uv cache clean
```

### 3. 重新安裝 vLLM

```bash
uv add vllm
```

安裝成功：
```
vLLM 0.22.1
```

### 4. 檔案變更

- `pyproject.toml`：移除 `sglang`，保留 `vllm`
- `.python-version`：維持 `3.12`
- `.cache/uv`：清理 68.4GB

## Deployment Command

```bash
vllm serve google/gemma-4-12B-it-qat-w4a16-ct \
  --quantization compressed-tensors \
  --gpu-memory-utilization 0.9 \
  --host 0.0.0.0 --port 8000
```

**注意：**
- 需要使用 `--gpu-memory-utilization 0.9` 以最大化利用 12GB VRAM
- 多模態 encoder（vision ~550M + audio ~300M）會額外佔用 ~1GB
- 建議 `--max-model-len` 不要太大，預留 KV cache 空間

## Key Learnings

1. **不要盲目追新框架** — SGLang main 雖然有新功能，但 `w4a16-ct` 格式是設計給 vLLM 的
2. **GPU VRAM 是硬性限制** — 12GB 卡必須用量化格式，bf16 直接排除
3. **壓縮格式 ≠ 通用支援** — compressed-tensors 目前只有 vLLM 原生支援

## Follow-up

- [ ] 測試 vLLM 能否成功載入 `gemma-4-12B-it-qat-w4a16-ct`
- [ ] 驗證多模態輸入（image + audio）是否正常工作
- [ ] 測試 vLLM Chat API 是否能與 Video2Text 無縫整合
- [ ] 評估是否可嘗試 `--quantization compressed-tensors --load-format bitsandbytes` 進一步壓縮

## References

- [pyproject.toml](../pyproject.toml)
- [01_2026_06_07_human_video2text-system-design.md](./01_2026_06_07_human_video2text-system-design.md)
- [04_2026_06_07_docs_gemma4-12b-qat-w4a16.md](./04_2026_06_07_docs_gemma4-12b-qat-w4a16.md)
- [Hugging Face — google/gemma-4-12B-it-qat-w4a16-ct](https://huggingface.co/google/gemma-4-12B-it-qat-w4a16-ct)
