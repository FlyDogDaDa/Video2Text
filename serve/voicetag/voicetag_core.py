"""VoiceTag model loading and identification logic (server-side).

This module is **independent** of the main Video2Text project.
It owns the model lifecycle and speaker identification computation.
"""

import os
from pathlib import Path
from typing import Optional

# Load .env before importing anything else
_ENV_LOADER = Path(__file__).resolve().parent / ".env"
if _ENV_LOADER.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(str(_ENV_LOADER))
    except ImportError:
        pass

del _ENV_LOADER

from voicetag import DiarizationResult, VoiceTag, VoiceTagConfig

# Supported audio extensions (soundfile needs WAV; we convert others via librosa)
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

# Global instance — initialized lazily on first call
_vt: Optional[VoiceTag] = None


def _ensure_voicetag(
    hf_token: Optional[str] = None,
    device: str = "cpu",
) -> VoiceTag:
    """Load or return the cached VoiceTag instance.

    Token resolution order:
    1. ``hf_token`` argument (explicit)
    2. ``HF_TOKEN`` environment variable (from .env or exported)
    3. Raise ``VoiceTagConfigError``

    Parameters
    ----------
    hf_token:
        HuggingFace token for pyannote model access.
    device:
        Torch device: ``"cpu"``, ``"cuda"``, or ``"mps"``.

    Returns
    -------
    VoiceTag
        Configured instance ready for inference.
    """
    global _vt
    if _vt is not None:
        return _vt

    # Resolve token: explicit arg > env var
    token = hf_token or os.environ.get("HF_TOKEN")
    config = VoiceTagConfig(hf_token=token, device=device)
    _vt = VoiceTag(config=config)
    print(f"[voicetag_core] VoiceTag loaded on {device}")
    return _vt


def _convert_to_wav(audio_path: str | Path, target_sr: int = 16000) -> Path:
    """Convert any supported audio to a temp WAV file for voicetag.

    voicetag uses soundfile internally, which cannot decode MP3/FLAC/etc.
    This helper loads via librosa and writes a WAV temp file.

    Parameters
    ----------
    audio_path:
        Path to the input audio file.
    target_sr:
        Target sample rate (default: 16000 for resemblyzer enrollment).

    Returns
    -------
    Path
        Path to the temp WAV file (caller must clean up).
    """
    import tempfile

    import librosa
    import soundfile as sf

    audio = Path(audio_path)
    if not audio.exists():
        raise FileNotFoundError(f"Input audio not found: {audio}")

    suffix = audio.suffix.lower()
    if suffix == ".wav":
        return audio  # No conversion needed

    # Load via librosa (supports MP3/FLAC/OGG/M4A via ffmpeg)
    y, sr = librosa.load(str(audio), sr=target_sr, mono=True)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, y, sr, format="WAV")
    tmp_path = Path(tmp.name)
    print(f"[voicetag_core] Converted {audio.name} -> {tmp_path.name} ({sr} Hz)")
    return tmp_path


def enroll(
    name: str,
    audio_paths: list[str | Path],
    hf_token: Optional[str] = None,
    device: str = "cpu",
) -> tuple[str, list[str]]:
    """Enroll a speaker from one or more audio samples.

    Automatically converts non-WAV files to WAV before enrollment.

    Parameters
    ----------
    name:
        Speaker name to register.
    audio_paths:
        Paths to audio files for this speaker.
    hf_token:
        HuggingFace token (falls back to env var).
    device:
        Compute device.

    Returns
    -------
    tuple[str, list[str]]
        (speaker_name, list_of_enrolled_audio_paths)
    """
    # Convert all audio files to WAV if needed
    wav_paths = []
    temp_files = []
    try:
        for ap in audio_paths:
            wav_path = _convert_to_wav(ap, target_sr=16000)
            if wav_path != ap:  # temp file created
                temp_files.append(wav_path)
            wav_paths.append(str(wav_path))

        vt = _ensure_voicetag(hf_token=hf_token, device=device)
        profile = vt.enroll(name, wav_paths)
        print(
            f"[voicetag_core] Enrolled speaker '{name}' from {len(wav_paths)} file(s)"
        )
        return (name, wav_paths)
    finally:
        # Clean up temp files
        for tf in temp_files:
            tf.unlink(missing_ok=True)


def identify(
    audio_path: str,
    profile_path: Optional[str] = None,
    hf_token: Optional[str] = None,
    device: str = "cpu",
) -> DiarizationResult:
    """Run speaker identification on an audio file.

    voicetag internally passes the file path to pyannote's Pipeline,
    which natively handles arbitrary-length audio via sliding window
    (30s window, 15s stride). No chunking or padding is needed.

    The only conversion required is non-WAV → WAV because soundfile
    (used by voicetag internally) cannot decode MP3/FLAC/OGG/M4A.

    Parameters
    ----------
    audio_path:
        Path to the input audio file.
    profile_path:
        Optional path to a saved speaker profiles JSON file.
        If provided, loaded before identification.
    hf_token:
        HuggingFace token (falls back to env var).
    device:
        Compute device.

    Returns
    -------
    DiarizationResult
        Pydantic model with segments, speaker count, timing.
    """
    import tempfile

    import librosa
    import soundfile as sf

    audio = Path(audio_path)
    if not audio.exists():
        raise FileNotFoundError(f"Input audio not found: {audio}")

    # Compute actual duration BEFORE any conversion
    y, sr = librosa.load(str(audio), sr=48000, mono=True)
    original_duration = len(y) / sr

    # Save to a temp WAV file (voicetag requires filesystem path;
    # soundfile cannot decode MP3/FLAC/OGG/M4A directly)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, y, sr, format="WAV")
    tmp_path = Path(tmp.name)

    try:
        vt = _ensure_voicetag(hf_token=hf_token, device=device)

        if profile_path:
            profiles = Path(profile_path)
            if not profiles.exists():
                raise FileNotFoundError(f"Profile file not found: {profile_path}")
            vt.load(str(profiles))

        result: DiarizationResult = vt.identify(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Override audio_duration with actual file duration
    # (pyannote may report slightly different duration from the WAV file)
    object.__setattr__(result, "audio_duration", original_duration)

    return result


def health(hf_token: Optional[str] = None, device: str = "cpu") -> dict:
    """Return service health and GPU status.

    Parameters
    ----------
    hf_token, device:
        Passed to ``_ensure_voicetag`` to warm up the model.

    Returns
    -------
    dict
        Health status with GPU info and speaker count.
    """
    import torch

    try:
        vt = _ensure_voicetag(hf_token=hf_token, device=device)
        return {
            "status": "ok",
            "gpu_available": torch.cuda.is_available(),
            "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "speakers_enrolled": len(vt.enrolled_speakers),
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
            "gpu_available": torch.cuda.is_available(),
            "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "speakers_enrolled": 0,
        }
