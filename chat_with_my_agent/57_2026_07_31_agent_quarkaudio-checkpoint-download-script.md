---
created: 2026-07-31
author: Vincent
type: agent
status: final
tags: [quark-audio, checkpoint-download, huggingface-cli]
---

# 2026-07-31 建立 QuarkAudio-UniSE 權重下載腳本

## What

建立 `download_checkpoints.sh` 腳本，使用 `hf` CLI 自動下載 QuarkAudio-UniSE 推理所需的所有模型權重。

## Why

官方程式碼沒有自動下載邏輯，需要手動準備：
- BiCodec（config.yaml + model.safetensors）
- UniSE 主 checkpoint（epoch=20-step=109367.ckpt）

## How

- 腳本：`serve/quark-audio/download_checkpoints.sh`
- 使用 `hf download` 搭配子路徑參數，自動建立 `BiCodec/` 目錄結構
- 關鍵技巧：`hf download <repo> <子路徑> --local-dir .` 會讓 hf 自動建立對應子目錄

### 下載命令

```bash
# BiCodec（從 Spark-TTS-0.5B）
hf download SparkAudio/Spark-TTS-0.5B BiCodec/config.yaml --local-dir .
hf download SparkAudio/Spark-TTS-0.5B BiCodec/model.safetensors --local-dir .

# UniSE 主 checkpoint
hf download QuarkAudio/QuarkAudio-UniSE epoch=20-step=109367.ckpt --local-dir .
```

### 驗證結果

```
checkpoints/
├── BiCodec/
│   ├── config.yaml
│   └── model.safetensors
└── epoch=20-step=109367.ckpt
```

結構完全符合官方預期。

## Follow-up

繼續建立測試音訊、完善 API、執行 TSE 推理。

## References

- [serve/quark-audio/download_checkpoints.sh](../../serve/quark-audio/download_checkpoints.sh)
- [serve/quark-audio/checkpoints/](../../serve/quark-audio/checkpoints/)