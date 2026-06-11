"""Video2Text IO utilities — PyAV-based video/audio slicing."""

from src.utils.audio import normalize_audio
from src.utils.factory import create_bytes_io
from src.utils.video import (
    IOCacheVideo,
    SliceParams,
    VideoInfo,
)

# Backwards-compat alias (prefer `create_bytes_io`)
load_bytes = create_bytes_io

__all__ = [
    "IOCacheVideo",
    "SliceParams",
    "VideoInfo",
    "load_bytes",
    "create_bytes_io",
    "normalize_audio",
]
