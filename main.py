"""Video2Text console test — pipeline end-to-end (audio + video)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from vllm import LLM

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

VIDEO_PATH = os.getenv(
    "VIDEO_PATH",
    str(Path(__file__).parent / "short_test.mp4"),
)


def main():
    """Run pipeline: load model → slice video → extract structured."""
    model_path = os.getenv("VLLM_MODEL", "google/gemma-4-12B-it-qat-w4a16-ct")

    print("\n" + "#" * 60)
    print("# VIDEO2TEXT PIPELINE TEST")
    print(f"# Model: {model_path}")
    print(f"# Video: {VIDEO_PATH}")
    print("#" * 60 + "\n")

    # Step 1: Load model
    llm: LLM = load_model(model_path)

    # Step 2: Open video and run structured extraction
    from src.pipeline.extractor import extract_structured
    from src.utils.video import IOCacheVideo

    with IOCacheVideo(VIDEO_PATH, cached=True) as video:
        results = extract_structured(llm, video)

    # Step 3: Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for i, r in enumerate(results):
        if "error" in r:
            print(f"\n[{i}] ERROR: {r['error']}")
        else:
            print(f"\n[{i}] {r.get('time_range', r)}")
            print(f"    visual: {r.get('visual', 'N/A')}")
            print(f"    dialogue: {r.get('dialogue', 'N/A')}")
            print(f"    sound: {r.get('sound', 'N/A')}")

    print("\n" + "#" * 60)
    print("# TEST COMPLETE")
    print("#" * 60 + "\n")


def load_model(
    model_path: str = "google/gemma-4-12B-it-qat-w4a16-ct",
) -> LLM:
    """Load vLLM model with compressed-tensors quantization."""
    from src.pipeline.loader import load_model as _load

    return _load(model_path, limit_mm_per_prompt={"image": 32, "audio": 1})


if __name__ == "__main__":
    main()
