"""Video file loading — load a file into ``io.BytesIO``.

This is a pure utility: read a file on disk, return a seekable ``BytesIO``.

Uses ``pathlib`` for all file system operations.

Usage
-----
>>> from src.utils.container import load_bytes
>>> buf = load_bytes(Path("video.mp4"))
>>> # pass ``buf`` to PyAV, other libraries, etc.
"""

from __future__ import annotations

import io
from pathlib import Path


def load_bytes(path: Path | str) -> io.BytesIO:
    """Load a file into memory as a seekable ``BytesIO``.

    Parameters
    ----------
    path:
        Path to the video (or any) file.  Accepts ``str`` or ``Path``.

    Returns
    -------
    ``io.BytesIO`` containing the full file content.

    Raises
    ------
    FileNotFoundError
        If *path* does not point to an existing file.
    ValueError
        If the file exists but has zero size.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if p.stat().st_size == 0:
        raise ValueError(f"File is empty: {path}")

    return io.BytesIO(p.read_bytes())
