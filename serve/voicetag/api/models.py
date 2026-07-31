"""Pydantic models for request/response validation."""

from typing import List, Optional

from pydantic import BaseModel, Field


class IdentifyRequest(BaseModel):
    """Request body for speaker identification."""

    audio_path: str = Field(..., description="Path to input audio file (absolute path)")
    profile_path: Optional[str] = Field(
        None, description="Optional path to saved speaker profiles JSON"
    )
    threshold: Optional[float] = Field(
        None, description="Similarity threshold override (0.0–1.0)"
    )


class SpeakerSegment(BaseModel):
    """A single speaker segment in the diarization timeline."""

    speaker: str = Field(..., description="Identified speaker name or 'UNKNOWN'")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    confidence: float = Field(..., description="Cosine similarity score (0.0–1.0)")
    duration: float = Field(..., description="End - Start in seconds")


class OverlapSegment(BaseModel):
    """A segment where multiple speakers talk simultaneously."""

    speakers: List[str] = Field(..., description="Names of overlapping speakers")
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    speaker: str = Field("OVERLAP", description="Always 'OVERLAP'")
    duration: float = Field(..., description="End - Start in seconds")


class IdentifyResponse(BaseModel):
    """Response body with diarization results."""

    segments: List[SpeakerSegment] = Field(
        ..., description="Ordered timeline of speaker segments"
    )
    audio_duration: float = Field(..., description="Total audio length in seconds")
    num_speakers: int = Field(..., description="Number of distinct speakers detected")
    processing_time: float = Field(
        ..., description="Wall-clock pipeline time in seconds"
    )
    status: str = Field("done", description="Status: done")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    gpu_available: bool
    gpu_count: int
    speakers_enrolled: int
