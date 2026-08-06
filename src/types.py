"""Video2Text core data models.

Pydantic schemas for the structured output of each window slice.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SliceResult(BaseModel, frozen=True):
    """Structured result for a single video window slice.

    Flat schema designed to minimize LLM cognitive load:
    - No nested sub-objects (zero indent tracking)
    - Three mutually exclusive content fields (classify, don't organize)
    - Consistent ``None`` semantics (absent vs. present)

    .. code-block:: json

        {
            "start_at": 0.0,
            "end_at": 30.0,
            "visual": "鏡頭掃過整間房間，牆上掛著一張世界地圖",
            "dialogue": "[John]: 是的，我們要前往柏林。",
            "sound": "輕柔的背景音樂"
        }

    Or with absent content:

    .. code-block:: json

        {
            "start_at": 30.0,
            "end_at": 60.0,
            "visual": "螢幕出現白色字幕：「三年後」",
            "dialogue": null,
            "sound": null
        }
    """

    start_at: float = Field(ge=0, description="Start timestamp in seconds")
    end_at: float = Field(ge=0, description="End timestamp in seconds")
    visual: str | None = Field(
        default=None,
        description="What happens visually in this window (actions, scenes, text on screen)",
    )
    dialogue: str | None = Field(
        default=None,
        description="Spoken dialogue, use [Speaker]: format when speaker is identifiable",
    )
    sound: str | None = Field(
        default=None,
        description="Non-speech audio: music, SFX, ambient sounds",
    )
