---
created: 2026-06-09
author: Vincent
type: human
status: draft
tags: [vllm, gemma4, nightly, disk-space, nas, symlink, storage-optimization]
---

# Nightly vLLM installation, Gemma-4-12B spec correction, disk space analysis & NAS migration plan

## What

1. **安裝 nightly vLLM** 以修復 `num_soft_tokens` bug
2. **更正日記**：Gemma-4-12B 的 encoder-free 架構 ≠ 沒有 audio encoder
3. **掃描系統磁碟空間**：找出元兇
4. **規劃搬移檔案到 NAS**（待 NFS 掛載完成後執行）

## Why

- Stable vLLM 0.22.1 有 `'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'` bug
- 之前日記錯誤寫 "12B 沒有 audio encoder"，實為 encoder-free 架構
- `/` 分割槽 467GB 已用 440GB（94%），只剩 3.8GB
- DeepShader `runs/` (24GB) 和 StableDiffusion `models/` (5.8GB) 可搬移到 NAS

## How

1. **Nightly vLLM 安裝**
   - 新增 `[[tool.uv.index]]` 指向 `https://wheels.vllm.ai/nightly/cu129`
   - 設定 `[tool.uv.sources]` 讓 uv 從 nightly 解析 vllm
   - 初始版本：`0.22.1rc1.dev296+g2385e140d`（有 num_soft_tokens bug）
   - 新增 `hf_overrides` patch 解決 dev296 bug
   - `uv add soundfile` 後 vLLM 自動升級到 **dev301**（bug 已原生修復）
   - **問題**：安裝後遇到 `libcudnn.so.9` 錯誤 → cuDNN 9 在 PyTorch bundled
   - 嘗試安裝 → **磁碟空間不足**（`No space left on device`）
   - **解決**：`rm -rf .venv && uv cache clean` 釋放 **55GB**（3.8GB → 61GB 可用）

2. **Gemma-4-12B 規格更正**（參考 vLLM 官方指南）
   - encoder-free = 單一 decoder-only transformer 直接處理所有模態
   - 音訊：raw 16kHz waveform frames 直接投影到 LM space
   - 影片：raw pixel patches 直接投影
   - 不需要獨立的 vision/audio encoder

3. **系統磁碟掃描結果**
   - 使用者 b11223209 總用量：**156GB**
   - workspace/ = 66GB（最大元兇）
   - DeepShader `runs/` = **24GB**（訓練記錄）
   - `.cache/uv/` = 51GB（已清理，uv 套件快取）→ **釋放 55GB**
   - `.cache/huggingface/` = **13GB**（HF Hub，含 9.6GB Gemma-4-12B）
   - `.venv/` = 13GB（Video2Text）

4. **NAS 搬移清單**（待 NFS 掛載完成）
   - `DeepShader/runs/` → NAS `B11223209-銘順/DeepShader/runs/`
   - `StableDiffusion/models/` → NAS `B11223209-銘順/Models/StableDiffusion/`
   - 測試影片 → NAS `B11223209-銘順/Video2Text/測試影片/`
   - 建立 symlink 保持本地路徑不變

5. **四模態測試結果（dev301）**
   - 純文字 ✅ `Hi`
   - 圖片 ✅ `Architecture`（看到架構圖）
   - 影片 ✅ `Tutorial`（看到音樂教學影片）
   - 音訊 ✅ `**Telugu**`（intro_voice_cover.wav）

## Follow-up

- [ ] NFS 掛載完成後執行搬移（步驟 1-2 優先）
- [ ] `uv cache clean` 釋放 51GB ✅ 已執行
- [ ] 重建 `.venv` 用 nightly vLLM（13GB 釋放 + bug 修復）✅ dev301 已自動修復 bug
- [ ] 測試圖片/音訊輸入 ✅ 全部通過

## References

- [08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py](./08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py)
- [multimodal_infer.py](./16_2026_06_09_references_vllm-nightly-installation-and-storage-optimization/multimodal_infer.py)
- [pyproject.toml](../pyproject.toml)
- [Gemma 4 vLLM Recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
