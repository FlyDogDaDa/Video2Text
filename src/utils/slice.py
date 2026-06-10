"""IOCacheVideo — PyAV video container wrapper with optional in-memory cache.

This is the **core** of the video-slicing toolkit.  It wraps ``av.open()`` and
exposes both the raw PyAV object (for power users) and convenient slice-level
helpers for extracting frames and audio at arbitrary time ranges.

Design principles
-----------------
1. **PyAV is the backend** — all I/O goes through ``av``.
2. **Optional in-memory cache** — set ``cached=True`` to load the file into
   ``io.BytesIO`` before opening; seek performance improves for repeated
   random access.
3. **Direct AV exposure** — ``container``, ``video_stream``, and
   ``audio_streams`` properties let callers drop down to PyAV at any time.

Usage
-----
Basic usage::

    from src.utils.slice import IOCacheVideo, SliceParams, SliceSource

    with IOCacheVideo("video.mp4") as video:
        frames = video.get_frames(0, 30)
        audio = video.get_audio(0, 30)

Cached mode (faster random access)::

    with IOCacheVideo("video.mp4", cached=True) as video:
        ...

Power user — raw PyAV::

    with IOCacheVideo("video.mp4") as video:
        video.container.seek(300 * int(video.video_stream.time_base),
                             stream=video.video_stream)
        for frame in video.container.decode(video.video_stream):
            process(frame)
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import av
import numpy as np
import numpy.typing as npt
from scipy.signal import resample as _resample

from src.utils.audio import normalize_audio
from src.utils.container import load_bytes

if TYPE_CHECKING:
    pass  # no cv2 or av needed for type hints

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
    audio_streams: list[int] | None = None  # None = all audio streams

    @property
    def step_seconds(self) -> float:
        """Sliding step = window − overlap."""
        return max(self.window_seconds - self.overlap_seconds, 0.1)

    @property
    def max_frames(self) -> int:
        """Max frames per slice, capped by Gemma-4 hard limit."""
        frames = int(self.window_seconds * self.sample_fps)
        return min(frames, _VIDEO_MAX_FRAMES)


# ---------------------------------------------------------------------------
# IOCacheVideo — the single core class
# ---------------------------------------------------------------------------


class IOCacheVideo:
    """PyAV container wrapper with optional in-memory cache.

    Parameters
    ----------
    source:
        File path (``str``) or a seekable ``io.BytesIO`` object.
    cached:
        When ``source`` is a path, load the file into ``BytesIO`` first.
        Improves seek performance for repeated random access at the cost
        of loading the full file into memory.

    Attributes
    ----------
    container : av.Container
        The underlying PyAV container — use directly for advanced operations.
    video_stream : av.VideoStream
        The first video stream in the container.
    audio_streams : list[av.AudioStream]
        All audio streams in the container.
    """

    def __init__(
        self, source: Path | str | io.BytesIO, *, cached: bool = False
    ) -> None:
        # Determine container source
        if isinstance(source, (str, Path)):
            if cached:
                # Load full file into BytesIO for faster seek
                self._container = av.open(load_bytes(source))
            else:
                self._container = av.open(source)
            self._path = str(source)
        else:
            self._container = av.open(source)
            self._path = "<bytesio>"
        self._cached = cached

        # Cache stream references
        self._video_stream = self._container.streams.video[0]
        self._audio_streams = list(self._container.streams.audio)

        # Precompute useful metadata from PyAV
        self._video_tb = float(self._video_stream.time_base)
        self._video_fps = (
            float(self._video_stream.base_rate)
            if hasattr(self._video_stream, "base_rate")
            else self._video_stream.average_rate
        )
        self._video_duration = (
            float(self._video_stream.duration * self._video_tb)
            if self._video_stream.duration
            else 0.0
        )
        self._video_width = self._video_stream.width
        self._video_height = self._video_stream.height

        # Duration from container if stream duration unavailable
        if not self._video_duration:
            self._video_duration = float(
                self._container.duration / 1_000_000
            )  # container duration in microseconds

    # -- public properties (direct AV exposure) ---------------------------

    @property
    def container(self):
        """The underlying ``av.Container`` object."""
        return self._container

    @property
    def video_stream(self):
        """The first video stream."""
        return self._video_stream

    @property
    def audio_streams(self):
        """All audio streams."""
        return self._audio_streams

    @property
    def info(self) -> VideoInfo:
        """Video metadata as ``VideoInfo``."""
        return VideoInfo(
            duration=self._video_duration,
            fps=self._video_fps or _DEFAULT_FPS,
            width=self._video_width,
            height=self._video_height,
            total_frames=int(self._video_duration * (self._video_fps or _DEFAULT_FPS)),
            path=self._path,
        )

    @property
    def duration(self) -> float:
        """Video duration in seconds."""
        return self._video_duration

    # -- frame extraction -------------------------------------------------

    def get_frames(
        self,
        start: float,
        end: float,
        sample_fps: float = _DEFAULT_FPS,
        max_frames: int = _VIDEO_MAX_FRAMES,
    ) -> npt.NDArray:
        """Extract frames in ``[start, end)`` as ``[N, H, W, 3]`` uint8 RGB.

        Parameters
        ----------
        start, end:
            Time range in seconds.
        sample_fps:
            Target frame sampling rate.  Default 1 fps.
        max_frames:
            Maximum number of frames to return.  Capped by Gemma-4 limit.

        Returns
        -------
        ``np.ndarray`` of shape ``[N, H, W, 3]`` or empty array if range is invalid.
        """
        if start >= end or start < 0:
            return np.empty(
                (0, self._video_height, self._video_width, 3), dtype=np.uint8
            )

        # Calculate frame indices
        start_time = start
        end_time = min(end, self._video_duration)
        num_samples = int((end_time - start_time) * sample_fps)
        num_samples = min(num_samples, max_frames)

        if num_samples <= 0:
            return np.empty(
                (0, self._video_height, self._video_width, 3), dtype=np.uint8
            )

        # Seek to start position (stream-level timebase)
        seek_pts = int(start_time / self._video_tb)
        self._container.seek(seek_pts, stream=self._video_stream)

        # Collect frames
        frames_list: list[np.ndarray] = []
        target_times = np.linspace(start_time, end_time - 1e-6, num_samples)
        target_idx = 0

        for frame in self._container.decode(self._video_stream):
            frame_time = frame.pts * frame.time_base
            if frame_time < start_time:
                continue
            if frame_time >= end_time:
                break

            # Check if we should sample this frame
            if target_idx < num_samples and frame_time >= target_times[target_idx]:
                # Convert to RGB (PyAV outputs YUV)
                rgb_frame = frame.to_rgb().to_ndarray()  # [H, W, 3] uint8
                frames_list.append(rgb_frame)
                target_idx += 1

            if len(frames_list) >= max_frames:
                break

        if not frames_list:
            return np.empty(
                (0, self._video_height, self._video_width, 3), dtype=np.uint8
            )

        return np.stack(frames_list)

    # -- audio extraction -------------------------------------------------

    def get_audio(
        self,
        start: float,
        end: float,
        max_clip_duration: float = 30.0,
        audio_streams: list[int] | None = None,
    ) -> list[np.ndarray]:
        """Extract audio in ``[start, end)`` as 16 kHz mono clips.

        Parameters
        ----------
        start, end:
            Time range in seconds.
        max_clip_duration:
            Maximum clip length in seconds.  Audio longer than this is split.
        audio_streams:
            Which audio streams to mix.  ``None`` means **all** streams.

        Returns
        -------
        A list of 1-D ``np.ndarray`` of dtype ``float32``, each ≤30 s.
        """
        if start >= end or not self._audio_streams:
            return []

        # Select streams
        selected_indices = (
            audio_streams
            if audio_streams is not None
            else list(range(len(self._audio_streams)))
        )
        streams_to_decode = [
            self._audio_streams[i]
            for i in selected_indices
            if i < len(self._audio_streams)
        ]
        if not streams_to_decode:
            return []

        # Seek to start position (stream-level timebase)
        seek_pts = int(start / streams_to_decode[0].time_base)
        self._container.seek(seek_pts, stream=streams_to_decode[0])

        # Decode each selected stream
        all_tracks: list[np.ndarray] = []
        for stream in streams_to_decode:
            frames_list: list[np.ndarray] = []
            for frame in self._container.decode(stream):
                if frame.pts is None:
                    continue
                frame_time = float(frame.pts * frame.time_base)
                if frame_time >= end:
                    break
                if frame_time >= start:
                    frames_list.append(frame.to_ndarray().astype(np.float32))

            if not frames_list:
                continue

            # Mono-mix per frame, then concatenate
            mono = [arr.mean(axis=1) for arr in frames_list]
            track = np.concatenate(mono)

            # Resample to 16 kHz if needed
            if int(stream.sample_rate) != _AUDIO_SAMPLE_RATE:
                n_out = int(len(track) * _AUDIO_SAMPLE_RATE / int(stream.sample_rate))
                track = _resample(track, n_out, axis=0)

            all_tracks.append(track)

        if not all_tracks:
            return []

        # Zero-pad all tracks to the same length, then sum
        max_len = max(len(t) for t in all_tracks)
        summed = np.zeros(max_len, dtype=np.float32)
        for t in all_tracks:
            summed[: len(t)] += t

        # Peak-normalise
        summed = normalize_audio(summed)

        # Split if longer than max_clip_duration
        if len(summed) <= _AUDIO_SAMPLE_RATE * max_clip_duration:
            return [summed]

        chunk_samples = int(_AUDIO_SAMPLE_RATE * max_clip_duration)
        chunks: list[np.ndarray] = []
        for i in range(0, len(summed), chunk_samples):
            chunks.append(summed[i : i + chunk_samples])
        return chunks

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Close the underlying PyAV container."""
        self._container.close()

    def __enter__(self) -> "IOCacheVideo":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        cached = " <cached>" if self._cached else ""
        return f"IOCacheVideo({self._path!r}, {len(self._audio_streams)} audio streams{cached})"
