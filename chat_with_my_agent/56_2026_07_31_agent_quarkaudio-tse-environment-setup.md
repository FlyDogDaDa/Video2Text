---
created: 2026-07-31
author: Vincent
type: agent
status: in-progress
tags: [tse, quark-audio, uni-se, environment-setup, voice-separation]
---

# 2026-07-31 搭建 QuarkAudio-UniSE TSE 環境

## What

建立 QuarkAudio-UniSE 本地推理環境，目標是從混合音訊中分離指定說話人的語音內容（Target Speaker Extraction, TSE）。

## Why

需要可商用、本地運行的 TSE 方案，支援輸入聲紋/參考音訊並從混合音訊中提取目標說話人內容。

## 模型選型過程

系統性搜尋多個方向，找到一個後再去找更好、更新的模型：

| 模型 | 授權 | 狀態 | 備註 |
|------|------|------|------|
| **QuarkAudio-UniSE**（阿里） | Apache 2.0 ✅ | Stable | 最新（2025/10）、最全面、推薦 |
| **MeanFlow-TSE**（哥倫比亞大學） | MIT ✅ | Interspeech 2026 | 單步生成、超低延遲，但生態較小 |
| **ClearerVoice-Studio**（阿里） | Apache 2.0 ✅ | 成熟 | 音訊+視覺 TSE，純音訊需自行訓練 |
| **WeSep**（文心） | Apache 2.0 ✅ | 生產級 | 支援 ONNX/TorchScript/C++ 部署 |
| **Metis/Amphion** | CC-BY-NC ❌ | — | 權重不可商用 |
| **LauraTSE** | CC BY-NC-SA ❌ | — | 不可商用 |

**決定採用：QuarkAudio-UniSE**

### 選擇理由
- Apache 2.0 授權，可商用
- 2025 年 10 月發表（arXiv:2510.20441），架構最新
- 整合 8 種音訊任務（TSE、SR、SS、VC 等）
- Decoder-only AR-LM 骨幹，結合 WavLM + BiCodec + LM
- 官方已支援 TSE 推理流程

## How

### 1. 建立 uv 環境

- 在 `serve/quark-audio/` 建立 Python 3.10.19 venv（`.venv/`）
- 關閉 uv 安裝隔離（`--no-build-isolation`），不修改 `pyproject.toml`
- 安裝依賴：
  - `torch==2.13.0+cu130`、`torchaudio==2.13.0+cu130`（CUDA 130）
  - `pytorch-lightning`、`transformers`、`soundfile`、`omegaconf`、`librosa`、`huggingface_hub`
  - 其他 TSE 相關依賴

### 2. 取得官方程式碼

- Clone `alibaba/unified-audio` 至 `serve/quark-audio/unified-audio/QuarkAudio-UniSE/`
- 官方已提供推理腳本（`test.py`），但需調整為獨立 API

### 3. 建立 Python API 包裝

- `serve/quark-audio/quark_audio/api.py`：
  - `QuarkAudioTSE` 類別：負載模型、分段推理
  - `extract(mix_path, enroll_path, output_path)`：5 秒片段、250ms 重疊銜接
  - `extract_target_speaker()` 便捷函式
- 實作核心推理邏輯（移植官方 `test_step`，不依賴 Lightning Trainer）

### 4. pyproject.toml

- 建立 `serve/quark-audio/pyproject.toml` 定義 uv 依賴
- `build-backend = "setuptools.build_meta"`

## 決策

1. **用 uv 不用 pip**：符合專案慣例
2. **`--no-build-isolation`**：官方 repo 的 `pyproject.toml` 不需隔離建構
3. **刪除下載腳本**：直接運行推理時自動下載模型權重
4. **HF 預設快取**：wav2vec2 等模型存於 `~/.cache/huggingface`
5. **僅使用推理程式**：不需要訓練相關代碼

## Follow-up

- [ ] 下載模型權重（`checkpoints/epoch=20-step=109367.ckpt`、BiCodec）
- [ ] 建立測試音訊 `test-audio/2026_07_21_test.mp3` 和 `test-audio/speech-reference.mp3`
- [ ] 建立 `workflows/quark-audio.py` 執行 TSE 推理
- [ ] 實際執行測試並驗證結果

## References

- [serve/quark-audio/pyproject.toml](../../serve/quark-audio/pyproject.toml)
- [serve/quark-audio/quark_audio/api.py](../../serve/quark-audio/quark_audio/api.py)
- [alibaba/unified-audio](https://github.com/alibaba/unified-audio)（483⭐）
- [QuarkAudio/QuarkAudio-UniSE](https://huggingface.co/QuarkAudio/QuarkAudio-UniSE)（HuggingFace 權重）
- [SparkAudio/Spark-TTS-0.5B](https://huggingface.co/SparkAudio/Spark-TTS-0.5B)（BiCodec 權重）