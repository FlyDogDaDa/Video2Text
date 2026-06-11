"""Video2Text pipeline — model loading, slicing, and structured extraction."""

from src.pipeline.extractor import extract_structured
from src.pipeline.loader import load_model
from src.pipeline.slicer import SliceInput, slice_video

__all__ = [
    "load_model",
    "slice_video",
    "SliceInput",
    "extract_structured",
]
