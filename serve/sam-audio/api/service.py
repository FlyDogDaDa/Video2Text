"""Service layer — wraps ``sam_audio_core.separate()``."""

from pathlib import Path

from sam_audio_core import separate as _separate

from api.models import SeparateRequest, SeparateResponse


class SamAudioService:
    """Wraps ``sam_audio_core.separate()``."""

    DEFAULT_DEVICE = "cuda:0"

    def separate(self, req: SeparateRequest) -> SeparateResponse:
        """Execute speaker separation.

        Parameters
        ----------
        req:
            Separation request with paths and anchors.

        Returns
        -------
        SeparateResponse
            Output paths.

        Raises
        ------
        FileNotFoundError:
            If the input audio file does not exist.
        """
        audio = Path(req.audio_path)
        if not audio.exists():
            raise FileNotFoundError(f"Input audio not found: {audio}")

        speaker_out = Path(req.speaker_output) if req.speaker_output else None
        residual_out = Path(req.residual_output) if req.residual_output else None

        spk, res = _separate(
            audio_path=str(audio),
            anchors=req.anchors,
            description=req.description or "",
            speaker_output=str(speaker_out) if speaker_out else None,
            residual_output=str(residual_out) if residual_out else None,
            device=self.DEFAULT_DEVICE,
        )

        return SeparateResponse(
            speaker=str(spk),
            residual=str(res),
            status="done",
        )
