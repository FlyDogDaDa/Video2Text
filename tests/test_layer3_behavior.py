"""Behavior tests for framework/config.py (layer 3).

Verifies cfg(), set_profile(), and get_profile_path() against YAML profiles
using tmp_path for full isolation between every test case.
"""

import os
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from video2text.framework.config import cfg, set_profile

# ── Pydantic models (mirrors module config classes) ──────────────────────────


class VadConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    threshold: float = 0.5
    min_silence_duration_ms: int = 300
    chunk_seconds: float = 300.0


class AsrConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "MediaTek-Research/Breeze-ASR-26"
    batch_size: int = 64
    language: str = "zh"


class VideoDescConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fps: float = 1.0
    max_tokens: int = 24576
    temperature: float = 1.0


class CleanConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chunk_size: int = 20
    temperature: float = 1.0


class SummaryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_tokens: int = 24576
    temperature: float = 1.0
    top_p: float = 0.95


# ── YAML generators ──────────────────────────────────────────────────────────


DEFAULT_YAML = """\
vad:
  threshold: 0.5
  min_silence_duration_ms: 300
  chunk_seconds: 300.0

asr:
  model: "MediaTek-Research/Breeze-ASR-26"
  batch_size: 64
  language: "zh"

video_desc:
  fps: 1.0
  max_tokens: 24576
  temperature: 1.0

clean:
  chunk_size: 20
  temperature: 1.0

summarize:
  max_tokens: 24576
  temperature: 1.0
  top_p: 0.95
"""

RESEARCH_YAML = """\
vad:
  threshold: 0.4
  chunk_seconds: 180

asr:
  batch_size: 32
"""

FINAL_YAML = """\
summarize:
  temperature: 0.7

asr:
  model: "google/gemma-4-12B-it-qat-w4a16-ct"
"""


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_profiles(tmp_path: Path):
    """Create an isolated set of profile YAMLs and switch cwd into it."""
    orig_cwd = os.getcwd()

    profiles = tmp_path / "profiles"
    profiles.mkdir()

    (profiles / "default.yaml").write_text(DEFAULT_YAML)
    (profiles / "research.yaml").write_text(RESEARCH_YAML)
    (profiles / "final.yaml").write_text(FINAL_YAML)

    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(orig_cwd)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_cfg_returns_config_not_dict(tmp_profiles: Path):
    """cfg() 回傳 Pydantic 模型實例，不是 dict。"""
    set_profile("profiles/default.yaml")
    obj = cfg("vad", VadConfig)

    assert isinstance(obj, VadConfig)
    assert not isinstance(obj, dict)


def test_cfg_uses_set_profile_path(tmp_profiles: Path):
    """cfg() 使用 set_profile() 設定的路徑讀取 YAML。"""
    set_profile("profiles/research.yaml")
    assert cfg("vad", VadConfig).threshold == 0.4

    set_profile("profiles/default.yaml")
    assert cfg("vad", VadConfig).threshold == 0.5


def test_set_profile_changes_cfg_values(tmp_profiles: Path):
    """set_profile(research.yaml) 後 cfg 值反映 research profile。"""
    set_profile("profiles/research.yaml")

    assert cfg("vad", VadConfig).threshold == 0.4
    assert cfg("asr", AsrConfig).batch_size == 32


def test_set_profile_uses_defaults(tmp_profiles: Path):
    """YAML 中不存在的欄位會使用 Pydantic 預設值，不拋 KeyError。"""
    set_profile("profiles/research.yaml")

    vad = cfg("vad", VadConfig)
    assert vad.threshold == 0.4
    assert vad.chunk_seconds == 180.0
    assert vad.min_silence_duration_ms == 300

    asr = cfg("asr", AsrConfig)
    assert asr.batch_size == 32
    assert asr.model == "MediaTek-Research/Breeze-ASR-26"
    assert asr.language == "zh"


def test_cfg_extra_yaml_ignored(tmp_profiles: Path):
    """YAML 中包含 config 模型沒有的欄位時不會 crash。"""
    extra_yaml = DEFAULT_YAML.replace(
        "chunk_seconds: 300.0\n",
        'chunk_seconds: 300.0\n  extra_field: "should_be_ignored"\n',
    )
    (tmp_profiles / "profiles" / "default.yaml").write_text(extra_yaml)

    set_profile("profiles/default.yaml")
    obj = cfg("vad", VadConfig)

    assert isinstance(obj, VadConfig)
    assert obj.threshold == 0.5


def test_cfg_unknown_key_returns_defaults(tmp_profiles: Path):
    """讀取 YAML 中不存在的 key 時，回傳模型預設值（不拋錯）。"""
    obj = cfg("nonexistent_section_xyz", VadConfig)

    # 因為 data.get(key, {}) 回傳空 dict，Pydantic 使用所有預設值
    assert isinstance(obj, VadConfig)
    assert obj.threshold == 0.5
    assert obj.min_silence_duration_ms == 300
    assert obj.chunk_seconds == 300.0


def test_set_profile_is_global(tmp_profiles: Path):
    """set_profile() 的影響是全域的，所有後續 cfg() 呼叫都使用新設定。"""
    set_profile("profiles/research.yaml")

    assert cfg("vad", VadConfig).threshold == 0.4
    assert cfg("asr", AsrConfig).batch_size == 32

    set_profile("profiles/default.yaml")

    assert cfg("vad", VadConfig).threshold == 0.5
    assert cfg("asr", AsrConfig).batch_size == 64

    set_profile("profiles/final.yaml")

    assert cfg("summarize", SummaryConfig).temperature == 0.7
    assert cfg("asr", AsrConfig).model == "google/gemma-4-12B-it-qat-w4a16-ct"
