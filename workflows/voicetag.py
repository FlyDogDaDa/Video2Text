"""VoiceTag identification workflow.

End-to-end speaker identification pipeline:
1. Run diarization + identification via the official voicetag library
2. Return structured JSON of who spoke when

Usage (CLI):
    uv run -- python workflows/voicetag.py test-audio/2026_07_21_test.mp3

Usage (import):
    from workflows.voicetag import identify_audio
    result = identify_audio("test-audio/2026_07_21_test.mp3")
    print(result.to_json(indent=2))
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

# Ensure the serve/voicetag directory is on sys.path for voicetag_core import
_SERVE_VOICETAG = Path(__file__).resolve().parent.parent / "serve" / "voicetag"
if str(_SERVE_VOICETAG) not in sys.path:
    sys.path.insert(0, str(_SERVE_VOICETAG))

from voicetag_core import identify as _identify  # noqa: E402


def identify_audio(
    audio_path: str | Path,
    profile_path: str | Path | None = None,
    output_json: str | Path | None = None,
    device: str = "cuda:0",
    hf_token: str | None = None,
) -> dict[str, Any]:
    """Run speaker identification on an audio file.

    Parameters
    ----------
    audio_path:
        Path to the input audio file.
    profile_path:
        Optional path to saved speaker profiles (JSON).
    output_json:
        If provided, save the result to this path as JSON.
    device:
        Torch device: ``"cpu"``, ``"cuda:0"``, ``"mps"``.
    hf_token:
        HuggingFace token for pyannote model access.

    Returns
    -------
    dict
        JSON-serializable diarization result.
    """
    audio = Path(audio_path)
    if not audio.exists():
        raise FileNotFoundError(f"Input audio not found: {audio}")

    result = _identify(
        audio_path=str(audio),
        profile_path=str(profile_path) if profile_path else None,
        hf_token=hf_token,
        device=device,
    )

    # Build JSON-serializable dict
    output: dict[str, Any] = {
        "audio_path": str(audio),
        "audio_duration": result.audio_duration,
        "num_speakers": result.num_speakers,
        "processing_time": result.processing_time,
        "segments": [],
    }

    for seg in result.segments:
        segment: dict[str, Any] = {
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "duration": round(seg.end - seg.start, 3),
            "speaker": seg.speaker,
        }
        # Overlap segments carry extra info; speaker segments have confidence
        if hasattr(seg, "speakers") and seg.speakers:
            segment["speakers"] = seg.speakers
            segment["type"] = "OVERLAP"
        elif hasattr(seg, "confidence"):
            segment["confidence"] = round(seg.confidence, 4)
            segment["type"] = "SPEAKER"
        else:
            segment["type"] = "SPEAKER"
        output["segments"].append(segment)

    # Save to file if requested
    if output_json:
        out = Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"[voicetag] Result saved to {out}")

    return output


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="VoiceTag speaker identification")
    parser.add_argument("audio", help="Path to input audio file")
    parser.add_argument(
        "--profile", default=None, help="Path to speaker profiles JSON file"
    )
    parser.add_argument("--output", "-o", default=None, help="Output JSON file path")
    parser.add_argument(
        "--device",
        default="cuda:0",
        choices=["cpu", "cuda:0", "cuda:1", "mps"],
        help="Torch device (default: cuda:0)",
    )
    parser.add_argument("--hf-token", default=None, help="HuggingFace token")
    args = parser.parse_args()

    result = identify_audio(
        audio_path=args.audio,
        profile_path=args.profile,
        output_json=args.output,
        device=args.device,
        hf_token=args.hf_token,
    )

    # Print to stdout
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
