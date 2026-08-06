"""FastAPI application — endpoints for VoiceTag service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from api.models import HealthResponse, IdentifyRequest, IdentifyResponse
from api.service import VoiceTagService

service = VoiceTagService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up model on startup using the same device as the service."""
    print(
        f"[voicetag_server] Loading VoiceTag model on {VoiceTagService.DEFAULT_DEVICE}..."
    )
    info = service.health()
    if info["status"] == "error":
        print(f"[voicetag_server] WARNING: Model failed to load: {info.get('detail')}")
    else:
        print("[voicetag_server] Model loaded successfully")
    yield


app = FastAPI(title="VoiceTag Service", version="0.1.0", lifespan=lifespan)


@app.post("/identify", response_model=IdentifyResponse)
def identify(req: IdentifyRequest):
    """Identify who spoke when in an audio file.

    Returns a timeline of speaker segments with timestamps and confidence scores.
    """
    try:
        return service.identify(req)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check — returns GPU status and enrolled speaker count."""
    return service.health()
