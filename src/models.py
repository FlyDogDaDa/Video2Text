"""
Video2Text core data models.

Pydantic schemas for the structured output of each window slice.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class TimeRange(BaseModel, frozen=True):
    """Start and end timestamps of a video window in seconds."""

    start: Decimal = Field(ge=0)
    end: Decimal = Field(ge=0)

    @property
    def duration(self) -> Decimal:
        """Return the duration of this time range."""
        return self.end - self.start


class Description(BaseModel, frozen=True):
    """Visual and audio description of a video window."""

    visual: str = Field(
        description="Description of events happening in the visual frame"
    )
    audio: str = Field(description="Description of audio content in the window")


class TranscriptionEntry(BaseModel, frozen=True):
    """A single spoken utterance with speaker identification."""

    text: str = Field(description="Spoken text content")
    speaker: str | None = Field(default=None, description="Speaker name or identifier")


class Transcription(BaseModel, frozen=True):
    """Transcription section containing detected spoken dialogue and visual captions."""

    audio: list[TranscriptionEntry] = Field(default_factory=list)
    visual: str = Field(
        default="",
        description="Visual caption describing what's happening in the scene",
    )


class SliceResult(BaseModel, frozen=True):
    """Structured result for a single video window slice.

    Matches the output schema designed in the system specification:

    .. code-block:: json

        {
            "description": {
                "visual": "...",
                "audio": "..."
            },
            "transcription": {
                "audio": [
                    {"text": "...", "speaker": "..."}
                ]
            },
            "time_range": {
                "start": 28.0,
                "end": 58.0
            }
        }
    """

    description: Description = Field(default_factory=Description)
    transcription: Transcription = Field(default_factory=Transcription)
    time_range: TimeRange = Field(default_factory=TimeRange)
