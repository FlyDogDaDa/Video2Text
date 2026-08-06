#!/usr/bin/env python3
"""Create a short 40-second test audio clip from /tmp/test.mp3."""

import shutil
import subprocess
from pathlib import Path

SRC = Path("/tmp/test.mp3")
DST = Path("/tmp/test_short.wav")

print(f"Extracting 40s clip from {SRC}...")

result = subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-i",
        str(SRC),
        "-ss",
        "0",
        "-t",
        "40",
        "-ar",
        "16000",  # 16kHz for SAM-Audio
        "-ac",
        "1",  # mono
        "-c:a",
        "pcm_s16le",  # WAV format
        str(DST),
    ],
    capture_output=True,
    text=True,
)

if result.returncode == 0:
    size = DST.stat().st_size
    print(f"✅ Created: {DST} ({size:,} bytes)")

    # Verify
    result2 = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(DST),
        ],
        capture_output=True,
        text=True,
    )
    print(f"   Duration: {result2.stdout.strip()} seconds")
else:
    print(f"❌ ffmpeg error: {result.stderr}")
