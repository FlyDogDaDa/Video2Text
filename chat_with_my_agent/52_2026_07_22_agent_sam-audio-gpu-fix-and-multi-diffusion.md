---
created: 2026-07-22
author: FlyDogDaDa
type: agent
status: final
tags: [sam-audio, gpu-fix, long-audio, multi-diffusion, code-restructure]
---

# Sam-Audio 伺服器 GPU 修復、長音訊處理與重構計畫

## What

修復 Sam-Audio 伺服器因錯誤配置導致模型跑在 CPU 上的問題，實作長音訊分離，並規劃重構官方程式庫。

## Why

伺服器雖然偵測到 GPU 可用，但音訊分離仍跑在 CPU 上，導致處理時間極長。此外，官方程式庫年久失修、Linux 安裝不友善、且未實作論文中提到的 Multi-diffusion sliding window。

## How

### 修復：`serve/sam-audio/api/main.py` — 移除錯誤的 allocator 配置

**問題：** 使用 `PYTORCH_CUDA_ALLOC_CONF` 設定 `malloc_fraction=0.5` 格式錯誤：
```bash
ValueError: Unrecognized key 'malloc_fraction=0.5' in CUDA allocator config.
```

**修復：** 移除不需要的 `alloc_conf` 參數，遵循官方 HuggingFace 模式：
```python
# Before（錯誤）
_ensure_model(device=SamAudioService.DEFAULT_DEVICE, alloc_conf=SamAudioService.DEFAULT_ALLOC_CONF)

# After（正確）
_ensure_model(device=SamAudioService.DEFAULT_DEVICE)
```

### 修復：`serve/sam-audio/sam_audio_core.py` — 簡化載入邏輯

移除不必要的 `alloc_conf` 參數和 `PYTORCH_CUDA_ALLOC_CONF` 環境變數設定：
```python
def _ensure_model(device: str = "cpu"):
    model = SAMAudio.from_pretrained("facebook/sam-audio-small")
    model = model.to(device).eval()
    processor = SAMAudioProcessor.from_pretrained("facebook/sam-audio-small")
```

模型 checkpoint 已經預設為 BF16，不需要額外的 fp16 轉換或記憶體配置。

### 修復：`sam_audio_core.py` — 移除不存在的 API 呼叫

原始程式碼調用了 `processor.prepare_anchors(anchors)`，但 `SAMAudioProcessor` 實際上不支援此方法。官方 API 要求 anchors 直接傳入 `processor()`：

```python
# Before（錯誤）
anchors_tensor = processor.prepare_anchors(anchors)
inputs = processor(audios=[...], anchors=[anchors_tensor])

# After（正確）
inputs = processor(audios=[...], anchors=[anchors])
```

### 修復：`sam_audio_core.py` — 修正 PyTorch device 存取方式

`nn.Module` 沒有 `.device` 屬性，應該使用 `next(model.parameters()).device` 存取：

```python
# Before（錯誤）
inputs = inputs.to(model.device)

# After（正確）
model_device = next(model.parameters()).device
inputs = inputs.to(model_device)
```

### 修復：`sam_audio_core.py` — 加入 `predict_spans=False` 參數

`model.separate()` 預設行為可能不符合預期，需要明確傳入：

```python
# Before
result = model.separate(inputs)

# After
result = model.separate(inputs, predict_spans=False)
```

### 長音訊處理實作

**判斷：** 120 秒音訊的 OOM 問題，根源在於 DAC-VAE 編碼率為 25 Hz，120 秒音訊會產生 3000 tokens，導致自注意力矩陣為 9M 元素（`3000 × 3000`），GPU 顯存不足以負擔。

**實驗結論：**
- 120 秒音檔：❌ OOM（需 ~15GB，顯存不足）
- 30 秒音檔：✅ 成功分離（cuda:0）

官方論文明確提到要使用 Multi-diffusion sliding window，但**官方尚未實作**（[issue #24](https://github.com/facebookresearch/sam-audio/issues/24)、[issue #102](https://github.com/facebookresearch/sam-audio/issues/102)）。

**下一步：** 重構官方程式，建立自己版本的程式庫供人下載。

## References

- [sam_audio_core.py](../serve/sam-audio/sam_audio_core.py)
- [api/main.py](../serve/sam-audio/api/main.py)
- [api/service.py](../serve/sam-audio/api/service.py)
- [Official SAM-Audio #24](https://github.com/facebookresearch/sam-audio/issues/24)
- [Official SAM-Audio #102](https://github.com/facebookresearch/sam-audio/issues/102)