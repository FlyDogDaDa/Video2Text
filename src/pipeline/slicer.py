"""Video slicing — split a video into overlapping windows.

This module provides ``slice_video()`` which yields ``SliceInput`` objects
ready for multimodal LLM inference.

Usage
-----
    from src.pipeline.slicer import slice_video
    from src.utils.slice import IOCacheVideo, SliceParams

    with IOCacheVideo("video.mkv") as video:
        params = SliceParams(window_seconds=30.0, overlap_seconds=2.0, sample_fps=1.0)
        for inp in slice_video(video, params):
            # inp: SliceInput(time_range=..., frames=..., audio_clips=..., info=...)
            ...

Re-exports
----------
``SliceParams`` is imported from ``src.utils.slice`` so callers only need
one fully-qualified name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator

from src.utils.video import IOCacheVideo, SliceParams

logger = logging.getLogger(__name__)

# Re-export so callers only need this module.
from src.utils.video import (
    _AUDIO_SAMPLE_RATE,
    _VIDEO_MAX_FRAMES,
    VideoInfo,  # noqa: F401
)


@dataclass(frozen=True)
class SliceInput:
    """Payload for a single video slice, ready for LLM inference.

    Parameters
    ----------
    time_range:
        ``(start, end)`` in seconds.
    frames:
        Numpy array of shape ``[N, H, W, 3]`` uint8 RGB.
    audio_clips:
        List of 16 kHz mono numpy arrays (each <= 30 s).
    info:
        ``VideoInfo`` metadata from the container.
    """

    time_range: tuple[float, float]
    frames: "np.ndarray"
    audio_clips: list["np.ndarray"]
    info: VideoInfo


def slice_video(
    video: IOCacheVideo,
    params: SliceParams | None = None,
) -> Iterator[SliceInput]:
    """Yield ``SliceInput`` objects by sliding a window over the video.

    Parameters
    ----------
    video:
        An open ``IOCacheVideo`` instance (caller owns the lifecycle).
    params:
        Slicing parameters from ``src.utils.slice.SliceParams``.
        Defaults to 30 s window, 2 s overlap, 1 fps.

    Yields
    ------
    ``SliceInput`` for each window.
    """
    if params is None:
        params = SliceParams()

    info = video.info
    duration = info.duration
    step = params.step_seconds

    print(
        f"   Duration: {duration:.1f}s | {info.fps:.1f}fps | "
        f"{info.width}\u00d7{info.height}"
    )
    print(
        f"   Window: {params.window_seconds}s | "
        f"Overlap: {params.overlap_seconds}s | "
        f"Step: {step:.1f}s"
    )
    print(f"   Max frames/slice: {params.max_frames} | Sample FPS: {params.sample_fps}")

    slice_num = 0
    t = 0.0
    while t < duration:
        start = t
        end = min(t + params.window_seconds, duration)
        if start >= end:
            break

        print(f"  [{slice_num:3d}] [{start:6.1f}s \u2013 {end:6.1f}s] ", end="")

        frames = video.get_frames(
            start,
            end,
            sample_fps=params.sample_fps,
            max_frames=params.max_frames,
        )
        audio_clips = video.get_audio(start, end, max_clip_duration=30.0)

        n_frames = frames.shape[0]
        audio_secs = [len(c) / _AUDIO_SAMPLE_RATE for c in audio_clips]
        print(
            f"frames={n_frames:3d}/{frames.shape[1]}x{frames.shape[2]} | "
            f"audio={len(audio_clips)}clip(s) "
            f"[{', '.join(f'{s:.1f}s' for s in audio_secs)}]"
        )

        yield SliceInput(
            time_range=(float(start), float(end)),
            frames=frames,
            audio_clips=audio_clips,
            info=info,
        )

        t += step
        slice_num += 1

    logger.info("%d slices yielded", slice_num)
