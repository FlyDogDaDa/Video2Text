---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm, gemma4, fetch_video, video-frame-count, _VIDEO_MAX_FRAMES]
---

# `vllm.multimodal.utils.fetch_video` 回傳值確認 & 32 幀取樣來源調查

## What

1. 確認 `fetch_video()` 回傳值的完整結構
2. 調查 32 幀取樣數量的控制來源

## Why

影片測試成功後需要理解 `fetch_video()` 回傳的實際格式，以及為什麼是 32 幀而非其他數量。

## How

### 1. `fetch_video()` 回傳格式

```python
fetch_video(video_url) -> tuple[NDArray, dict]
```

**tuple[0] — NDArray（幀資料）：**

| 欄位 | 值 | 說明 |
|------|------|------|
| `type` | `numpy.ndarray` | NumPy 陣列 |
| `shape` | `(32, 1082, 1920, 3)` | 32 幀 × 1082 高 × 1920 寬 × 3 通道（RGB） |
| `dtype` | `uint8` | 8-bit 整數 |
| `ndim` | 4 | 4 維陣列 `[num_frames, height, width, channels]` |

**tuple[1] — metadata（元資料）：**

| 欄位 | 值 | 說明 |
|------|------|------|
| `total_num_frames` | `207785` | 原始影片總幀數 |
| `fps` | `60.0` | 影片幀率 |
| `duration` | `3463.08` | 影片長度（秒）= ~57.7 分鐘 |
| `video_backend` | `opencv` | 讀取後端 |
| `frames_indices` | `[0, 6702, 13405, ...]` | 被取樣的 32 個幀索引（等間距） |
| `do_sample_frames` | `False` | 是否啟用了自定義幀取樣（預設值） |

### 2. 計算驗證

- **幀間隔** = 207785 / 32 ≈ 6493 幀（等間距取樣）
- **每幀時長** = 1 / 60 ≈ 0.017 秒
- **總時長** = 207785 / 60 ≈ 3463 秒 ≈ 57.7 分鐘
- **取樣率** = 57.7 分鐘 / 32 幀 ≈ 每 1.8 分鐘取一幀

### 3. 32 幀來源 — 寫死在 vLLM Gemma4 模型檔案

**檔案：** `vllm/model_executor/models/gemma4_mm.py`
**常數：** `_VIDEO_MAX_FRAMES = 32`

```python
_VIDEO_MAX_FRAMES = 32  # max sampled frames per video
```

使用位置：
- `gemma4_mm.py:93` — 常數定義
- `gemma4_mm.py:259` — `num_frames = _VIDEO_MAX_FRAMES`
- `gemma4_mm.py:502` — `num_frames=_VIDEO_MAX_FRAMES`
- `gemma4_unified.py:36` — `from .gemma4_mm import _VIDEO_MAX_FRAMES`
- `gemma4_unified.py:175` — `num_frames = _VIDEO_MAX_FRAMES`

**可客製化：** 如果 `video_opts.num_frames is not None`，則 `num_frames = min(num_frames, video_opts.num_frames)`（來自 `limit_mm_per_prompt["video"]`）。

### 4. 其他相關常數

```python
_SUPPORTED_SOFT_TOKENS = (70, 140, 280, 560, 1120)  # 影像 token 預算
_VIDEO_MAX_SOFT_TOKENS = 70  # 每幀影像的 soft tokens（vs 影像 280）
```

## Follow-up

- [ ] 確認能否透過 `mm_processor_kwargs` 調整 `num_frames`
- [ ] 測試不同影片幀率對回傳值的影響

## References

- [vllm/multimodal/video.py](../../.venv/lib/python3.12/site-packages/vllm/multimodal/video.py): `VideoBackend.create_hf_metadata()`
- [vllm/multimodal/media/video.py](../../.venv/lib/python3.12/site-packages/vllm/multimodal/media/video.py): `JPEGSequenceVideoLoader.load_bytes()`
- [vllm/model_executor/models/gemma4_mm.py](../../.venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mm.py): `_VIDEO_MAX_FRAMES = 32`
- [vllm/model_executor/models/gemma4_unified.py](../../.venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_unified.py): `_VIDEO_MAX_FRAMES` import & usage
