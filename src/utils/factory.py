"""BytesIO factory — create seekable ``BytesIO`` from files.

Pure utility: read a file on disk, return a seekable ``BytesIO``.

Uses ``pathlib`` for all file system operations.

Usage
-----
>>> from src.utils.factory import create_bytes_io
>>> buf = create_bytes_io(Path("video.mp4"))
>>> # pass ``buf`` to PyAV, other libraries, etc.
"""

from __future__ import annotations

import io
from pathlib import Path


def create_bytes_io(path: Path | str) -> io.BytesIO:
    """Create a seekable ``BytesIO`` from a file on disk.

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
