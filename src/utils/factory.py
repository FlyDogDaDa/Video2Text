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

import numpy as np


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


def create_slices_indices(
    start: float,  # 切片起點
    end: float,  # 切片終點
    window: float,  # 切片長度
    step: float,  # 切片位移
) -> np.ndarray:
    """
    產生每個切片的位置，並進行輸入參數的邊緣情況檢查。
    """
    # 1. 數值合理性檢查
    if step <= 0:
        raise ValueError(f"步長 (step) 必須大於 0，當前輸入為: {step}")
    if window <= 0:
        raise ValueError(f"視窗長度 (window) 必須大於 0，當前輸入為: {window}")
    if start >= end:
        raise ValueError(f"起點 (start: {start}) 必須小於終點 (end: {end})")
    if window > (end - start):
        # 視窗長度超過總區間長度，直接返回整個區間
        return np.array([[start, end]])

    # 2. 產生起始點
    starts = np.arange(start, end - window, step)

    # 若因為浮點數精度等極端原因導致未產生起點，返回空陣列
    if len(starts) == 0:
        return np.empty((0, 2))

    # 3. 計算終點（終點為起點加上 window，但最高不能超過整體的終點 end）
    # 這裡將原本的 .clip(0, window) 修正為以 end 為上限
    ends = np.minimum(starts + window, end)

    # 4. 打包與回傳
    return np.column_stack((starts, ends))
