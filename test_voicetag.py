#!/usr/bin/env python3
"""測試 VoiceTag 完整流程：enroll → save → identify → JSON 輸出"""

import json
import os
import sys
from pathlib import Path

# Preload .env and token before any voicetag import
os.environ["HF_TOKEN"] = "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"

sys.path.insert(0, str(Path(__file__).resolve().parent / "serve" / "voicetag"))

from voicetag import VoiceTag, VoiceTagConfig
from voicetag_core import enroll, identify

PROFILES_DIR = Path(__file__).parent / "output" / "voicetag"


def main():
    print("=" * 60)
    print("VoiceTag 完整測試：Enroll → Save → Identify")
    print("=" * 60)

    # ── Step 1: Enroll speaker from reference ──────────────────────
    print("\n[Step 1] 用參考音訊註冊說話人")
    ref_audio = Path("test-audio/speech-reference.mp3")
    print(f"  參考音訊：{ref_audio.name} ({ref_audio.stat().st_size / 1024:.0f} KB)")

    config = VoiceTagConfig(
        hf_token=os.environ["HF_TOKEN"],
        device="cuda:0",
        similarity_threshold=0.75,
    )

    # enroll() internally calls _ensure_voicetag() and returns the shared instance
    # We capture the returned tuple but also access the global VT for subsequent ops
    enrolled_name, wav_paths = enroll(
        name="boss",
        audio_paths=[str(ref_audio)],
        hf_token=os.environ["HF_TOKEN"],
        device="cuda:0",
    )

    # Get the cached global instance (created by enroll)
    from voicetag_core import _vt as cached_vt

    vt = cached_vt
    if vt is None:
        vt = VoiceTag(config=config)

    print(f"  已註冊：{vt.enrolled_speakers}")
    profile = vt._encoder._profiles.get("boss")
    if profile:
        print(f"  embedding dimensions: {len(profile.embedding)}")

    # ── Step 2: Save profile ──────────────────────────────────────
    profile_file = PROFILES_DIR / "profiles.json"
    profile_file.parent.mkdir(parents=True, exist_ok=True)
    vt.save(str(profile_file))
    print(f"\n[Step 2] 已儲存 profiles 到：{profile_file}")

    # ── Step 3: Identify on test audio ────────────────────────────
    test_audio = Path("test-audio/2026_07_21_test.mp3")
    print(
        f"\n[Step 3] 測試音訊辨識：{test_audio.name} ({test_audio.stat().st_size / 1024 / 1024:.1f} MB)"
    )

    result = identify(
        audio_path=str(test_audio),
        profile_path=str(profile_file),
        hf_token=None,  # from env var
        device="cuda:0",
    )

    print(f"\n{'=' * 60}")
    print("辨識結果")
    print(f"{'=' * 60}")
    print(f"  音訊長度：{result.audio_duration:.1f}s")
    print(f"  說話人數：{result.num_speakers}")
    print(f"  處理時間：{result.processing_time:.1f}s")
    print(f"  分段數：{len(result.segments)}")

    # Count speakers
    speaker_counts = {}
    for seg in result.segments:
        name = seg.speaker
        if hasattr(seg, "speakers") and seg.speakers:
            for s in seg.speakers:
                speaker_counts[s] = speaker_counts.get(s, 0) + 1
        else:
            speaker_counts[name] = speaker_counts.get(name, 0) + 1

    print(f"\n  各說話人出現次數：")
    for name, count in sorted(speaker_counts.items(), key=lambda x: -x[1]):
        print(f"    {name}: {count} 個分段")

    # Print segments timeline
    print(f"\n  時間軸：")
    for i, seg in enumerate(result.segments):
        if hasattr(seg, "speakers") and seg.speakers:
            speakers_str = "+".join(seg.speakers)
            print(
                f"    [{i + 1:>2}] {seg.start:6.1f}s - {seg.end:6.1f}s  OVERLAP({speakers_str})  "
                f"duration={seg.end - seg.start:.1f}s"
            )
        else:
            print(
                f"    [{i + 1:>2}] {seg.start:6.1f}s - {seg.end:6.1f}s  "
                f"{seg.speaker:<12s}  conf={seg.confidence:.2f}  "
                f"duration={seg.end - seg.start:.1f}s"
            )

    # ── Step 4: Save JSON ────────────────────────────────────────
    output_json = PROFILES_DIR / "result.json"

    output_data = {
        "audio_path": str(test_audio),
        "audio_duration": result.audio_duration,
        "num_speakers": result.num_speakers,
        "processing_time": result.processing_time,
        "segments": [],
    }

    for seg in result.segments:
        segment = {
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "duration": round(seg.end - seg.start, 3),
            "speaker": seg.speaker,
            "confidence": round(seg.confidence, 4)
            if hasattr(seg, "confidence")
            else None,
        }
        if hasattr(seg, "speakers") and seg.speakers:
            segment["speakers"] = seg.speakers
            segment["type"] = "OVERLAP"
        else:
            segment["type"] = "SPEAKER"
        output_data["segments"].append(segment)

    output_json.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    print(f"\n[Step 4] JSON 已儲存：{output_json}")

    # ── Summary ──────────────────────────────────────────────────
    identified_count = sum(
        1 for s in output_data["segments"] if s.get("speaker") == "boss"
    )
    total_segments = len(output_data["segments"])
    print(f"\n{'=' * 60}")
    print(f"總結：{identified_count}/{total_segments} 個分段被識別為 'boss'")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
