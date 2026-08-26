---
created: 2026-06-10
author: Agent
type: agent
status: draft
tags: [slice-utilities, audio-extraction, video-frame-sampling, vllm, gemma4, memory-cache]
---

# Slice utilities implementation — audio/video extraction, window slicing, memory caching

## What

實作 `src/utils/slice.py` 完整 slice 工具模組，解決 vLLM 預設行為與 System Design (`01_2026_06_07_human_video2text-system-design.md`) 的差距。模組包含：

1. 視窗切片（30s 視窗 + 2s 重疊）
2. 切片感知音訊提取（≤30s mono clips，split 超長音訊）
3. 切片感知影片幀提取（1 fps，seek-buffering 避免每 slice 重開）
4. 可選記憶體快取（`cache_frames` / `cache_audio` 引數控制）

## Why

vLLM 內建模組在面對 1 小時影片時有三大問題：

| 問題 | vLLM 預設行為 | 造成的影響 |
|------|---------------|------------|
| 影片 60fps 等間距抽 32 幀 | `np.linspace(0, 207784, 32)` | 幀間隔 ~108 秒，每 1.8 分鐘才取一幀，幾乎錯過所有場景變化 |
| 全片音軌一次讀入不切割 | `sf.read(full_file)` | 1 小時音訊 >30s 模型限制，僅輸出 warning 但不截斷不切分 |
| 無視窗/切片機制 | 一次送完整影片 | 無從匹配 System Design 的 30s window + sliding step |

System Design 要求：
- 30 秒視窗 + 滑動步長（window − overlap）
- 音訊 Mono 混音，≤30s 片段
- 1 FPS 視覺抽幀
- 支援 1 小時以上影片不崩潰

## How

### 1. 核心資料結構

```
src/utils/
├── __init__.py          # 匯出所有 public API
└── slice.py             # 核心實作 (~620 行)
```

#### SliceSource — 單一視窗的 media payload

```python
@dataclass(frozen=True)
class SliceSource:
    time_range: tuple[float, float]  # (start, end) seconds
    frames: npt.NDArray | None        # [N, H, W, 3] uint8 RGB
    audio_clips: list[np.ndarray]     # 1-D mono, 16kHz, each ≤30s
```

#### SliceParams — 視窗引數（預設符合 System Design）

```python
@dataclass
class SliceParams:
    window_seconds: float = 30.0   # 視窗大小
    overlap_seconds: float = 2.0   # 重疊量
    sample_fps: float = 1.0        # 抽幀 FPS

    @property
    def step_seconds(self) -> float:
        return max(self.window_seconds - self.overlap_seconds, 0.1)
```

#### VideoInfo — 影片元資料

```python
@dataclass(frozen=True)
class VideoInfo:
    duration: float    # seconds
    fps: float         # original frame rate
    width: int
    height: int
    total_frames: int
    path: str
```

### 2. 幀提取 — VideoReader seek-buffering

**關鍵設計：** `VideoReader` 保持單一 `cv2.VideoCapture` handle 開啟，快取最後抓到的 frame 編號。相鄰 slice 讀取只做 forward grab，不需要重新 seek。

```python
class VideoReader:
    """Single-handle OpenCV video reader with seek-buffering.
    
    Consecutive reads within SEEK_THRESHOLD_FRAMES=300 只做 forward grab.
    大於 300 frames 的跳躍才重新 seek。
    """
    SEEK_THRESHOLD_FRAMES: ClassVar[int] = 300

    def read_frames(self, start, end, max_frames=32) -> np.ndarray:
        # 判斷是否重 seek
        if abs(start_frame - self._last_frame) > self.SEEK_THRESHOLD_FRAMES:
            _ = self._cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        # Forward grab + selective retrieve
        ...
```

**不使用 `extract_frames_slice`**（每次開關 VideoCapture 的 single-use helper），而是在批次處理時用 `SliceStore` 共用 `VideoReader`。

### 3. 音訊提取 — soundfile range read

```python
def extract_audio_slice(path, start, end, max_clip_duration=30.0) -> list[np.ndarray]:
    # soundfile.read() 支援 start/stop sample index
    data, _ = _sf.read(
        path,
        samplerate=_AUDIO_SAMPLE_RATE,  # 16000
        dtype="float32",
        start=start_sample,              # int(start * 16000)
        stop=end_sample,                 # int(end * 16000)
    )
    # stereo → mono (mean)
    if data.ndim > 1:
        data = data.mean(axis=1)
    # normalize to [-1, 1]
    peak = float(np.abs(data).max())
    if peak > 0:
        data = data / peak
    # split into ≤30s chunks
    if len(data) > _AUDIO_SAMPLE_RATE * max_clip_duration:
        chunks = split_evenly(data, max_clip_duration)
        return chunks
    return [data]
```

**與 vLLM `multimodal_infer.py` 的差異：**

| | `multimodal_infer.py` | `slice.py` |
|---|---|---|
| 讀取方式 | 全片讀入 `sf.read()` | `sf.read(start=, stop=)` 只讀所需區段 |
| stereo→mono | `data.mean(axis=1)` | 同上 |
| normalize | `vllm.multimodal.audio.normalize_audio()` | 自實作 `[-1, 1]` 等價邏輯 |
| 超長處理 | ❌ 無 | ✅ 自動切分成 ≤30s |

### 4. SliceStore — context manager 管理模式

```python
class SliceStore:
    """Manages optional in-memory caching + batch slice extraction."""

    def __init__(self, path, cache_frames=False, cache_audio=False):
        ...
        self._video_reader: VideoReader | None = None  # reused across slices

    # -- lifecycle (context manager) ----------------------------------
    def open(self) -> "SliceStore":
        self._video_reader = VideoReader(self.path)
        return self

    def __enter__(self) -> "SliceStore":
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- public API ---------------------------------------------------
    def extract_slice(self, start, end, max_frames=32) -> SliceSource:
        # Frames: cached buffer OR shared VideoReader OR single-use fallback
        if self._cache_frames and self._cached_frames is not None:
            ...  # sub-sample from full frame stack
        elif self._video_reader is not None:
            frames = self._video_reader.read_frames(start, end, max_frames)
        else:
            frames = extract_frames_slice(self.path, start, end, max_frames)
        # Audio: cached OR lazy range read
        ...
```

**使用方式（推薦）：**

```python
with SliceStore(path, cache_audio=True) as store:
    for src in store.iter_slices():
        frames = src.frames
        for clip in src.audio_clips:
            ...
```

### 5. 記憶體快取設計

| 快取選項 | 1 小時影片用量 | 適用場景 |
|---|---|---|
| 無快取 | ~0（每次 seek 開關，但 VideoReader 共用 handle）| 1 小時以上影片 |
| `cache_audio=True` | ~230 MB（16kHz mono float32）| 推薦，RAM 需求低 |
| `cache_frames=True` | 數 GB（全幀堆疊）| 不建議，>10 分鐘影片不適合 |

### 6. `create_slices()` — 最簡入口

```python
def create_slices(
    video_path: str,
    params: SliceParams | None = None,
    cache_frames: bool = False,
    cache_audio: bool = False,
) -> list[SliceSource]:
    """One-liner: split video and extract media for each slice."""
    store = SliceStore(video_path, cache_frames=cache_frames, cache_audio=cache_audio)
    with store.open():
        return store.iter_slices(params)
```

## Follow-up

- [ ] **Run validation tests** — `tests/test_slice_utils.py` 尚未執行（terminal 在寫入期間卡住，需重新建立環境後測試）
- [ ] **Test with real 1-hour video** — `/home/b11223209/workspace/ProgramDevelopment/Video2Text/2026_05_11-19_18_26_louder4x.mp4`（57.7 min, 60fps, 207785 frames）
- [ ] **Integrate with `multimodal_infer.py`** — 替換掉 `fetch_video()` 全片邏輯，改用 slice-aware 提取
- [ ] **Benchmark seek performance** — 驗證 seek-buffering vs 每 slice 重開的差距（預期 70+ slices × forward grab vs 70+ seeks）

## References

- [src/utils/slice.py](../../src/utils/slice.py) — 本實作
- [src/utils/__init__.py](../../src/utils/__init__.py) — 公共 API 出口
- [01_2026_06_07_human_video2text-system-design.md](./01_2026_06_07_human_video2text-system-design.md) — System Design 規格（視窗 30s、重疊 2s、mono audio、1fps）
- [18_vllm_audio_extraction_logic.md](./18_vllm_audio_extraction_logic.md) — vLLM 音訊/影片預設行為調查
- [.venv/lib/.../vllm/multimodal/video.py](../.venv/lib/python3.12/site-packages/vllm/multimodal/video.py) — vLLM 幀取樣邏輯
- [.venv/lib/.../vllm/multimodal/audio.py](../.venv/lib/python3.12/site-packages/vllm/multimodal/audio.py) — vLLM 音訊處理模組
- [.venv/lib/.../vllm/model_executor/models/gemma4_mm.py](../.venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mm.py) — `_VIDEO_MAX_FRAMES=32`、`audio_seq_length=750`、`audio_ms_per_token=40`
- [multimodal_infer.py](../src/inference/multimodal_infer.py) — 現有推論指令碼（需整合 slice utilities）
