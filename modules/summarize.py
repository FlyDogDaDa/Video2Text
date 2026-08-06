"""多模態總結模組。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from framework.config import cfg


class SummaryConfig(BaseModel):
    """總結設定。

    Parameters
    ----------
    max_tokens :
        模型最大 token 數。
    temperature :
        生成溫度。
    top_p :
        Nucleus sampling 比例。
    """

    max_tokens: int = 24576
    temperature: float = 1.0
    top_p: float = 0.95


def generate_summary(audio: Path, video: Path) -> Path:
    """生成多模態總結。

    Parameters
    ----------
    audio :
        音訊逐字稿檔案路徑。
    video :
        視訊逐字稿檔案路徑。

    Returns
    -------
    Path
        總結檔案路徑（markdown 格式）。
    """
    # 1. 使用 cfg() 取得設定
    c = cfg("summarize", SummaryConfig)

    # 2. TODO: 實作總結邏輯

    # 3. 回傳測試路徑
    return Path("output.md")
