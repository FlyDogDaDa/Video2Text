"""Pydantic models for request/response validation."""

from typing import List

from pydantic import BaseModel, Field


class SeparateRequest(BaseModel):
    """Request body for speaker separation."""

    audio_path: str = Field(..., description="Path to input audio file (absolute path)")
    anchors: List[List] = Field(
        ..., description="Time span annotations: [['+', 0.5, 3.2], ...]"
    )
    description: str = Field(
        "", description="Optional text description (empty for pure span mode)"
    )
    speaker_output: str = Field(
        "", description="Optional custom output path for speaker audio"
    )
    residual_output: str = Field(
        "", description="Optional custom output path for residual audio"
    )


class SeparateResponse(BaseModel):
    """Response body with output paths."""

    speaker: str = Field(..., description="Path to separated speaker audio")
    residual: str = Field(..., description="Path to residual audio")
    status: str = Field("done", description="Status: done")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    gpu_available: bool
    gpu_count: int
