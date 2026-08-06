"""Enroll speakers from reference audio and run full meeting identification.

Usage:
    uv run python test_voicetag_meeting.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "serve" / "voicetag"))

from voicetag_core import enroll, identify

# Speaker reference files
REF_DIR = Path("test-audio/speaker-ref")
SPEAKERS = {
    "黃": [REF_DIR / "黃.wav"],
    "文": [REF_DIR / "文.wav"],
    "婕": [REF_DIR / "婕.wav"],
    "陳": [REF_DIR / "陳.wav"],
}
OUTPUT_JSON = Path("output/voicetag/meeting_result.json")
PROFILES_JSON = Path("output/voicetag/meeting_profiles.json")


def main():
    # 1. Enroll all speakers
    print("=" * 60)
    print("Step 1: Enroll speakers")
    print("=" * 60)
    for name, paths in SPEAKERS.items():
        print(f"Enrolling '{name}' from {len(paths)} file(s)...")
        try:
            enroll(name, paths, device="cuda:0")
        except Exception as e:
            print(f"  ⚠️  Failed to enroll '{name}': {e}")

    # 2. Save profiles
    print()
    print("=" * 60)
    print("Step 2: Save profiles")
    print("=" * 60)
    from voicetag_core import _ensure_voicetag

    vt = _ensure_voicetag(device="cuda:0")
    vt.save(str(PROFILES_JSON))
    print(f"Profiles saved to {PROFILES_JSON}")

    # 3. Identify on full meeting audio
    print()
    print("=" * 60)
    print("Step 3: Identify on full meeting (40 min)")
    print("=" * 60)
    result = identify(
        audio_path="test-audio/保修工程會議.wav",
        profile_path=str(PROFILES_JSON),
        device="cuda:0",
    )

    # 4. Build output dict
    output = {
        "audio_path": "test-audio/保修工程會議.wav",
        "audio_duration": round(result.audio_duration, 3),
        "num_speakers": result.num_speakers,
        "processing_time": round(result.processing_time, 2),
        "enrolled_speakers": list(vt.enrolled_speakers),
        "segments": [],
    }

    speaker_count = {}
    overlap_count = 0
    for seg in result.segments:
        output["segments"].append(
            {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "duration": round(seg.end - seg.start, 3),
                "speaker": seg.speaker,
            }
        )
        if hasattr(seg, "speakers") and seg.speakers:
            overlap_count += 1
        else:
            speaker_count[seg.speaker] = speaker_count.get(seg.speaker, 0) + 1

    output["speaker_counts"] = speaker_count
    output["overlap_segments"] = overlap_count

    # Save
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nResult saved to {OUTPUT_JSON}")

    # Summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total segments:  {len(output['segments'])}")
    print(f"Overlap segments: {overlap_count}")
    print(
        f"Duration: {result.audio_duration:.1f}s ({result.audio_duration / 60:.1f} min)"
    )
    print(f"Processing time: {result.processing_time:.1f}s")
    print(f"Speaker breakdown:")
    for s, c in sorted(speaker_count.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c} segments")


if __name__ == "__main__":
    main()
