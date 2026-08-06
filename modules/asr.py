"""Automatic Speech Recognition (ASR) module.

Transcribes spoken segments from video files using configurable
speech-to-text models.
"""

from pathlib import Path

from pydantic import BaseModel

from framework.config import cfg


class AsrConfig(BaseModel):
    """Configuration for the ASR pipeline.

    Attributes
    ----------
    model : str
        Hugging Face model identifier for the speech-to-text model.
    batch_size : int
        Number of segments to process per inference batch.
    language : str
        Language code for transcription (e.g. ``"zh"``, ``"en"``).
    """

    model: str = "MediaTek-Research/Breeze-ASR-26"
    batch_size: int = 64
    language: str = "zh"


def transcribe(video: Path, segments: list[dict]) -> Path:
    """Transcribe spoken segments from a video file.

    Extracts audio intervals defined by *segments* and runs
    speech-to-text recognition to produce a word-level
    transcription file in JSONL format.

    Parameters
    ----------
    video:
        Path to the input video file.
    segments:
        List of speaking intervals; each element is a dict with
        ``"start"`` and ``"end"`` keys specifying time offsets in seconds.

    Returns
    -------
    Path
        Path to the output JSONL transcription file.
    """
    c = cfg("asr", AsrConfig)

    # TODO: 實作 ASR 邏輯
    # 1. 使用 ffmpeg 或 moviepy 從 video 提取區間音訊
    # 2. 批次送給 c.model 推理
    # 3. 將逐字稿寫入 JSONL 並回傳路徑

    return Path("output.jsonl")
