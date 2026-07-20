import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from openai import AsyncOpenAI

from src.types import SliceResult
from src.utils.video import IOCacheVideo, SliceParams

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Update these with your environment details
VLLM_BASE_URL = "http://localhost:65500/v1"
MODEL_NAME = "google/gemma-4-12b-it-qat-w4a16-ct"
API_KEY = "EMPTY"

client = AsyncOpenAI(base_url=VLLM_BASE_URL, api_key=API_KEY)


@dataclass
class TranscriptionTask:
    video_path: Path
    output_dir: Path
    slice_params: SliceParams

    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)


async def extract_transcription_phase(task: TranscriptionTask):
    """
    Phase 1: Extract transcriptions from all video slices and perform redundancy reduction.
    """
    logger.info(f"Starting Transcription Phase for: {task.video_path}")

    with IOCacheVideo(str(task.video_path), cached=True) as video:
        duration = video.duration
        # Calculate slice boundaries
        slices = []
        current_start = 0.0
        while current_start < duration - 1.0:
            current_end = min(
                current_start + task.slice_params.window_seconds, duration
            )
            slices.append((current_start, current_end))
            current_start += task.slice_params.step_seconds

        logger.info(f"Identified {len(slices)} slices for transcription.")

        # Parallel transcription
        semaphore = asyncio.Semaphore(16)

        async def fetch_slice_transcription(start, end):
            async with semaphore:
                logger.info(f"Requesting transcription for [{start:.2f}s, {end:.2f}s]")
                # Note: In a real production scenario, we'd pass the audio data.
                # Since the vLLM server handles video_url/base64, we pass the file path or content.
                # For this prototype, we assume the server can access the file path or we'd provide base64.
                # Given our previous strategy, let's use a placeholder for the actual content extraction.

                response = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Transcribe the dialogue from the video at {start}s to {end}s. Return only the transcribed text.",
                        }
                    ],
                    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
                    tool_choice="none",
                )
                return {"start": start, "end": end, "text": response.choices[0].content}

        # For the prototype, we simulate the chunking and transcription
        # and perform the 'Reduction of Redundancy' step.
        results = await asyncio.gather(
            *[fetch_slice_transcription(s[0], s[1]) for s in slices]
        )

        # Save intermediate jsonl
        jsonl_path = task.output_dir / "transcript_segments.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for res in results:
                f.write(json.dumps(res) + "\n")
        logger.info(f"Saved transcriptions to {jsonl_path}")

        # Reduction of Redundancy
        # 1. Collect all text
        all_text = "\n".join([r["text"] for r in results])

        # 2. Call LLM to reduce redundancy
        logger.info("Starting redundancy reduction...")
        reduction_response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": f"The following are raw transcriptions from a video. Please remove redundant information, filler words, and repetitive sections. Keep the core dialogue and facts intact. Wrap the final cleaned text in a code block.\n\n{all_text}",
                }
            ],
            extra_body={"chat_template_kwargs": {"enable_thinking": True}},
            tool_choice="none",
        )

        cleaned_text = reduction_response.choices[0].content
        # Strip code blocks if present
        if "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].replace("python", "").strip()

        # 3. Save clean_transcript.md
        md_path = task.output_dir / "clean_transcript.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
        logger.info(f"Saved cleaned transcript to {md_path}")


async def main():
    # Use the test media provided in the repo
    video_path = Path("short_test.mp4")
    if not video_path.exists():
        # Fallback to another available video
        video_path = Path("2026_05_11-19_18_26_louder4x.mp4")

    params = SliceParams(window_seconds=30.0, overlap_seconds=15.0, sample_fps=1.0)

    task = TranscriptionTask(
        video_path=video_path,
        output_dir=video_path.parent / f"output_{video_path.stem}",
        slice_params=params,
    )

    await extract_transcription_phase(task)

    await extract_transcription_phase(task)


if __name__ == "__main__":
    asyncio.run(main())
