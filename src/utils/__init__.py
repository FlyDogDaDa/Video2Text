"""Video2Text IO utilities — PyAV-based video/audio slicing."""

from src.utils.audio import normalize_audio
from src.utils.factory import create_bytes_io, create_slices_indices
from src.utils.jsonl import read_jsonl, write_jsonl
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
    "create_slices_indices",
    "normalize_audio",
    "write_jsonl",
    "read_jsonl",
]
