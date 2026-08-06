"""Video2Text workflow — main entry point.

Usage:
    uv run python workflow.py --input video.mp4
    uv run python workflow.py --input video.mp4 --profile profiles/research.yaml
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from framework.config import set_profile
from modules.asr import transcribe
from modules.clean import reduce_redundancy
from modules.summarize import generate_summary
from modules.vad import detect_speech
from modules.video_desc import describe_frames


def main():
    parser = argparse.ArgumentParser(description="Video2Text video processing pipeline")
    parser.add_argument("--input", required=True, type=Path, help="Input video file")
    parser.add_argument(
        "--profile",
        default="profiles/default.yaml",
        type=Path,
        help="Profile YAML file",
    )
    args = parser.parse_args()

    # Set profile (global state for all modules)
    set_profile(str(args.profile))

    # Run pipeline (explicit function calls, no super-function)
    print(f"Processing: {args.input}")
    print(f"Profile: {args.profile}")

    segments = detect_speech(args.input)
    print(f"  VAD: {len(segments)} speech segments detected")

    transcript = transcribe(args.input, segments)
    print(f"  ASR: {transcript}")

    video_desc_result = describe_frames(args.input)
    print(f"  Video desc: {video_desc_result}")

    cleaned = reduce_redundancy(transcript)
    print(f"  Clean: {cleaned}")

    summary = generate_summary(cleaned, video_desc_result)
    print(f"  Summary: {summary}")

    print(f"\nDone → {summary}")


if __name__ == "__main__":
    main()
