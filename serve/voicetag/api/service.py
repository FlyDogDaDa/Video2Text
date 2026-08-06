"""Service layer — wraps ``voicetag_core.identify()``."""

from pathlib import Path

from voicetag import DiarizationResult
from voicetag_core import health as _health
from voicetag_core import identify as _identify

from api.models import (
    HealthResponse,
    IdentifyRequest,
    IdentifyResponse,
    OverlapSegment,
    SpeakerSegment,
)


class VoiceTagService:
    """Wraps ``voicetag_core.identify()``."""

    DEFAULT_DEVICE = "cuda:0"
    DEFAULT_HF_TOKEN: str | None = None

    def identify(self, req: IdentifyRequest) -> IdentifyResponse:
        """Run speaker identification on audio.

        Parameters
        ----------
        req:
            Identification request with audio path and options.

        Returns
        -------
        IdentifyResponse
            Diarization result as Pydantic model.

        Raises
        ------
        FileNotFoundError:
            If the input audio file does not exist.
        """
        audio = Path(req.audio_path)
        if not audio.exists():
            raise FileNotFoundError(f"Input audio not found: {audio}")

        result: DiarizationResult = _identify(
            audio_path=str(audio),
            profile_path=req.profile_path,
            hf_token=self.DEFAULT_HF_TOKEN,
            device=self.DEFAULT_DEVICE,
        )

        return self._to_response(result)

    @staticmethod
    def _to_response(result: DiarizationResult) -> IdentifyResponse:
        """Convert voicetag ``DiarizationResult`` to ``IdentifyResponse``."""
        segments = []
        for seg in result.segments:
            if hasattr(seg, "speakers") and seg.speakers:
                segments.append(
                    OverlapSegment(
                        speakers=seg.speakers,
                        start=seg.start,
                        end=seg.end,
                        duration=seg.end - seg.start,
                    )
                )
            else:
                segments.append(
                    SpeakerSegment(
                        speaker=seg.speaker,
                        start=seg.start,
                        end=seg.end,
                        confidence=seg.confidence,
                        duration=seg.end - seg.start,
                    )
                )

        return IdentifyResponse(
            segments=segments,
            audio_duration=result.audio_duration,
            num_speakers=result.num_speakers,
            processing_time=result.processing_time,
            status="done",
        )

    def health(self) -> HealthResponse:
        """Check service health and GPU status."""
        info = _health(hf_token=self.DEFAULT_HF_TOKEN, device=self.DEFAULT_DEVICE)
        return HealthResponse(
            status=info["status"],
            gpu_available=info["gpu_available"],
            gpu_count=info["gpu_count"],
            speakers_enrolled=info["speakers_enrolled"],
        )
