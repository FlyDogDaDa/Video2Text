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


def load_model(model_path: str = "google/gemma-4-12B-it-qat-w4a16-ct"):
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

    llm = LLM(
        model=model_path,
        quantization="compressed-tensors",
        tensor_parallel_size=tp_size,  # Use 2 GPUs
        max_model_len=2048,  # Conservative to save VRAM
        trust_remote_code=True,
        gpu_memory_utilization=0.8,  # Very low — only 3GB free on GPU 0
        enforce_eager=True,  # Disable torch.compile — Gemma 4 has dynamic shape issues
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
    from pathlib import Path

    import numpy as np

    from src.utils.slice import IOCacheVideo, SliceParams, VideoInfo

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
        t = 0.0
        slice_num = 0

        while t < duration:
            end = min(t + params.window_seconds, duration)
            # If last window, ensure it ends at exactly duration
            if end == duration and t > 0:
                # Adjust start so last window has proper size
                t = max(0.0, end - params.window_seconds)

            start = t
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

        print(f"\n✅ {len(slices)} slices extracted ({duration / step:.0f} steps)")
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
