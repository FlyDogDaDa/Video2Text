"""Speech voice activity detection (VAD) module.

Detects speech intervals in video/audio files using silence-based segmentation.
"""

from pathlib import Path

from pydantic import BaseModel

from framework.config import cfg


class VadConfig(BaseModel):
    """Configuration for voice activity detection.

    Parameters
    ----------
    threshold:
        Energy threshold for speech detection.
    min_silence_duration_ms:
        Minimum silence duration in milliseconds to split segments.
    chunk_seconds:
        Maximum analysis chunk size in seconds.
    """

    threshold: float = 0.5
    min_silence_duration_ms: int = 300
    chunk_seconds: float = 300.0


def detect_speech(video: Path) -> list[dict]:
    """Detect speech intervals in a video file.

    Parameters
    ----------
    video:
        Path to the video file.

    Returns
    -------
    list[dict]
        List of speech intervals, each represented as ``{"start": float, "end": float}``.

    Notes
    -----
    TODO: 實作 VAD 邏輯
    """
    c = cfg("vad", VadConfig)

    # TODO: 實作 VAD 邏輯

    return []
