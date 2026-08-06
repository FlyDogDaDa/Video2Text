"""FastAPI application — endpoints for SAM-Audio service."""

from fastapi import FastAPI, HTTPException

from api.models import HealthResponse, SeparateRequest, SeparateResponse
from api.service import SamAudioService

app = FastAPI(title="SAM-Audio Service", version="0.1.0")
service = SamAudioService()


@app.post("/separate", response_model=SeparateResponse)
def separate(req: SeparateRequest):
    """Separate speaker from audio using span prompts.

    Input/output paths are absolute.
    Files may still be writing when response is returned — check file size to confirm completion.
    """
    try:
        return service.separate(req)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check — returns GPU status."""
    import torch

    return {
        "status": "ok",
        "gpu_available": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }
