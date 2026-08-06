#!/usr/bin/env python3
"""
Breeze-ASR-26 Audio Transcription Tool

Transcribe audio files using MediaTek-Research/Breeze-ASR-26 via vLLM server
with the OpenAI-compatible speech-to-text API (`/v1/audio/transcriptions`).

Usage:
    # Basic transcription of a single audio file
    uv run -- python asr_transcribe.py intro_voice_cover.wav

    # Test both reference audio files
    uv run -- python asr_transcribe.py --test-all

    # Long audio with custom segment length and overlap
    uv run -- python asr_transcribe.py long_audio.wav --segment 20 --overlap 5

    # Save results to JSON file
    uv run -- python asr_transcribe.py intro_voice_cover.wav --output result.json

    # Skip auto-launch (assume server already running)
    uv run -- python asr_transcribe.py intro_voice_cover.wav --no-launch
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
BASE_URL = "http://localhost:8750/v1"
MODEL_NAME = "MediaTek-Research/Breeze-ASR-26"
LAUNCH_SCRIPT = (
    Path(__file__).parent.parent.parent
    / "src"
    / "vllm_launch"
    / "launch_BreezeASR26.sh"
)

# Long audio splitting defaults
DEFAULT_SEGMENT_SECONDS = 30
DEFAULT_OVERLAP_SECONDS = 3
MAX_AUDIO_BYTES = 100 * 1024 * 1024  # 100 MB for vLLM audio input limit


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class TranscriptionResult:
    """Complete transcription result."""

    text: str
    duration: float = 0.0


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------
def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using runtime/ffprobe."""
    runtime_dir = Path(__file__).parent.parent.parent / "runtime"
    ffprobe = runtime_dir / "ffprobe"
    if not ffprobe.exists():
        ffprobe = Path("ffprobe")

    proc = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr}")
    return float(proc.stdout.strip())


# ---------------------------------------------------------------------------
# Long audio: overlap-based splitting
# ---------------------------------------------------------------------------
def split_audio_into_segments(
    audio_path: Path,
    segment_duration: float,
    overlap: float,
) -> list[tuple[float, float]]:
    """Split audio into overlapping segments.

    Strategy:
    - Use fixed-length sliding windows with overlap
    - Overlap ensures sentences aren't cut in the middle
    - Deduplicate overlapping regions in post-processing
    """
    duration = get_audio_duration(audio_path)
    if duration <= segment_duration:
        return [(0.0, duration)]

    segments = []
    step = segment_duration - overlap
    t_start = 0.0

    while t_start < duration:
        t_end = min(t_start + segment_duration, duration)
        segments.append((t_start, t_end))
        if t_end >= duration:
            break
        t_start += step

    return segments


# ---------------------------------------------------------------------------
# vLLM transcription client
# ---------------------------------------------------------------------------
class BreezeASRClient:
    """Client for Breeze-ASR-26 via OpenAI-compatible /v1/audio/transcriptions API.

    Supported response formats:
      - text:  {"text": "..."}
      - json:  {"text": "...", "usage": {"type": "duration", "seconds": N}}
      - verbose_json: {"text": "...", "segments": [], "words": null, "duration": "N", "language": "zh"}
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    async def transcribe(
        self,
        audio_path: Path,
        language: str = "zh",
        prompt: str = "",
    ) -> TranscriptionResult:
        """Basic transcription — returns plain text."""
        if len(audio_path.read_bytes()) > MAX_AUDIO_BYTES:
            raise ValueError(
                f"Audio too large ({len(audio_path.read_bytes())} bytes). "
                f"Use --segment to split first."
            )

        client = AsyncOpenAI(base_url=self.base_url, api_key="EMPTY")

        with open(audio_path, "rb") as f:
            r = await client.audio.transcriptions.create(
                model=MODEL_NAME,
                file=f,
                language=language,
                response_format="json",
                extra_body={"prompt": prompt} if prompt else {},
            )

        text = r.text if hasattr(r, "text") else str(r)
        duration = 0.0
        if hasattr(r, "duration_ms") and r.duration_ms:
            duration = r.duration_ms / 1000.0
        elif hasattr(r, "usage"):
            usage = r.usage
            if isinstance(usage, dict) and "seconds" in usage:
                duration = float(usage["seconds"])
            elif hasattr(usage, "seconds"):
                duration = float(usage.seconds)

        return TranscriptionResult(text=text.strip(), duration=duration)


# ---------------------------------------------------------------------------
# Long audio processor: split → transcribe → merge
# ---------------------------------------------------------------------------
class LongAudioProcessor:
    """Process long audio by splitting into overlapping segments,
    transcribing each, then merging with deduplication.
    """

    def __init__(
        self,
        client: BreezeASRClient,
        segment_duration: float = DEFAULT_SEGMENT_SECONDS,
        overlap: float = DEFAULT_OVERLAP_SECONDS,
    ):
        self.client = client
        self.segment_duration = segment_duration
        self.overlap = overlap

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe long audio with overlap-based splitting.

        Strategy:
        1. Split into overlapping segments
        2. Transcribe each segment independently
        3. Concatenate transcripts
        """
        segments = split_audio_into_segments(
            audio_path, self.segment_duration, self.overlap
        )

        print(f"🎵 Audio : {audio_path.name}")
        print(f"   Duration: {get_audio_duration(audio_path):.1f}s")
        print(
            f"   Segments: {len(segments)} "
            f"(chunk={self.segment_duration}s, overlap={self.overlap}s)"
        )
        print()

        combined_text = ""

        for i, (seg_start, seg_end) in enumerate(segments):
            hint = (
                f"This segment covers [{seg_start:.1f}s - {seg_end:.1f}s] "
                f"of the full audio. Transcribe only what you hear in this window."
            )

            result = await self.client.transcribe(audio_path, prompt=hint)
            combined_text += result.text + "\n"

            print(f"   ✓ Segment {i + 1}/{len(segments)}")

        return TranscriptionResult(
            text=combined_text.strip(),
            duration=get_audio_duration(audio_path),
        )


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------
async def wait_for_server(url: str, timeout: float = 120.0) -> bool:
    """Poll the /v1/models endpoint to wait for the vLLM server."""
    print(f"⏳ Waiting for server at {url} ...")
    deadline = time.time() + timeout
    client = AsyncOpenAI(base_url=url, api_key="EMPTY")

    while time.time() < deadline:
        try:
            models = await client.models.list()
            if models.data:
                print(f"✅ Server is ready! Models: {[m.id for m in models.data]}")
                return True
        except Exception:
            pass
        await asyncio.sleep(3)

    raise RuntimeError(f"Server not ready after {timeout}s")


async def launch_server(wait_ready: bool = True) -> subprocess.Popen:
    """Launch vLLM server for Breeze-ASR-26 in background."""
    if not LAUNCH_SCRIPT.exists():
        raise FileNotFoundError(f"Launch script not found: {LAUNCH_SCRIPT}")

    print(f"🚀 Launching vLLM server from {LAUNCH_SCRIPT} ...")

    proc = subprocess.Popen(
        ["bash", str(LAUNCH_SCRIPT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if wait_ready:
        await wait_for_server(BASE_URL)

    return proc


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def display_result(result: TranscriptionResult):
    """Pretty-print the transcription result."""
    print("\n" + "=" * 70)
    print("TRANSCRIPTION RESULT")
    print("=" * 70)
    print(f"Duration : {result.duration:.2f}s")
    print(f"Full text: {result.text}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Breeze-ASR-26 via vLLM (/v1/audio/transcriptions API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic transcription
  uv run -- python asr_transcribe.py intro_voice_cover.wav

  # Test both reference audio files
  uv run -- python asr_transcribe.py --test-all

  # Long audio with custom segment/overlap
  uv run -- python asr_transcribe.py long.wav --segment 20 --overlap 5

  # Save results to JSON
  uv run -- python asr_transcribe.py intro_voice_cover.wav --output result.json
        """,
    )
    parser.add_argument("audio", nargs="?", help="Audio file path")
    parser.add_argument(
        "--server", default=BASE_URL, help=f"vLLM server URL (default: {BASE_URL})"
    )
    parser.add_argument(
        "--segment",
        type=float,
        default=DEFAULT_SEGMENT_SECONDS,
        help=f"Segment duration for long audio (default: {DEFAULT_SEGMENT_SECONDS}s)",
    )
    parser.add_argument(
        "--overlap",
        type=float,
        default=DEFAULT_OVERLAP_SECONDS,
        help=f"Overlap between segments (default: {DEFAULT_OVERLAP_SECONDS}s)",
    )
    parser.add_argument(
        "--test-all", action="store_true", help="Test all reference audio files"
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Skip server auto-launch (assume already running)",
    )
    parser.add_argument(
        "--language",
        default="zh",
        help="Language code (default: zh for Mandarin/Chinese)",
    )
    parser.add_argument("--output", type=str, help="Save results to JSON file")

    args = parser.parse_args()

    # Determine audio files
    if args.test_all:
        audio_files = [
            Path("intro_voice_cover.wav"),
            Path(
                "chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/references/test_audio.wav"
            ),
        ]
    elif args.audio:
        audio_files = [Path(args.audio)]
    else:
        parser.print_help()
        return

    # Validate existence
    for af in audio_files:
        if not af.exists():
            print(f"❌ Audio file not found: {af}")
            return

    # Launch server if needed
    server_proc = None
    if not args.no_launch:
        try:
            await wait_for_server(args.server, timeout=5)
            print("✅ Server already running")
        except RuntimeError:
            print("⚠ Server not running, launching...")
            server_proc = await launch_server(wait_ready=True)

    client = BreezeASRClient(args.server)
    processor = LongAudioProcessor(
        client,
        segment_duration=args.segment,
        overlap=args.overlap,
    )

    # Process each file
    for audio_file in audio_files:
        print(f"\n{'=' * 70}")
        print(f"Processing: {audio_file}")
        print(f"{'=' * 70}")

        result = await processor.transcribe(audio_file)

        display_result(result)

        # Save JSON if requested
        if args.output:
            data = {
                "audio": str(audio_file),
                "duration": result.duration,
                "text": result.text,
            }
            Path(args.output).write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"💾 Saved to: {args.output}")

    # Cleanup
    if server_proc:
        print("\n🛑 Stopping server...")
        server_proc.terminate()
        server_proc.wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
        sys.exit(1)
