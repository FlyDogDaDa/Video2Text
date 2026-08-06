"""Video frame description module.


Extracts frame-level captions from a video file using a vision model.
"""

from pathlib import Path

from pydantic import BaseModel

from framework.config import cfg


class VideoDescConfig(BaseModel):
    """Configuration for the video frame description pipeline.

    Attributes
    ----------
    fps : float
        Frame sampling rate (frames per second).
    max_tokens : int
        Maximum number of tokens per description.
    temperature : float
        Sampling temperature for the vision model.
    """

    fps: float = 1.0
    max_tokens: int = 24576
    temperature: float = 1.0


def describe_frames(video: Path) -> Path:
    """Describe frames of a video.

    Parameters
    ----------
    video:
        Path to the input video file.

    Returns
    -------
    Path
        Path to the output JSONL file containing frame descriptions.
    """
    c = cfg("video_desc", VideoDescConfig)

    # TODO: 實作畫面描述邏輯

    return Path("output.jsonl")
