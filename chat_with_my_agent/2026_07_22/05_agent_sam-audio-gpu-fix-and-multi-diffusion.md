---
created: 2026-07-22
author: FlyDogDaDa
type: agent
status: final
tags: [sam-audio, gpu-fix, long-audio, multi-diffusion]
---

# Sam-Audio 伺服器 GPU 修復與長音訊處理

## What

修復 Sam-Audio 伺服器因錯誤配置導致模型跑在 CPU 上的問題，並實作滑動視窗機制以處理長音訊分離。

## Why

伺服器雖然偵測到 GPU 可用，但音訊分離仍跑在 CPU 上，導致處理時間極長（超過 10 分鐘）。原因是 `malloc_fraction` 引數格式錯誤，導致 CUDA 初始化失敗，模型最終 fallback 到 CPU 執行。

## How

### 修復：`serve/sam-audio/api/main.py` — 移除錯誤的 allocator 配置

**問題：** 使用 `PYTORCH_CUDA_ALLOC_CONF` 設定 `malloc_fraction=0.5` 格式錯誤：
```bash
ValueError: Unrecognized key 'malloc_fraction=0.5' in CUDA allocator config.
```

**修復：** 移除不需要的 `alloc_conf` 引數，遵循官方 HuggingFace 模式：
```python
# Before (錯誤)
_ensure_model(device=SamAudioService.DEFAULT_DEVICE, alloc_conf=SamAudioService.DEFAULT_ALLOC_CONF)

# After (正確)
_ensure_model(device=SamAudioService.DEFAULT_DEVICE)
```

### 修復：`serve/sam-audio/sam_audio_core.py` — 簡化載入邏輯

移除不必要的 `alloc_conf` 引數和 `PYTORCH_CUDA_ALLOC_CONF` 環境變數設定：
```python
def _ensure_model(device: str = "cpu"):
    model = SAMAudio.from_pretrained("facebook/sam-audio-small")
    model = model.to(device).eval()
    processor = SAMAudioProcessor.from_pretrained("facebook/sam-audio-small")
```

模型 checkpoint 已經預設為 BF16，不需要額外的 fp16 轉換或記憶體配置。

### 實作：`serve/sam-audio/sam_audio_core.py` — 長音訊處理

根據 [研究員回應](https://github.com/facebookresearch/sam-audio/issues/49)，模型訓練時使用的音訊片段通常只有 **10 秒**。120 秒音訊的 OOM 問題，根源在於 DAC-VAE 編位元速率為 25 Hz，120 秒音訊會產生 3000 tokens，導致自注意力矩陣為 9M 元素，造成 GPU OOM。

解決方案：實作滑動視窗機制（Multi-diffusion processing），將長音訊切分為多個短視窗獨立處理：
- 預設視窗大小：30 秒
- 重疊區域：3 秒
- 使用三角形加權函式進行平滑過渡

關鍵修改：
```python
def separate(
    audio_path: str,
    anchors: list[list],
    description: str = "",
    speaker_output: str = None,
    residual_output: str = None,
    device: str = "cpu",
    window_seconds: float = 30.0,   # 新增引數
    overlap_seconds: float = 3.0,    # 新增引數
) -> tuple[Path, Path]:
    """Separate audio using SAM-Audio with sliding-window processing."""
```

## Follow-up

- [ ] 測試長音訊分離品質
- [ ] 確認融合後的音軌品質

## References

- [sam_audio_core.py](../serve/sam-audio/sam_audio_core.py)
- [api/main.py](../serve/sam-audio/api/main.py)
- [api/service.py](../serve/sam-audio/api/service.py)