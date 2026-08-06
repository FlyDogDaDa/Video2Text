"""Video2Text — structured video understanding powered by vLLM."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import cv2
import torch
from dotenv import load_dotenv
from PIL import Image
from transformers import AutoProcessor
from vllm import LLM, SamplingParams

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")


GPU_0 = os.getenv("CUDA_VISIBLE_DEVICES", "0").split(",")[0]


def test_gpu():
    """Test GPU availability and configuration."""
    print("=" * 60)
    print("GPU TEST")
    print("=" * 60)
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA device count: {torch.cuda.device_count()}")

    for i in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(i)
        print(f"\nGPU {i}: {props.name}")
        print(f"  Total memory: {props.total_memory / 1024**3:.1f} GB")
        print(f"  Compute capability: {props.major}.{props.minor}")
    print()


def load_model(
    model_path: str = "google/gemma-4-12B-it-qat-w4a16-ct",
    limit_mm_per_prompt: dict | None = None,
):
    """Load vLLM model with compressed-tensors quantization."""
    print("=" * 60)
    print(f"LOADING MODEL: {model_path}")
    print("=" * 60)

    # Check VRAM before loading
    for i in range(torch.cuda.device_count()):
        mem_free = torch.cuda.mem_get_info(i)[0] / 1024**3
        mem_total = torch.cuda.get_device_properties(i).total_memory / 1024**3
        print(f"GPU {i} - Free: {mem_free:.1f}GB / Total: {mem_total:.1f}GB")

    num_gpus = torch.cuda.device_count()
    tp_size = min(num_gpus, 2)  # Use both GPUs if available

    print(
        f"\nUsing tensor_parallel_size={tp_size} (GPU count: {num_gpus}, total VRAM: {sum(torch.cuda.get_device_properties(i).total_memory for i in range(num_gpus)) / 1024**3:.1f}GB)"
    )

    # Multimodal config
    if limit_mm_per_prompt is None:
        # Default: 32 images + 1 audio per prompt
        limit_mm_per_prompt = {"image": 32, "audio": 1}

    llm = LLM(
        model=model_path,
        quantization="compressed-tensors",
        tensor_parallel_size=tp_size,  # Use 2 GPUs
        max_model_len=16384,  # Enough for 29 images (29 * 280 = 8120) + prompt + audio
        trust_remote_code=True,
        gpu_memory_utilization=0.8,  # Very low — only 3GB free on GPU 0
        enforce_eager=True,  # Disable torch.compile — Gemma 4 has dynamic shape issues
        # Multimodal token budget
        limit_mm_per_prompt=limit_mm_per_prompt,
        mm_processor_kwargs={"max_soft_tokens": 280},
        # Patch num_soft_tokens to fix vLLM nightly bug (dev296)
        hf_overrides={
            "vision_config": {"num_soft_tokens": 1120},
        },
    )

    print("\n✓ Model loaded successfully!")
    return llm


def test_text_generation(llm: LLM):
    """Test basic text generation."""
    print("\n" + "=" * 60)
    print("TEXT GENERATION TEST")
    print("=" * 60)

    prompts = ["Describe a sunset over the ocean."]

    sampling_params = SamplingParams(
        temperature=0.7,
        max_tokens=256,
    )

    outputs = llm.generate(prompts, sampling_params)

    print(f"\nPrompt: {prompts[0]}")
    print(f"Response: {outputs[0].outputs[0].text}")


def extract_frames(video_path: str, output_dir: Path, fps: float = 1.0):
    """Extract frames from video at specified FPS."""
    print("\n" + "=" * 60)
    print(f"EXTRACTING FRAMES from {video_path}")
    print("=" * 60)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / total_fps

    print(f"Video: {total_frames} frames, {duration:.1f}s, {total_fps}FPS")
    print(f"Extracting at {fps}FPS → ~{duration * fps} frames")

    output_dir.mkdir(parents=True, exist_ok=True)

    frame_interval = int(total_fps / fps)
    frame_count = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frame_path = output_dir / f"frame_{saved_count:04d}.jpg"
            Image.fromarray(frame).save(frame_path)
            saved_count += 1
            print(f"  Saved frame {saved_count} ({frame_path.name})")

        frame_count += 1

    cap.release()
    print(f"\n✓ Extracted {saved_count} frames to {output_dir}")
    return saved_count


def swarm_extract(video_path: str, *, cached: bool = True) -> list[dict]:
    """Swarm-style video extraction — splits video into sliding windows and extracts frames+audio.

    Returns a list of dicts, one per slice, each containing:
    - time_range: (start, end) in seconds
    - frames: numpy array [N, H, W, 3] uint8 RGB
    - audio_clips: list of 16kHz mono numpy arrays (each ≤30s)
    - info: VideoInfo metadata
    """
    import numpy as np

    from src.utils.slice import IOCacheVideo, SliceParams

    params = SliceParams(window_seconds=30.0, overlap_seconds=2.0, sample_fps=1.0)
    step = params.step_seconds

    with IOCacheVideo(video_path, cached=cached) as video:
        info = video.info
        duration = info.duration

        print(f"📹 {info.path}")
        print(
            f"   Duration: {duration:.1f}s | {info.fps:.1f}fps | {info.width}×{info.height}"
        )
        print(
            f"   Window: {params.window_seconds}s | Overlap: {params.overlap_seconds}s | Step: {step:.1f}s"
        )
        print(
            f"   Max frames/slice: {params.max_frames} | Sample FPS: {params.sample_fps}"
        )

        slices: list[dict] = []
        slice_num = 0

        # Generate windows with step, clamped to [0, duration]
        t = 0.0
        while t < duration:
            start = t
            end = min(t + params.window_seconds, duration)
            if start >= end:
                break

            print(f"  [{slice_num:3d}] [{start:6.1f}s – {end:6.1f}s] ", end="")

            frames = video.get_frames(
                start, end, sample_fps=params.sample_fps, max_frames=params.max_frames
            )
            audio_clips = video.get_audio(start, end, max_clip_duration=30.0)

            audio_secs = [len(c) / 16000 for c in audio_clips]
            print(
                f"frames={frames.shape[0]:3d}/{frames.shape[1]}x{frames.shape[2]} | "
                f"audio={len(audio_clips)}clip(s) [{', '.join(f'{s:.1f}s' for s in audio_secs)}]"
            )

            slices.append(
                {
                    "time_range": (float(start), float(end)),
                    "frames": frames,
                    "audio_clips": audio_clips,
                    "info": info,
                }
            )

            t += step
            slice_num += 1

        print(f"\n✅ {len(slices)} slices extracted")
        return slices


def test_multimodal(llm: LLM, video_path: str = "2026_05_11-19_18_26.mkv"):
    """Test video frame analysis."""
    print("\n" + "=" * 60)
    print("MULTIMODAL TEST (Image + Text)")
    print("=" * 60)

    # Extract a few frames for testing
    output_dir = Path("test_frames")
    num_frames = extract_frames(video_path, output_dir, fps=1.0)

    # Test with first frame
    frame_path = output_dir / "frame_0000.jpg"
    if frame_path.exists():
        # Note: vLLM doesn't directly support images, need to use processor
        print(f"\nAnalyzing frame: {frame_path}")

        # Create prompt
        prompt = "Describe what you see in this image."

        sampling_params = SamplingParams(
            temperature=0.7,
            max_tokens=256,
        )

        # vLLM text-only test (no image support in this version)
        outputs = llm.generate([prompt], sampling_params)

        print(f"\nPrompt: {prompt}")
        print(f"Response: {outputs[0].outputs[0].text}")

    print("\n⚠ Note: Image processing requires transformers processor")
    print("  vLLM serve API supports multimodal via HTTP")


def _build_slice_prompt(start: float, end: float) -> str:
    """Build a JSON structure prompt for vLLM."""
    import json

    template = {
        "description": {"visual": "", "audio": ""},
        "transcription": {"audio": [{"text": "", "speaker": ""}], "visual": ""},
        "time_range": {"start": start, "end": end},
    }
    return (
        f"Analyze this {int(end - start)}-second video slice [{start:.0f}s – {end:.0f}s]. "
        f"Return ONLY valid JSON with this structure:\n\n"
        f"{json.dumps(template, indent=2)}\n\n"
        f"Fill in the values based on the video content."
    )


def extract_structured(llm: LLM, video_path: str, *, cached: bool = True) -> list[dict]:
    """Swarm extract structured content via vLLM — one full run.

    For each video slice:
    1. Extract frames + audio (swarm slicing)
    2. Send to vLLM for structured extraction
    3. Return list of SliceResult dicts
    """
    import json
    from pathlib import Path

    from PIL import Image
    from transformers import AutoProcessor

    from src.utils.slice import IOCacheVideo, SliceParams

    # Build prompt template
    prompt_template = _build_slice_prompt(0, 30)  # placeholder values

    # Load processor for chat template
    model_path = "google/gemma-4-12B-it-qat-w4a16-ct"
    processor = AutoProcessor.from_pretrained(model_path)

    params = SliceParams(window_seconds=30.0, overlap_seconds=2.0, sample_fps=1.0)
    step = params.step_seconds

    sampling_params = SamplingParams(
        temperature=0.1,
        max_tokens=512,
        seed=42,
    )

    with IOCacheVideo(video_path, cached=cached) as video:
        info = video.info
        duration = info.duration

        print(f"\n🤖 Structured extraction via vLLM")
        print(
            f"   Video: {info.path} | {duration:.1f}s | {info.fps:.1f}fps | {info.width}×{info.height}"
        )
        print(
            f"   Strategy: {params.window_seconds}s window, {step:.1f}s step, {params.max_frames} frames/slice"
        )

        results: list[dict] = []
        slice_num = 0
        t = 0.0

        while t < duration:
            start = t
            end = min(t + params.window_seconds, duration)
            if start >= end:
                break

            # Extract media for this slice
            frames = video.get_frames(
                start, end, sample_fps=params.sample_fps, max_frames=params.max_frames
            )
            audio_clips = video.get_audio(start, end, max_clip_duration=30.0)

            n_frames = frames.shape[0]
            print(
                f"\n  [{slice_num:3d}] [{start:6.1f}s – {end:6.1f}s] {n_frames} frames, {len(audio_clips)} audio clips",
                end="",
            )

            try:
                # Build messages with prompt and images
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_template},
                            *[{"type": "image"} for _ in range(n_frames)],
                        ],
                    }
                ]

                # Apply chat template
                prompt = processor.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )

                # Prepare multi_modal_data
                multi_modal_data = {}
                if n_frames > 0:
                    multi_modal_data["image"] = [Image.fromarray(f) for f in frames]
                if audio_clips:
                    multi_modal_data["audio"] = [audio_clips[0]]

                # vLLM v1 API: use dict format with "prompt" key
                inputs = {
                    "prompt": prompt,
                    "multi_modal_data": multi_modal_data if multi_modal_data else None,
                }

                outputs = llm.generate(inputs, sampling_params=sampling_params)

                response = outputs[0].outputs[0].text.strip()
                print(f" → {response[:80]}...")

                # Parse JSON result
                try:
                    # Extract JSON from response (handle markdown code blocks)
                    json_text = response
                    if "```json" in response:
                        json_text = response.split("```json")[1].split("```")[0]
                    elif "```" in response:
                        json_text = response.split("```")[1].split("```")[0]

                    result = json.loads(json_text)
                    results.append(result)
                    print(f"   ✅ Extracted")
                except json.JSONDecodeError as e:
                    print(f"\n   ⚠ JSON parse error: {e}")
                    print(f"   Raw response: {response[:200]}")
                    results.append({"raw_response": response})

            except Exception as e:
                print(f"\n   ⚠ vLLM error: {e}")
                results.append({"error": str(e), "time_range": (start, end)})

            t += step
            slice_num += 1

        print(f"\n✅ {len(results)} structured results extracted")
        return results


def main():
    """Run video2text console test."""
    model_path = os.getenv("VLLM_MODEL", "google/gemma-4-12B-it-qat-w4a16-ct")
    video_path = "2026_05_11-19_18_26.mkv"

    print("\n" + "#" * 60)
    print("# VIDEO2TEXT CONSOLE TEST")
    print("#" * 60 + "\n")

    # Test 1: GPU
    test_gpu()

    # Test 2: Load model
    llm = load_model(model_path)

    # Test 3: Text generation
    test_text_generation(llm)

    # Test 4: Multimodal
    if Path(video_path).exists():
        test_multimodal(llm, video_path)
    else:
        print(f"\n⚠ Video file not found: {video_path}")

    print("\n" + "#" * 60)
    print("# TEST COMPLETE")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    main()
