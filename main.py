"""Video2Text console test — GPU check + text generation."""

from __future__ import annotations

import os
from pathlib import Path

import torch
from dotenv import load_dotenv
from vllm import SamplingParams

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


def test_text_generation(llm):
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


def main():
    """Run video2text console test."""
    model_path = os.getenv("VLLM_MODEL", "google/gemma-4-12B-it-qat-w4a16-ct")

    print("\n" + "#" * 60)
    print("# VIDEO2TEXT CONSOLE TEST")
    print("#" * 60 + "\n")

    # Test 1: GPU
    test_gpu()

    # Test 2: Load model
    from src.pipeline import load_model

    llm = load_model(model_path)

    # Test 3: Text generation
    test_text_generation(llm)

    print("\n" + "#" * 60)
    print("# TEST COMPLETE")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    main()
