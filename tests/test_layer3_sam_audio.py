"""Tests for sam_audio.py (HTTP client layer).

Verifies SeparationResult model and separate_by_anchor() client behavior
using httpx mock to avoid requiring the remote server.
"""

import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from modules.sam_audio import SeparationResult, separate_by_anchor

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_audio_file(tmp_path: Path):
    """Create a fake audio file path for testing output paths."""
    audio = tmp_path / "test_input.wav"
    audio.write_bytes(b"fake audio data")
    return audio


# ── Tests: SeparationResult ─────────────────────────────────────────────────


class TestSeparationResult:
    """Tests for the SeparationResult Pydantic model."""

    def test_has_speaker_field(self) -> None:
        """SeparationResult 包含 speaker 欄位，型別為 Path。"""
        result = SeparationResult(
            speaker=Path("/output/speaker.wav"),
            residual=Path("/output/residual.wav"),
        )

        assert isinstance(result.speaker, Path)

    def test_has_residual_field(self) -> None:
        """SeparationResult 包含 residual 欄位，型別為 Path。"""
        result = SeparationResult(
            speaker=Path("/output/speaker.wav"),
            residual=Path("/output/residual.wav"),
        )

        assert isinstance(result.residual, Path)

    def test_speaker_and_residual_are_paths(self) -> None:
        """speaker 與 residual 都是 Path 物件。"""
        result = SeparationResult(
            speaker=Path("/output/speaker.wav"),
            residual=Path("/output/residual.wav"),
        )

        assert isinstance(result.speaker, Path)
        assert isinstance(result.residual, Path)

    def test_can_serialize(self) -> None:
        """SeparationResult 可以序列化（dict）。"""
        result = SeparationResult(
            speaker=Path("/output/speaker.wav"),
            residual=Path("/output/residual.wav"),
        )

        d = result.model_dump()
        assert isinstance(d["speaker"], Path)
        assert d["speaker"].name == "speaker.wav"
        assert isinstance(d["residual"], Path)
        assert d["residual"].name == "residual.wav"

    def test_json_roundtrip(self) -> None:
        """SeparationResult 可以 JSON 序列化再還原。"""
        original = SeparationResult(
            speaker=Path("/output/speaker.wav"),
            residual=Path("/output/residual.wav"),
        )

        restored = SeparationResult.model_validate_json(original.model_dump_json())
        assert restored.speaker == original.speaker
        assert restored.residual == original.residual


# ── Tests: separate_by_anchor() client ──────────────────────────────────────


class TestSeparateByAnchorClient:
    """Tests for the separate_by_anchor() HTTP client."""

    def test_sends_correct_request(
        self, tmp_audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """separate_by_anchor() 發送正確的 HTTP POST 請求。"""
        called_url = []
        called_json = []

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "speaker": str(tmp_audio_file.parent / "test_input_speaker.wav"),
                    "residual": str(tmp_audio_file.parent / "test_input_residual.wav"),
                    "status": "done",
                }

            def raise_for_status(self):
                pass

        def fake_post(url: str, json: dict, timeout: float):
            called_url.append(url)
            called_json.append(json)
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)

        anchors = [["+", 0.5, 3.2], ["-", 0.0, 0.5]]
        result = separate_by_anchor(
            tmp_audio_file,
            anchors,
            "single speaker",
            server_url="http://localhost:9999",
        )

        assert called_url == ["http://localhost:9999/separate"]
        assert called_json[0]["audio_path"] == str(tmp_audio_file)
        assert called_json[0]["anchors"] == anchors
        assert called_json[0]["description"] == "single speaker"
        assert isinstance(result, SeparationResult)

    def test_defaults_output_paths(
        self, tmp_audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """不指定輸出路徑時，使用預設命名規則。"""
        call_json = []

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "speaker": str(tmp_audio_file.parent / "test_input_speaker.wav"),
                    "residual": str(tmp_audio_file.parent / "test_input_residual.wav"),
                    "status": "done",
                }

            def raise_for_status(self):
                pass

        def fake_post(url: str, json: dict, timeout: float):
            call_json.append(json)
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)

        separate_by_anchor(tmp_audio_file, [["+", 0.0, 1.0]])

        assert call_json[0]["speaker_output"] == str(
            tmp_audio_file.parent / "test_input_speaker.wav"
        )
        assert call_json[0]["residual_output"] == str(
            tmp_audio_file.parent / "test_input_residual.wav"
        )

    def test_custom_output_paths(
        self, tmp_audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """自訂輸出路徑會被正確傳遞到請求中。"""
        call_json = []
        custom_spk = "/custom/output/speaker.wav"
        custom_res = "/custom/output/residual.wav"

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"speaker": custom_spk, "residual": custom_res, "status": "done"}

            def raise_for_status(self):
                pass

        def fake_post(url: str, json: dict, timeout: float):
            call_json.append(json)
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)

        separate_by_anchor(
            tmp_audio_file,
            [["+", 0.0, 1.0]],
            speaker_output=Path(custom_spk),
            residual_output=Path(custom_res),
        )

        assert call_json[0]["speaker_output"] == custom_spk
        assert call_json[0]["residual_output"] == custom_res

    def test_default_server_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """預設連線到 localhost:8000。"""
        called_url = []

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "speaker": "/out/speaker.wav",
                    "residual": "/out/residual.wav",
                    "status": "done",
                }

            def raise_for_status(self):
                pass

        def fake_post(url: str, json: dict, timeout: float):
            called_url.append(url)
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)

        separate_by_anchor(Path("/tmp/test.wav"), [["+", 0.0, 1.0]])

        assert called_url[0] == "http://localhost:8000/separate"

    def test_raises_on_http_error(
        self, tmp_audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """伺服器回傳非 2xx 時拋出 httpx.HTTPStatusError。"""
        import httpx

        class FakeResponse:
            status_code = 500

            def raise_for_status(self):
                raise httpx.HTTPStatusError("Server Error", request=None, response=None)

        monkeypatch.setattr("httpx.post", lambda *a, **kw: FakeResponse())

        with pytest.raises(httpx.HTTPStatusError):
            separate_by_anchor(tmp_audio_file, [["+", 0.0, 1.0]])

    def test_returns_path_objects(
        self, tmp_audio_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """回傳的 SeparationResult 中 speaker 和 residual 都是 Path 物件。"""

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "speaker": str(tmp_audio_file.parent / "out_spk.wav"),
                    "residual": str(tmp_audio_file.parent / "out_res.wav"),
                    "status": "done",
                }

            def raise_for_status(self):
                pass

        monkeypatch.setattr("httpx.post", lambda *a, **kw: FakeResponse())

        result = separate_by_anchor(tmp_audio_file, [["+", 0.0, 1.0]])

        assert isinstance(result.speaker, Path)
        assert isinstance(result.residual, Path)
        assert result.speaker.name == "out_spk.wav"
        assert result.residual.name == "out_res.wav"
