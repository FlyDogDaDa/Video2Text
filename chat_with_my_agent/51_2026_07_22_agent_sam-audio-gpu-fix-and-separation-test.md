---
created: 2026-07-22
author: FlyDogDaDa
type: agent
status: final
tags: [sam-audio, gpu-fix, separation-test]
---

# Sam-Audio 伺服器 GPU 修復與分離測試

## What

修復 `POST /separate` 端點因預載裝置不匹配導致模型跑在 CPU 的問題，並執行實際音訊分離測試。

## Why

Lifespan 預載模型時未傳入 `device` 參數，預設使用 CPU。後續 `service.separate()` 雖指定 `cuda:0`，但 `_ensure_model()` 因快取已存在而跳過載入，導致計算全在 CPU 執行，極度緩慢。

## How

### Bug 修復：`api/main.py` — 移除 `alloc_conf` 錯誤參數

`malloc_fraction=0.5` 格式錯誤，導致 CUDA 初始化時 `ValueError: Unrecognized key 'malloc_fraction=0.5' in CUDA allocator config.`。

按照官方 HuggingFace 用法，不需要 `malloc_fraction` 或 fp16 轉換：

```python
# Before（錯誤）
_ensure_model(device=SamAudioService.DEFAULT_DEVICE, alloc_conf=SamAudioService.DEFAULT_ALLOC_CONF)

# After（正確）
_ensure_model(device=SamAudioService.DEFAULT_DEVICE)
```

### Bug 修復：`sam_audio_core.py` — 簡化載入邏輯

移除不需要的 `alloc_conf` 參數和 `PYTORCH_CUDA_ALLOC_CONF` 環境變數設定，遵循官方模式：

```python
def _ensure_model(device: str = "cpu"):
    model = SAMAudio.from_pretrained("facebook/sam-audio-small")
    model = model.to(device).eval()
```

### Bug 修復：`api/service.py` — 移除 `DEFAULT_ALLOC_CONF`

### 分離測試

| 參數 | 值 |
|------|-----|
| 音軌 | `~/文件/AudioRecording/2026_07_21_test.mp3`（120 秒） |
| 區間 | 28.750 ~ 36.618 秒 |
| 提示 | "vocal" |
| 裝置 | cuda:0 |

### 關鍵檔案

| 檔案 | 動作 | 說明 |
|------|------|------|
| `api/main.py` | 修改 | lifespan 預載改用 `cuda:0` + `alloc_conf` |
| `sam_audio_core.py` | 修改 | 移除 `process_anchors()`、修正 `model.device` |

## Follow-up

- [ ] 確認分離後的音軌品質
- [ ] 確認 `sam-audio` 模組整合到主專案 pipeline

## References

- [sam_audio_core.py](../serve/sam-audio/sam_audio_core.py)
- [api/main.py](../serve/sam-audio/api/main.py)
- [api/service.py](../serve/sam-audio/api/service.py)