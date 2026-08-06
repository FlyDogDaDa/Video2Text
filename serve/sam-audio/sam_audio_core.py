"""SAM-Audio model loading and separation logic (server-side).

This module is **independent** of the main Video2Text project.
It owns the model lifecycle, GPU management, and separation computation.
"""

import os
from pathlib import Path

import torch
import torchaudio

# Model cache — loaded once on first call
_model = None
_processor = None


# ── Public API ────────────────────────────────────────────────────────────────


def _ensure_model(device: str = "cpu", alloc_conf: str = ""):
    """Load or return the cached SAM-Audio model and processor."""
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor

    if alloc_conf:
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = alloc_conf

    from sam_audio import SAMAudio, SAMAudioProcessor

    model = SAMAudio.from_pretrained(
        "facebook/sam-audio-small",
        proxies={},
        resume_download=True,
    )
    processor = SAMAudioProcessor.from_pretrained(
        "facebook/sam-audio-small",
        proxies={},
        resume_download=True,
    )

    # Use fp16 if on GPU to save memory; otherwise cpu
    if device.startswith("cuda") and model.dtype != torch.float16:
        try:
            model = model.half().to(device)  # fp16 to save ~50% memory
            print(f"[sam_audio_core] Loaded model in fp16 on {device}")
        except Exception:
            print(f"[sam_audio_core] fp16 failed, falling back to cpu")
            device = "cpu"
            model = model.to(device)
    else:
        model = model.to(device)

    model.eval()
    processor = processor.to(device) if hasattr(processor, "to") else processor

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
    alloc_conf: str = "",
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
    alloc_conf:
        PyTorch CUDA allocation config.

    Returns
    -------
    (speaker_path, residual_path)
    """
    print(f"[sam_audio_core] Loading model on {device}...")
    model, processor = _ensure_model(device, alloc_conf)

    # Prepare anchors
    anchors_tensor = processor.prepare_anchors(anchors)

    # Process audio + anchors
    inputs = processor(
        audios=[str(audio_path)],
        descriptions=[description],
        anchors=[anchors_tensor],
    )
    inputs = inputs.to(model.device)

    print(f"[sam_audio_core] Running separation on {model.device}...")

    # Run separation
    with torch.inference_mode():
        result = model.separate(inputs)

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
