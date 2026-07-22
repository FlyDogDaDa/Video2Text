"""Lightweight SAM-Audio client — calls the remote microservice.

The heavy model logic lives in ``serve/sam-audio``.
This module only builds HTTP requests and parses responses.
"""

from pathlib import Path

import httpx
from pydantic import BaseModel


class SeparationResult(BaseModel):
    """Result of a speaker separation request.

    Parameters
    ----------
    speaker:
        Path to the isolated speaker audio file.
    residual:
        Path to the residual (remainder) audio file.
    """

    speaker: Path
    residual: Path


# ── Public API ────────────────────────────────────────────────────────────────


def separate_by_anchor(
    audio: Path,
    anchors: list[list],
    description: str = "",
    speaker_output: Path = None,
    residual_output: Path = None,
    server_url: str = "http://localhost:8000",
) -> SeparationResult:
    """Separate audio by sending a request to the SAM-Audio microservice.

    Parameters
    ----------
    audio:
        Path to the input audio file (mixture).
    anchors:
        Time span annotations. Each span is ``[type, start, end]``.
        ``"+"`` marks where the target sound IS present.
        ``"-"`` marks where the target sound is NOT present.
    description:
        Optional text description. Use empty string for pure span mode.
    speaker_output:
        Output path for separated speaker audio.
        Defaults to ``{audio.stem}_speaker.wav``.
    residual_output:
        Output path for residual audio.
        Defaults to ``{audio.stem}_residual.wav``.
    server_url:
        Base URL of the SAM-Audio microservice.

    Returns
    -------
    SeparationResult
        Paths to separated speaker and residual audio files.

    Raises
    ------
    httpx.HTTPStatusError:
        If the server returns a non-2xx status code.
    httpx.RequestError:
        If the server is unreachable.
    """
    spk = speaker_output or (audio.parent / f"{audio.stem}_speaker.wav")
    res = residual_output or (audio.parent / f"{audio.stem}_residual.wav")

    response = httpx.post(
        f"{server_url}/separate",
        json={
            "audio_path": str(audio),
            "anchors": anchors,
            "description": description,
            "speaker_output": str(spk),
            "residual_output": str(res),
        },
        timeout=300,
    )
    response.raise_for_status()

    body = response.json()
    return SeparationResult(
        speaker=Path(body["speaker"]),
        residual=Path(body["residual"]),
    )
