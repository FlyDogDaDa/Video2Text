"""
Slice utilities — audio extraction, video frame sampling, window slicing.

This module implements the slice-level audio/video extraction logic that
vLLM's built-in helpers do **not** provide for per-slice windows:

  - vLLM ``fetch_video()`` samples a full video into 32 frames with no
    slice-aware time-range support.
  - vLLM's audio loading reads the **entire** audio file with no splitting
    for clips longer than the 30-second model limit.

Here we provide a ``SliceStore`` that manages slice generation, optional
in-memory caching, and slice-aware audio/frame extraction compatible with
Gemma-4's constraints (16 kHz mono audio ≤30 s, 1 fps video ≤32 frames).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final

import numpy as np
import numpy.typing as npt
from scipy.signal import resample as _resample

if TYPE_CHECKING:
    from typing import Any as Cv2VideoCapture

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemma-4 hard constraints
# ---------------------------------------------------------------------------

_AUDIO_SAMPLE_RATE: Final[int] = 16_000
_AUDIO_MAX_SAMPLES: Final[int] = _AUDIO_SAMPLE_RATE * 30  # 30 s @ 16kHz
_VIDEO_MAX_FRAMES: Final[int] = 32
_DEFAULT_FPS: Final[float] = 1.0  # 1 frame per second

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VideoInfo:
    """Read-only metadata extracted from a video file."""

    duration: float  # seconds
    fps: float  # original frame rate
    width: int
    height: int
    total_frames: int
    path: str


@dataclass
class SliceParams:
    """Parameters controlling how a video is split into slices."""

    window_seconds: float = 30.0
    overlap_seconds: float = 2.0
    sample_fps: float = _DEFAULT_FPS

    @property
    def step_seconds(self) -> float:
        """Sliding step = window − overlap."""
        return max(self.window_seconds - self.overlap_seconds, 0.1)

    @property
    def max_frames(self) -> int:
        """Max frames per slice, capped by Gemma-4 hard limit."""
        frames = int(self.window_seconds * self.sample_fps)
        return min(frames, _VIDEO_MAX_FRAMES)


@dataclass(frozen=True)
class SliceSource:
    """One slice's extracted media ready for vLLM multimodal input."""

    time_range: tuple[float, float]  # (start, end) in seconds
    frames: npt.NDArray | None = None  # [num_frames, H, W, 3] uint8 RGB
    audio_clips: list[np.ndarray] = field(default_factory=list)


@dataclass
class SliceResult:
    """Result object produced by ``create_slices`` for each window."""

    time_range: tuple[float, float]
    frames: npt.NDArray | None
    audio_clips: list[np.ndarray]
    # Placeholder — caller fills in the LLM response later.
    llm_output: dict | None = None

    @classmethod
    def from_source(
        cls, src: SliceSource, *, llm_output: dict | None = None
    ) -> SliceResult:
        return cls(
            time_range=src.time_range,
            frames=src.frames,
            audio_clips=src.audio_clips,
            llm_output=llm_output,
        )


# ---------------------------------------------------------------------------
# Video info (OpenCV — optional dependency)
# ---------------------------------------------------------------------------

_cv2: Any = None
_HAS_CV2 = False

try:
    import cv2 as _cv2  # noqa: PLC-0414 (module-level optional import)

    _HAS_CV2 = True
except ImportError:
    pass


def load_video_info(path: str) -> VideoInfo:
    """Return ``VideoInfo`` for *path* without loading any frames into memory."""
    if not _HAS_CV2:
        raise ImportError("OpenCV (cv2) is required for video metadata extraction.")

    cap = _cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")

    total_frames = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(_cv2.CAP_PROP_FPS)
    width = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))

    # Duration: prefer the value derived from total_frames / fps when both are valid
    if fps > 0 and total_frames > 0:
        duration = total_frames / fps
    else:
        duration = cap.get(_cv2.CAP_PROP_DURATION) / 1000.0  # cv2 returns ms

    cap.release()

    return VideoInfo(
        duration=duration,
        fps=fps,
        width=width,
        height=height,
        total_frames=total_frames,
        path=str(path),
    )


# ---------------------------------------------------------------------------
# Frame extraction — reusable VideoReader (single handle, seek buffer)
# ---------------------------------------------------------------------------


class VideoReader:
    """Single-handle OpenCV video reader with seek-buffering.

    Keeps one ``cv2.VideoCapture`` open and caches the last seek position.
    Consecutive reads that are near the previous seek point only do forward
    frame grabs instead of re-seeking from frame 0.

    This is essential for slice-based extraction on long videos: without it
    each slice would open/close the file and seek from the beginning.
    """

    SEEK_THRESHOLD_FRAMES: ClassVar[int] = 300  # re-seek if gap > this many frames

    def __init__(self, path: str) -> None:
        self.path = path
        self._cap: "Cv2VideoCapture" = _cv2.VideoCapture(path)  # type: ignore[arg-type]
        if not self._cap.isOpened():
            raise ValueError(f"Cannot open video: {path}")
        self._fps: float = self._cap.get(_cv2.CAP_PROP_FPS) or _DEFAULT_FPS
        self._total_frames: int = int(self._cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        self._width: int = int(self._cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        self._height: int = int(self._cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        self._last_frame: int = -1  # frame number we last grabbed from

    # -- public -----------------------------------------------------------

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    def read_frames(
        self,
        start: float,
        end: float,
        max_frames: int = _VIDEO_MAX_FRAMES,
    ) -> np.ndarray:
        """Grab frames at ~1 fps in [start, end) using the seek-buffer."""
        start_frame = max(0, int(start * self._fps))
        end_frame = min(self._total_frames, int(end * self._fps))

        if end_frame <= start_frame:
            return np.empty((0, self._height, self._width, 3), dtype=np.uint8)

        # Decide whether to seek or grab forward
        if abs(start_frame - self._last_frame) > self.SEEK_THRESHOLD_FRAMES:
            _ = self._cap.set(_cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Grab forward
        num_indices = min(int(end - start), max_frames)
        indices = np.linspace(start_frame, end_frame - 1, num_indices, dtype=int)
        indices = np.unique(np.clip(indices, start_frame, end_frame - 1))
        idx_set = set(indices.tolist())

        frames_list: list[np.ndarray] = []
        for frame_no in range(self._last_frame + 1, end_frame + 1):
            ok = self._cap.grab()
            if not ok:
                continue
            if frame_no in idx_set:
                ret, frame = self._cap.retrieve()
                if ret and frame is not None:
                    frames_list.append(_cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB))
            self._last_frame = frame_no
            if frame_no >= end_frame:
                break

        if not frames_list:
            return np.empty((0, self._height, self._width, 3), dtype=np.uint8)

        return np.stack(frames_list)

    def release(self) -> None:
        self._cap.release()

    def __del__(self) -> None:
        self.release()


def extract_frames_slice(
    path: str,
    start: float,
    end: float,
    max_frames: int = _VIDEO_MAX_FRAMES,
) -> np.ndarray:
    """Extract frames at ~1 fps within [start, end) — single-use helper.

    Creates a temporary ``VideoReader``, reads the slice, then closes it.
    For batch slicing use ``SliceStore`` directly (it reuses one reader).
    """
    if start >= end:
        return np.empty((0, 0, 0, 3), dtype=np.uint8)

    reader = VideoReader(path)
    try:
        return reader.read_frames(start, end, max_frames)
    finally:
        reader.release()


# ---------------------------------------------------------------------------
# Audio/video backends (optional dependencies)
# ---------------------------------------------------------------------------

_sf: Any = None
_HAS_SF = False

try:
    import soundfile as _sf  # noqa: PLC-0414

    _HAS_SF = True
except ImportError:
    pass

_av: Any = None
_HAS_AV = False

try:
    import av as _av  # noqa: PLC-0414

    _HAS_AV = True
except ImportError:
    pass


def _normalize_audio(data: np.ndarray) -> np.ndarray:
    """Mono-mix (mean) and normalise to [-1, 1].

    Mirrors ``vllm.multimodal.audio.normalize_audio`` + ``normalize_audio``
    from ``multimodal_infer.py`` for consistency.
    """
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.abs(data).max())
    if peak > 0:
        data = data / peak
    return data


def extract_audio_slice(
    path: str,
    start: float,
    end: float,
    max_clip_duration: float = 30.0,
) -> list[np.ndarray]:
    """Extract audio within [start, end), 16 kHz mono, clipped to ≤30 s.

    Uses PyAV to open the video container, seek to the requested time
    range, decode audio samples, and resample to 16 kHz.  Avoids loading
    the entire file into memory.  Returns a list of 1-D ``np.ndarray``
    of dtype ``float32``.  If the slice duration exceeds 30 s it is
    split into ≤30 s segments.
    """
    if not _HAS_AV:
        raise ImportError("av (PyAV) is required for audio extraction from video.")

    if start >= end:
        return []

    with _av.open(path) as container:
        # Find the first audio stream
        audio_stream = None
        for stream in container.streams.audio:
            audio_stream = stream
            break
        if audio_stream is None:
            return []

        # Seek to start position
        container.seek(int(start * 1_000_000), stream=audio_stream)

        # Decode frames in [start, end)
        all_samples: list[np.ndarray] = []
        for frame in container.decode(audio_stream):
            # frame.pts is in stream timebase; convert to seconds
            frame_time = frame.pts * frame.time_base / _av.time_base
            if frame_time is not None and frame_time >= end:
                break
            if frame_time is not None and frame_time >= start:
                # frame.to_ndarray(): shape (num_samples, channels) float32 (fltp)
                arr = frame.to_ndarray().astype(np.float32)
                all_samples.append(arr)

        if not all_samples:
            return []

        # Each arr is (num_samples, channels). Mono-mix per frame, then concatenate.
        mono = [arr.mean(axis=1) for arr in all_samples]  # list of (num_samples,)
        raw_audio = np.concatenate(mono)

        # Get original sample rate
        orig_sr = int(audio_stream.sample_rate)

    # Resample to 16 kHz if needed
    if orig_sr != _AUDIO_SAMPLE_RATE:
        n_out = int(len(raw_audio) * _AUDIO_SAMPLE_RATE / orig_sr)
        raw_audio = _resample(raw_audio, n_out, axis=0)

    raw_audio = _normalize_audio(raw_audio)

    # If within limit, return as-is
    if len(raw_audio) <= _AUDIO_SAMPLE_RATE * max_clip_duration:
        return [raw_audio]

    # Split into ≤30 s chunks.
    chunk_samples = int(_AUDIO_SAMPLE_RATE * max_clip_duration)
    chunks: list[np.ndarray] = []
    for i in range(0, len(raw_audio), chunk_samples):
        chunks.append(raw_audio[i : i + chunk_samples])
    return chunks


# ---------------------------------------------------------------------------
# In-memory caching + batch slicing
# ---------------------------------------------------------------------------


class SliceStore:
    """Manages optional in-memory caching of video data.

    For videos up to ~10 min at 1 fps the full frame stack fits in memory.
    Audio at 16 kHz mono uses ~64 KB/s.  A 1-hour file ≈ 230 MB.

    The ``VideoReader`` handle is kept alive across slices so consecutive
    slices grab forward instead of re-seeking — critical for 1-hour videos
    with 70+ slices.

    Usage (recommended — context manager):

    .. code-block:: python

        with SliceStore(path, cache_audio=True) as store:
            for src in store.iter_slices():
                frames = src.frames
                for clip in src.audio_clips:
                    ...

    Usage (manual open/close):

    .. code-block:: python

        store = SliceStore(path)
        store.open()
        try:
            src = store.extract_slice(0, 30)
        finally:
            store.close()
    """

    def __init__(
        self,
        path: str,
        *,
        cache_frames: bool = False,
        cache_audio: bool = False,
    ) -> None:
        self.path = path
        self.info: VideoInfo | None = None
        self._cached_frames: npt.NDArray | None = None
        self._cached_audio: npt.NDArray | None = None
        self._cache_frames = cache_frames
        self._cache_audio = cache_audio
        self._video_reader: VideoReader | None = None

    # -- helpers -----------------------------------------------------------

    def _ensure_info(self) -> VideoInfo:
        if self.info is None:
            self.info = load_video_info(self.path)
        return self.info

    def _ensure_frames(self) -> npt.NDArray:
        """Load ALL frames into memory (expensive — use only with cache_frames=True)."""
        if self._cached_frames is not None:
            return self._cached_frames

        info = self._ensure_info()
        cap = _cv2.VideoCapture(self.path)  # type: ignore[arg-type]
        frames: list[np.ndarray] = []
        while True:
            ok = cap.grab()
            if not ok:
                break
            ret, frame = cap.retrieve()
            if ret and frame is not None:
                frames.append(_cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB))
        cap.release()

        if not frames:
            self._cached_frames = np.empty(
                (0, info.height, info.width, 3), dtype=np.uint8
            )
        else:
            self._cached_frames = np.stack(frames)
        return self._cached_frames

    def _ensure_audio(self) -> np.ndarray:
        """Load full audio into memory (cache_audio=True)."""
        if self._cached_audio is not None:
            return self._cached_audio

        data, _ = _sf.read(self.path, samplerate=_AUDIO_SAMPLE_RATE, dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)
        self._cached_audio = _normalize_audio(data)
        return self._cached_audio

    # -- lifecycle -------------------------------------------------------

    def open(self) -> "SliceStore":
        """Open the ``VideoReader`` for batch slice extraction."""
        self._video_reader = VideoReader(self.path)
        return self

    def __enter__(self) -> "SliceStore":
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Release the ``VideoReader``."""
        if self._video_reader is not None:
            self._video_reader.release()
            self._video_reader = None

    # -- public API ------------------------------------------------------

    @property
    def has_cached_frames(self) -> bool:
        return self._cached_frames is not None

    @property
    def has_cached_audio(self) -> bool:
        return self._cached_audio is not None

    @property
    def audio_size_mb(self) -> float:
        """Estimated audio size in MB if cached."""
        if self._cached_audio is not None:
            return self._cached_audio.nbytes / (1024 * 1024)
        info = self._ensure_info()
        return info.duration * _AUDIO_SAMPLE_RATE * 4 / (1024 * 1024)

    def extract_slice(
        self,
        start: float,
        end: float,
        max_frames: int = _VIDEO_MAX_FRAMES,
        max_clip_duration: float = 30.0,
    ) -> SliceSource:
        """Return a ``SliceSource`` for the time range [start, end)."""
        # Ensure caches
        if self._cache_frames and self._cached_frames is None:
            self._ensure_frames()
        if self._cache_audio and self._cached_audio is None:
            self._ensure_audio()

        # Frames — use the shared VideoReader or the cached buffer
        frames: npt.NDArray | None = None
        if self._cache_frames and self._cached_frames is not None:
            info = self._ensure_info()
            fps = max(info.fps, 1.0)
            start_frame = int(start * fps)
            end_frame = int(end * fps)
            if start_frame < self._cached_frames.shape[0]:
                chunk = self._cached_frames[start_frame:end_frame]
                if len(chunk) > 0:
                    num_frames = min(len(chunk), max_frames)
                    if num_frames > 0:
                        step = max(len(chunk) // num_frames, 1)
                        indices = list(range(0, len(chunk), step))[:max_frames]
                        frames = self._cached_frames[indices]
                    else:
                        frames = chunk[:max_frames]
        elif self._video_reader is not None:
            # Reuses the shared reader with seek-buffering
            frames = self._video_reader.read_frames(start, end, max_frames)
        else:
            # Fallback: single-use reader (opens/closes per slice)
            frames = extract_frames_slice(self.path, start, end, max_frames)

        # Audio
        audio_clips: list[np.ndarray] = []
        if self._cache_audio and self._cached_audio is not None:
            data = self._cached_audio
            start_sample = int(start * _AUDIO_SAMPLE_RATE)
            end_sample = int(end * _AUDIO_SAMPLE_RATE)
            chunk = data[start_sample:end_sample]
            if len(chunk) > 0:
                chunk_samples = int(_AUDIO_SAMPLE_RATE * max_clip_duration)
                for i in range(0, len(chunk), chunk_samples):
                    audio_clips.append(chunk[i : i + chunk_samples])
        else:
            audio_clips = extract_audio_slice(
                self.path, start, end, max_clip_duration=max_clip_duration
            )

        return SliceSource(
            time_range=(start, end),
            frames=frames,
            audio_clips=audio_clips,
        )

    def iter_slices(
        self,
        params: SliceParams | None = None,
    ) -> list[SliceSource]:
        """Iterate over all slices from 0 to video end.

        Requires ``open()`` to have been called (or used as context manager).
        """
        if self._video_reader is None:
            raise RuntimeError(
                "Call store.open() or use `with SliceStore(...)` before iter_slices()."
            )
        if params is None:
            params = SliceParams()

        info = self._ensure_info()
        slices: list[SliceSource] = []
        t = 0.0
        while t < info.duration:
            end = min(t + params.window_seconds, info.duration)
            if end - t < 0.5:
                break
            src = self.extract_slice(t, end, max_frames=params.max_frames)
            slices.append(src)
            t += params.step_seconds
        return slices

    def __repr__(self) -> str:
        flags = []
        if self._cache_frames:
            flags.append(
                "frames=CACHED" if self.has_cached_frames else "frames=not loaded"
            )
        else:
            flags.append("frames=OFF")
        if self._cache_audio:
            flags.append(f"audio=CACHED ({self.audio_size_mb:.1f} MB)")
        else:
            flags.append("audio=OFF")
        return f"SliceStore({Path(self.path).name} [{', '.join(flags)}])"

    # -- memory management -------------------------------------------------

    def free(self) -> None:
        """Release cached data to free memory."""
        self._cached_frames = None
        self._cached_audio = None


# ---------------------------------------------------------------------------
# Slice creation helpers
# ---------------------------------------------------------------------------


def create_slices(
    video_path: str,
    params: SliceParams | None = None,
    cache_frames: bool = False,
    cache_audio: bool = False,
) -> list[SliceSource]:
    """Split a video into slices according to *params* and extract media.

    Parameters
    ----------
    video_path:
        Path to the video file (also used as the audio source).
    params:
        Window sizing.  Defaults to 30 s window, 2 s overlap.
    cache_frames:
        Load **all** video frames into memory before slicing.  Useful when
        the video is ≤ ~10 minutes so seeking repeatedly would be slower
        than a single decode.  For 1-hour videos this is **not** recommended.
    cache_audio:
        Load the full audio waveform into memory before slicing.
        For a 1-hour file at 16 kHz mono this is ~230 MB.

    Returns
    -------
    A list of ``SliceSource`` objects, each containing extracted frames
    and audio clip(s) for that slice's time range.
    """
    info = load_video_info(video_path)
    store = SliceStore(video_path, cache_frames=cache_frames, cache_audio=cache_audio)

    # Use context manager: opens VideoReader, then auto-closes on exit
    with store.open():
        return store.iter_slices(params)
