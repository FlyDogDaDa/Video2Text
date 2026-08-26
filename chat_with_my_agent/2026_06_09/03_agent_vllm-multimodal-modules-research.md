---
created: 2026-06-09
author: Agent
type: agent
status: final
tags: [vllm, multimodal, video, audio, image, api, openai-sdk, research]
---

# vLLM 多模態模組研究（video / audio / image）

## What

研究 `vllm.multimodal.video`、`vllm.multimodal.audio`、`vllm.multimodal.image` 三個模組的內容與用法，釐清線上 API 模式與離線推理模式的差異。

## 研究成果

### `vllm.multimodal.video`

**核心資料結構：**

| 類別 | 欄位 | 用途 |
|------|------|------|
| `VideoSourceMetadata` | `total_frames_num`, `original_fps`, `duration` | 影片來源資訊 |
| `VideoTargetMetadata` | `num_frames`, `fps`, `max_duration` | 目標規格 |

**VideoBackend 家族（VideoLoader 抽象基類）：**

| Backend | 註冊名稱 | 取樣策略 |
|---------|----------|----------|
| `VideoBackend` | `"opencv"` | 均勻取樣：`num_frames` 或 `1/fps` 取少者 |
| `DynamicVideoBackend` | `"opencv_dynamic"` | 長度感知：≤ max_duration 用 fps，超長則均勻分佈 |
| `Molmo2VideoBackend` | `"molmo2"` | 針對 Molmo2 的 FPS 因子演算法 |
| `NemotronVLVideoBackend` | `"nemotron_vl"` | 繼承 VideoBackend，額外回傳 `original_video_bytes` |
| `OpenCVDynamicOpenPanguVideoBackend` | `"openpangu"` | 時間戳記基礎的均勻取樣 |

**幀解碼混合器：**

| 類別 | 用途 |
|------|------|
| `OpenCVVideoBackendMixin` | OpenCV VideoCapture 解碼，含幀恢復機制 (`frame_recovery=True`) |
| `PyAVVideoBackendMixin` | PyAV (FFmpeg) 解碼，seek + GIL 釋放，適合高併發 |

**主要 API：**

```python
# 讀取影片 → (frames_array, metadata_dict)
frames, meta = VideoBackend.load_bytes(
    data=video_bytes,       # 影片 raw bytes
    num_frames=-1,          # -1 = 全部幀
    fps=2,                  # 取樣 FPS
    max_duration=300,       # 最大長度（秒）
    backend="pyav",         # "opencv" 或 "pyav"
    frame_recovery=False,   # 幀恢復
)
# frames: np.ndarray [num_frames, H, W, 3], dtype=np.uint8
```

**輔助函式：**

```python
sample_frames_from_video(frames, num_frames=16)    # 進一步抽幀
resize_video(frames, size_factor=0.5)              # 調整解析度
```

### `vllm.multimodal.audio`

| 類別/函式 | 用途 |
|-----------|------|
| `get_audio_duration(y, sr)` | 音訊長度（秒）|
| `AudioSpec` | 規格：`target_channels`, `channel_reduction` |
| `ChannelReduction` (Enum) | `MEAN`（預設）, `FIRST`, `MAX`, `SUM` |
| `normalize_audio(audio, spec)` | 多聲道 → 目標聲道 |
| `AudioResampler` | 重取樣，支援 `pyav` / `scipy` 方法 |
| `split_audio(audio, sr, max_clip, overlap, min_energy)` | 低能量區間切割長音訊 |
| `find_split_point(wav, start, end, window)` | 找最安靜的切割點 |

**預設規格：** `MONO_AUDIO_SPEC`（1 channel, MEAN reduction）、`PASSTHROUGH_AUDIO_SPEC`（不處理）

**主要 API：**

```python
# 多聲道 → mono
mono = normalize_audio(audio_2d, AudioSpec(target_channels=1))

# 重取樣
resampler = AudioResampler(target_sr=16000, method="pyav")
resampled = resampler.resample(audio, orig_sr=48000)

# 切割長音訊
chunks = split_audio(audio, 16000, max_clip_duration_s=30, overlap_duration_s=1, min_energy_window_size=1600)
```

### `vllm.multimodal.image`

| 函式 | 用途 |
|------|------|
| `rescale_image_size(image, size_factor, transpose)` | 按比例縮放 |
| `rgba_to_rgb(image, background_color)` | RGBA → RGB，透明處用底色填充 |
| `convert_image_mode(image, to_mode)` | 通用 mode 轉換 |

**主要 API：**

```python
from PIL import Image
rescale_image_size(img, 0.5)              # 縮半
rgba_to_rgb(img_rgba, background_color)    # RGBA → RGB
convert_image_mode(img, "L")              # 轉灰階
```

## 結論：線上 API vs 離線推理

這三個模組是 vLLM **內部使用的多模態預處理工具**，不是直接給 OpenAI API 用的。

| 模式 | 如何處理多模態輸入 |
|------|-------------------|
| **線上 API** (`/v1/chat/completions`) | 使用者傳 `{"type": "video_url", ...}` → vLLM 自動呼叫這些模組預處理 |
| **離線推理** (`LLM.generate()`) | 程式碼直接呼叫 `vllm.multimodal.video.VideoBackend.load_bytes()` |

### 線上 API 多模態 content 格式（OpenAI 相容）

```json
{
  "role": "user",
  "content": [
    {"type": "video_url", "video_url": {"url": "file:///path/to/video.mp4"}},
    {"type": "text", "text": "Summarize what happens."}
  ]
}
```

### 當前狀態

- **離線推理**：✅ 三個模組在 stable v0.22.1 都有，`try_video.py` 可正常運作
- **線上 API `video_url`**：❌ 僅在 vLLM 開發 branch 支援，stable 版本尚無

## References

- `vllm/multimodal/video.py`
- `vllm/multimodal/audio.py`
- `vllm/multimodal/image.py`
- [Gemma 4 Usage Guide - vLLM Recipes](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
