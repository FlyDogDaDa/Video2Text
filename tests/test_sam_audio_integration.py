"""Integration tests for SAM-Audio client-server communication.

Starts the uvicorn server in a subprocess, verifies endpoints work,
then shuts the server down.
"""

import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

_project_root = Path("/home/b11223209/workspace/ProgramDevelopment/Video2Text")
sys.path.insert(0, str(_project_root))

SERVER_DIR = _project_root / "serve" / "sam-audio"


class TestIntegration:
    """End-to-end tests: server + client communication."""

    @pytest.fixture(scope="class", autouse=True)
    def server_proc(self) -> subprocess.Popen:
        """Start the server once for all tests in this class."""
        env = {
            **dict(__import__("os").environ),
            "PYTHONPATH": str(_project_root) + ":" + str(SERVER_DIR),
            "VIRTUAL_ENV": str(SERVER_DIR / ".venv"),
        }
        proc = subprocess.Popen(
            [
                str(SERVER_DIR / ".venv" / "bin" / "python"),
                str(SERVER_DIR / "server.py"),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Wait for startup
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                resp = httpx.get("http://localhost:8000/health", timeout=2)
                if resp.status_code == 200:
                    yield proc
                    return
            except httpx.RequestError:
                pass
            time.sleep(0.5)
        proc.kill()
        pytest.skip("Server did not start")

    def test_health_endpoint(self, server_proc: subprocess.Popen) -> None:
        """Server /health 端點可以正常回傳 GPU 狀態。"""
        resp = httpx.get("http://localhost:8000/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "gpu_available" in data
        assert "gpu_count" in data

    def test_separate_file_not_found(self, server_proc: subprocess.Popen) -> None:
        """伺服器對不存在的檔案回傳 404。"""
        resp = httpx.post(
            "http://localhost:8000/separate",
            json={
                "audio_path": "/tmp/nonexistent_sam_audio_test.wav",
                "anchors": [["+", 0.1, 0.9]],
            },
            timeout=30,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_separate_invalid_request(self, server_proc: subprocess.Popen) -> None:
        """伺服器對無效請求回傳 422。"""
        resp = httpx.post(
            "http://localhost:8000/separate",
            json={"audio_path": "/tmp/test.wav"},  # missing anchors
            timeout=5,
        )
        assert resp.status_code == 422

    @pytest.mark.skip(reason="Requires actual SAM-Audio model download and GPU")
    def test_separation_pipeline(
        self, server_proc: subprocess.Popen, tmp_path: Path
    ) -> None:
        """完整流程：client → server → 回傳 SeparationResult。"""
        import wave

        # Create test audio
        audio_path = tmp_path / "test.wav"
        with wave.open(str(audio_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 32000)

        from modules.sam_audio import separate_by_anchor

        result = separate_by_anchor(
            audio_path,
            [["+", 0.1, 0.9]],
            "single speaker",
            server_url="http://localhost:8000",
        )

        assert isinstance(result.speaker, Path)
        assert isinstance(result.residual, Path)
        assert result.speaker.exists()
        assert result.residual.exists()
