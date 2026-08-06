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
