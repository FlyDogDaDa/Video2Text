# vLLM 音訊提取邏輯與 1 小時影片預設行為調查

## 1. 音訊處理管道

### 1.1 在 `multimodal_infer.py` 中的音訊載入

```python
# multimodal_infer.py:155-168
import soundfile as sf
from vllm.multimodal.audio import AudioResampler, normalize_audio

data, sr = sf.read(audio_path, samplerate=16000)   # ① 以 16kHz 讀取
if len(data.shape) > 1:                              # ② Stereo → Mono
    data = data.mean(axis=1)
data = normalize_audio(data)                         # ③ 歸一化到 [-1, 1]
```

### 1.2 vLLM 內部 `vllm.multimodal.audio` 模組

| 函式 / 類別 | 功能 |
|---|---|
| `normalize_audio(audio, spec)` | 多聲道 → mono，使用 `ChannelReduction.MEAN`（平均值）|
| `AudioResampler.resample(audio, orig_sr)` | 重取樣至 target_sr（支援 pyav / scipy 兩種方法）|
| `split_audio(audio, sr, max_clip, overlap, min_energy)` | **切割長音訊**：在低能量區間切斷，支援 overlap |
| `find_split_point(wav, start, end, min_energy_window)` | 在搜尋區間找最安靜的切割點（RMS energy）|

**注意：** 在 `multimodal_infer.py` 的音訊載入邏輯中，**只做了 ①16kHz 讀取 + ②stereo→mono + ③normalize，沒有呼叫 `split_audio()`**。

### 1.3 30 秒限制來源

Gemna-4 音訊處理的 **30 秒上限是模型 processor 設定的**，不是程式碼強制截斷：

| 常數 | 值 | 用途 |
|---|---|---|
| `audio_seq_length` | 750 | audio token 的最大長度 |
| `audio_ms_per_token` | 40 ms | 每個 token 對應 40 毫秒音訊 |
| **max audio duration** | **750 × 40 / 1000 = 30.0 秒** | 硬限制 |

當音訊超過 30 秒時，vLLM 僅輸出 warning：

```python
# gemma4_mm.py:693-707
if duration_s > max_duration_s:
    logger.warning(
        "Audio duration exceeds max: %f > %f seconds",
        duration_s, max_duration_s,
    )
```

**不會自動截斷或切分。** 超過 30 秒的音訊仍會傳入模型，但會超出 `audio_seq_length` 限制，導致 token 被截斷或處理錯誤。

---

## 2. 影片處理管道

### 2.1 幀取樣邏輯

```python
# fetch_video(video_url) → (frames: NDArray, metadata: dict)
# vllm/multimodal/video.py: VideoBackend.compute_frames_index_to_sample()
```

**取樣流程：**

```
原始影片 (60fps, 1小時, 207785幀)
    │
    ▼
VideoSourceMetadata(total_frames=207785, fps=60, duration=3463s)
    │
    ▼
VideoTargetMetadata(num_frames=32, fps=2, max_duration=...)
    │                    ↑              ↑
    │                    │              └─ 影片原始長度
    │                    └─ 取樣目標 FPS
    ▼
compute_frames_index_to_sample()
    → np.linspace(0, 207784, 32) ≈ [0, 6702, 13405, ...]
    └─ 等間距取樣，幀間隔 ≈ 6493 幀 ≈ 108 秒
    │
    ▼
frames: np.ndarray [32, 1082, 1920, 3]  # uint8, RGB
metadata: {
    "total_num_frames": 207785,
    "fps": 60.0,
    "duration": 3463.08,
    "video_backend": "opencv",
    "frames_indices": [0, 6702, 13405, ...],  # 32 個索引
    "do_sample_frames": False
}
```

### 2.2 32 幀限制來源

寫死在 vLLM Gemma-4 模型檔案中：

```python
# gemma4_mm.py:93
_VIDEO_MAX_FRAMES = 32  # max sampled frames per video
```

同時在 `gemma4_unified.py` 中也引用此常數。這是最終傳入模型的幀數上限。

### 2.3 影片長度限制

| 來源 | 限制 |
|---|---|
| `_VIDEO_MAX_FRAMES` | 32 幀（寫死） |
| `fps` 預設值 | 2（`VideoBackend.load_bytes` 的預設 `sampling_fps`） |
| 實際 FPS | **1 fps**（Gemma-4 unified 模型使用 1fps 取樣） |
| 有效涵蓋時長 | 32 幀 × 1s = 32 秒的「內容視窗」|
| 原始影片長度 | **任意**（1 小時也可以，只是 99% 的畫面被跳過）|

**關鍵數字：** 60fps 影片 → 等間距抽 32 幀 → **每 ~1.8 分鐘抽一幀**

---

## 3. 面對 1 小時影片的完整預設行為

```
輸入：--video 1hr.mp4 --audio 1hr.mp4
         │                    │
         ▼                    ▼
    等間距抽 32 幀         soundfile 16kHz 全音軌讀取
    幀間隔 ~108s           stereo → mono (mean)
    格式 [32, H, W, 3]     normalize [-1, 1]
                              │
                              ▼
                       ⚠️ 超過 30s → 輸出 warning
                       （無自動截斷/切分）
```

### 3.1 視覺部分

| 專案 | 值 |
|---|---|
| 抽取幀數 | **32 幀**（固定上限 `_VIDEO_MAX_FRAMES`）|
| 取樣方式 | **等間距**（`np.linspace`）|
| 幀間隔 | ~108 秒（對於 1 小時影片）|
| 解碼後端 | OpenCV（預設）|
| 幀恢復 | `frame_recovery=True`（容錯）|

### 3.2 音訊部分

| 專案 | 值 |
|---|---|
| 讀取樣本率 | **16kHz**（寫死在 `sf.read(samplerate=16000)`）|
| 聲道處理 | **stereo → mono**（`data.mean(axis=1)`）|
| 歸一化 | `normalize_audio()` → [-1, 1]|
| 長度限制 | **30 秒**（`audio_seq_length=750` × `audio_ms_per_token=40ms`）|
| 超長處理 | ⚠️ **只輸出 warning，不截斷不切分** |
| 切割工具 | `split_audio()` 存在但 **此指令碼未呼叫** |

---

## 4. 與 System Design 檔案的差距

| 設計檔案期望 | 目前實作 | 差距 |
|---|---|---|
| 視窗大小 30 秒 | 影片直接丟全片（32 幀等間距） | ❌ 無視窗切片邏輯 |
| 音訊 Mono 混音 | ✅ stereo → mono (mean) | ✅ 符合 |
| 1 FPS 視覺抽幀 | ✅ 1 fps（Gemma4 unified 內部設定） | ✅ 符合 |
| 音訊切割長音訊 | ❌ 未使用 `split_audio()` | ❌ 1 小時音訊會超 30s 限制 |
| 滑動視窗處理 | ❌ 一次送完整影片 | ❌ 沒有 window/slice 機制 |

---

## 5. 建議與 follow-up

1. **音訊超長問題**：若需處理超過 30 秒的音訊，需自行呼叫 `vllm.multimodal.audio.split_audio()` 切割成 ≤30s 的片段再逐段送模型。

2. **視窗切片**：目前 `multimodal_infer.py` 是「一鍵送全片」模式，缺乏 design doc 中定義的 30 秒視窗 + 滑動步長機制。需自行實作切片邏輯。

3. **幀取樣可客製化**：透過 `limit_mm_per_prompt={"video": N}` 可調整 `num_frames`，但 `_VIDEO_MAX_FRAMES=32` 是模型層級上限。
