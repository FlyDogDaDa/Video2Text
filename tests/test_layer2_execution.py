"""Layer 2 execution tests — import checks and profile validation.

These tests verify that all modules can be imported successfully,
the workflow CLI is functional, and all profile YAML files are valid.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))


class TestModuleImports:
    """Test that all framework and module imports succeed."""

    def test_framework_config_import(self) -> None:
        """框架設定模組可以順利匯入 cfg 和 set_profile 函數。"""
        from framework.config import cfg, set_profile  # noqa: F401

        assert callable(cfg)
        assert callable(set_profile)

    def test_vad_import(self) -> None:
        """語音偵測模組可以順利匯入 detect_speech 函數。"""
        from modules.vad import detect_speech  # noqa: F401

        assert callable(detect_speech)

    def test_asr_import(self) -> None:
        """自動語音識別模組可以順利匯入 transcribe 函數。"""
        from modules.asr import transcribe  # noqa: F401

        assert callable(transcribe)

    def test_video_desc_import(self) -> None:
        """影片描述模組可以順利匯入 describe_frames 函數。"""
        from modules.video_desc import describe_frames  # noqa: F401

        assert callable(describe_frames)

    def test_clean_import(self) -> None:
        """逐字稿清理模組可以順利匯入 reduce_redundancy 函數。"""
        from modules.clean import reduce_redundancy  # noqa: F401

        assert callable(reduce_redundancy)

    def test_summarize_import(self) -> None:
        """摘要生成模組可以順利匯入 generate_summary 函數。"""
        from modules.summarize import generate_summary  # noqa: F401

        assert callable(generate_summary)

    def test_sam_audio_import(self) -> None:
        """SAM-Audio 分離模組可以順利匯入 separate_by_anchor 函數。"""
        from modules.sam_audio import separate_by_anchor  # noqa: F401

        assert callable(separate_by_anchor)


class TestWorkflowCLI:
    """Test that the workflow CLI entry point works."""

    def test_workflow_help(self) -> None:
        """workflow.py --help 能正常執行且不會崩潰。"""
        workflow_script = _project_root / "workflow.py"
        venv_python = _project_root / ".venv" / "bin" / "python3"
        if not venv_python.exists():
            venv_python = _project_root / ".venv" / "bin" / "python"
        result = subprocess.run(
            [str(venv_python), str(workflow_script), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "--input" in result.stdout
        assert "--profile" in result.stdout


class TestProfileYAML:
    """Test that all profile YAML files exist and are valid."""

    @pytest.mark.parametrize(
        "profile_name",
        ["default", "research", "final"],
    )
    def test_profile_exists_and_valid(self, profile_name: str) -> None:
        """profiles/{name}.yaml 是合法 YAML 且至少包含一個 section。"""
        profile_path = _project_root / "profiles" / f"{profile_name}.yaml"

        assert profile_path.exists(), f"Profile file not found: {profile_path}"

        with open(profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data is not None, f"Profile is empty: {profile_path}"
        assert isinstance(data, dict), f"Profile root is not a dict: {profile_path}"
        assert len(data) > 0, f"Profile has no sections: {profile_path}"
