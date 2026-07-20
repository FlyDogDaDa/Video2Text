"""Audio normalization utilities."""

from __future__ import annotations

import numpy as np


def normalize_audio(data: np.ndarray) -> np.ndarray:
    """Mono-mix (mean) and normalise to [-1, 1].

    Mirrors ``vllm.multimodal.audio.normalize_audio`` + ``normalize_audio``
    from ``multimodal_infer.py`` for consistency.

    Parameters
    ----------
    data:
        Input audio array.  Multi-channel arrays are mixed down to mono
        by taking the mean along axis 1.

    Returns
    -------
    Normalised 1-D ``np.ndarray``.
    """
    if data.ndim > 1:
        data = data.mean(axis=1)
    peak = float(np.abs(data).max())
    if peak > 0:
        data = data / peak
    return data
