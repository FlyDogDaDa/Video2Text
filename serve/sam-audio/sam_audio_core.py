"""SAM-Audio model loading and separation logic (server-side).

This module is **independent** of the main Video2Text project.
It owns the model lifecycle, GPU management, and separation computation.
"""

from pathlib import Path

import torch
import torchaudio

# Model cache — loaded once on first call
_model = None
_processor = None


# ── Public API ────────────────────────────────────────────────────────────────


def _ensure_model(device: str = "cpu"):
    """Load or return the cached SAM-Audio model and processor.

    Follows the official HuggingFace pattern:
    model = SAMAudio.from_pretrained().to(device).eval()
    """
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor

    from sam_audio import SAMAudio, SAMAudioProcessor

    model = SAMAudio.from_pretrained(
        "facebook/sam-audio-small",
    )
    processor = SAMAudioProcessor.from_pretrained(
        "facebook/sam-audio-small",
    )

    # Move to device; model checkpoint is already bf16
    model = model.to(device).eval()
    processor = processor.to(device) if hasattr(processor, "to") else processor

    print(f"[sam_audio_core] Model loaded on {device}")
    _model = model
    _processor = processor
    return _model, _processor


def separate(
    audio_path: str,
    anchors: list[list],
    description: str = "",
    speaker_output: str = None,
    residual_output: str = None,
    device: str = "cpu",
) -> tuple[Path, Path]:
    """Separate audio using SAM-Audio span prompting.

    Parameters
    ----------
    audio_path:
        Path to the input audio file.
    anchors:
        Time span annotations. Each span is ``[type, start, end]``.
    description:
        Text description (empty for pure span mode).
    speaker_output:
        Output path for speaker audio (auto-generated if ``None``).
    residual_output:
        Output path for residual audio (auto-generated if ``None``).
    device:
        Compute device.

    Returns
    -------
    (speaker_path, residual_path)
    """
    print(f"[sam_audio_core] Loading model on {device}...")
    model, processor = _ensure_model(device)

    # Process audio + anchors
    # anchors format: [['+', start, end], ...] — passed directly, triple-nested: [[[...]]]
    inputs = processor(
        audios=[str(audio_path)],
        descriptions=[description],
        anchors=[anchors],
    )
    model_device = next(model.parameters()).device
    # Move inputs to model device (fp32 only, no dtype conversion needed)
    inputs = inputs.to(model_device)

    print(f"[sam_audio_core] Running separation on {model_device}...")

    # Run separation
    with torch.inference_mode():
        result = model.separate(inputs, predict_spans=False)

    # Move to CPU for saving
    target = result.target[0].cpu()
    residual = result.residual[0].cpu()

    # Default output names
    if speaker_output is None:
        audio = Path(audio_path)
        speaker_output = str(audio.parent / f"{audio.stem}_speaker.wav")
    if residual_output is None:
        audio = Path(audio_path)
        residual_output = str(audio.parent / f"{audio.stem}_residual.wav")

    sample_rate = processor.audio_sampling_rate

    torchaudio.save(str(speaker_output), target, sample_rate)
    torchaudio.save(str(residual_output), residual, sample_rate)

    return Path(speaker_output), Path(residual_output)


# ── Health ────────────────────────────────────────────────────────────────────


def health() -> dict:
    """Return GPU status."""
    return {
        "status": "ok",
        "gpu_available": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }
