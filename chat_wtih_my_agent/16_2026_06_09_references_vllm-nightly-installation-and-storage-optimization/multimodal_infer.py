#!/usr/bin/env python3
"""
Multimodal Offline Inference for Gemma-4-12B (Encoder-Free)

Official vLLM Gemma 4 Guide: https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html

Usage examples:

# Text only
python src/inference/multimodal_infer.py \
  --prompt "What is the meaning of life?"

# Text + Image (nightly vLLM fixes num_soft_tokens bug)
python src/inference/multimodal_infer.py \
  --prompt "Describe this image." \
  --image ./path/to/image.jpg

# Text + Image + Audio (12B encoder-free projects raw audio into LM space)
python src/inference/multimodal_infer.py \
  --prompt "Describe this image and transcribe the audio." \
  --image ./cat.jpg \
  --audio ./audio.wav

# Text + Video (requires custom vLLM branch - not available yet)
python src/inference/multimodal_infer.py \
  --prompt "Summarize this video." \
  --video ./video.mp4

# Mixed: Text + Image + Audio + Video
python src/inference/multimodal_infer.py \
  --prompt "Analyze these inputs." \
  --image ./img.jpg \
  --audio ./audio.wav \
  --video ./video.mp4

# Text + Multiple Images
python src/inference/multimodal_infer.py \
  --prompt "Compare these images." \
  --image ./img1.jpg \
  --image ./img2.jpg

Note: Gemma-4-12B is encoder-free multimodal (text, image, video, audio).
      Raw pixel patches and audio waveform frames are projected directly into LM space
      via the decoder-only transformer — no separate vision/audio encoders needed.
      Audio max: 30s. Video max: 60s (1fps). Vision tokens: 70/140/280(default)/560/1120.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image
from vllm import LLM, SamplingParams
from vllm.config import AttentionConfig
from vllm.multimodal.utils import fetch_video
from vllm.v1.attention.backends.registry import AttentionBackendEnum

# ============================================================
# Configuration
# ============================================================

MODEL_PATH = "google/gemma-4-12B-it-qat-w4a16-ct"
TP_SIZE = 2
MAX_MODEL_LEN = 4096  # Conservative for 2×12GB GPUs
QUANTIZATION = "compressed-tensors"

# ============================================================
# Input loading functions
# ============================================================


def load_image(image_path: str) -> Image.Image:
    """Load a local image file."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    return Image.open(path).convert("RGB")


def load_video(video_path: str):
    """Load video using vllm.multimodal.utils.fetch_video."""
    # fetch_video expects a file:// URL or HTTP URL
    if video_path.startswith("http"):
        video_url = video_path
    else:
        video_url = f"file://{Path(video_path).resolve()}"
    return fetch_video(video_url)


def build_messages(
    prompt: str,
    images: list[str] = None,
    audio_files: list[str] = None,
    videos: list[str] = None,
) -> list[dict]:
    """
    Build chat messages array for vLLM input.

    Format follows OpenAI multimodal content structure:
    [
      {"type": "text", "text": "..."},
      {"type": "image"},  # placeholder, vLLM fills in the image
      {"type": "video"},  # placeholder
      {"type": "text", "text": "..."},
    ]
    """
    content = []

    # Add text prompt
    if prompt:
        content.append({"type": "text", "text": prompt})

    # Add image placeholders
    for _ in images or []:
        content.append({"type": "image"})

    # Add audio placeholder
    for _ in audio_files or []:
        content.append({"type": "audio"})

    # Add video placeholder
    for _ in videos or []:
        content.append({"type": "video"})

    return [{"role": "user", "content": content}]


def build_multi_modal_data(
    images: list[str] = None,
    audio_files: list[str] = None,
    videos: list[str] = None,
) -> dict:
    """
    Build multi_modal_data dict for LLM.generate().

    Gemma-4-12B (encoder-free) supports:
    - Images: PIL Image objects
    - Audio: numpy arrays (raw 16kHz waveform frames projected into LM space)
    - Video: requires custom vLLM branch (not stable yet)

    Format:
    {
      "image": [...],    # list of PIL Image
      "audio": [...],    # list of numpy arrays
      "video": [...],    # list of video data
    }
    """
    multi_modal_data = {}

    if images:
        multi_modal_data["image"] = [load_image(p) for p in images]

    if audio_files:
        # Gemma-4-12B encoder-free: projects raw audio into LM space
        try:
            import numpy as np
            import soundfile as sf
            from vllm.multimodal.audio import AudioResampler, normalize_audio

            audio_data_list = []
            for audio_path in audio_files:
                # Load audio at 16kHz (required by Gemma 4)
                data, sr = sf.read(audio_path, samplerate=16000)
                if len(data.shape) > 1:  # Stereo to mono
                    data = data.mean(axis=1)
                # Normalize to [-1, 1]
                data = normalize_audio(data)
                audio_data_list.append(data)
            multi_modal_data["audio"] = audio_data_list
        except ImportError as e:
            print(f"WARNING: Audio requires extra packages: {e}", file=sys.stderr)
            print("Install with: pip install soundfile", file=sys.stderr)
        except Exception as e:
            print(f"Audio loading failed: {e}", file=sys.stderr)

    if videos:
        video_data_list = []
        for v in videos:
            video_data = load_video(v)
            video_data_list.append(video_data)
        multi_modal_data["video"] = video_data_list

    return multi_modal_data


# ============================================================
# Main inference
# ============================================================


def create_llm(
    multimodal_input_count: int = 0,
    use_images: bool = False,
    use_audio: bool = False,
    use_video: bool = False,
    gpu_memory_utilization: float = 0.7,
):
    """Create LLM instance with proper configuration.

    Official Gemma 4 fixes (vLLM nightly):
    - mm_processor_kwargs: controls vision token budget per request
    - limit_mm_per_prompt: controls VRAM allocation per modality
    - hf_overrides: patches num_soft_tokens to fix vLLM bug on nightly dev296

    Args:
        multimodal_input_count: Total number of multimodal inputs.
                                Set to 0 for text-only to save VRAM.
        use_images: Whether images are provided.
        use_audio: Whether audio is provided.
        use_video: Whether video is provided.
        gpu_memory_utilization: Fraction of GPU memory to use (default: 0.7).
                                Lower values leave more room for KV cache.
    """
    # Text-only: skip multimodal profiling entirely to save VRAM
    # With multimodal: enable appropriate modalities
    # Note: video support requires custom vLLM branch (not in stable yet)
    if multimodal_input_count == 0:
        limit_mm = {"image": 0, "audio": 0}
    else:
        limit_mm = {}
        if use_images:
            limit_mm["image"] = 4
        if use_audio:
            limit_mm["audio"] = 1
        # Video is disabled until custom vLLM branch is available

    llm_kwargs = {
        "model": MODEL_PATH,
        "quantization": QUANTIZATION,
        "tensor_parallel_size": TP_SIZE,
        "max_model_len": MAX_MODEL_LEN,
        "trust_remote_code": True,
        "enforce_eager": True,
        "gpu_memory_utilization": gpu_memory_utilization,
        "attention_config": AttentionConfig(backend=AttentionBackendEnum.TRITON_ATTN),
        # Official fixes for Gemma 4 (from vLLM recipe guide)
        "limit_mm_per_prompt": limit_mm,
        "mm_processor_kwargs": {"max_soft_tokens": 280},  # Default vision token budget
        # Patch num_soft_tokens to fix the vLLM bug on nightly dev296
        "hf_overrides": {
            "vision_config": {"num_soft_tokens": 1120},
        },
    }
    return LLM(**llm_kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="Multimodal offline inference for Gemma-4-12B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        required=True,
        help="Text prompt to send to the model",
    )
    parser.add_argument(
        "--image",
        "-i",
        type=str,
        nargs="+",
        default=[],
        help="Local image file(s) to include (can be specified multiple times)",
    )
    parser.add_argument(
        "--audio",
        "-a",
        type=str,
        nargs="+",
        default=[],
        help="Audio file(s) to include (max 30s, 16kHz WAV/FLAC) — 12B encoder-free supports audio",
    )
    parser.add_argument(
        "--video",
        "-v",
        type=str,
        nargs="+",
        default=[],
        help="Video file(s) to include (can be specified multiple times)",
    )
    parser.add_argument(
        "--max-tokens",
        "-m",
        type=int,
        default=512,
        help="Maximum output tokens (default: 512)",
    )
    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0 = greedy)",
    )
    parser.add_argument(
        "--tp-size",
        type=int,
        default=TP_SIZE,
        help=f"Tensor parallel size (default: {TP_SIZE})",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.prompt:
        print("ERROR: --prompt is required", file=sys.stderr)
        sys.exit(1)

    multimodal_count = len(args.image) + len(args.video) + len(args.audio)

    if multimodal_count == 0:
        print("NOTE: No multimodal inputs specified (text-only mode)", file=sys.stderr)
    else:
        print(f"Multimodal inputs: {multimodal_count} total", file=sys.stderr)
        if args.audio:
            print(
                f"  - {len(args.audio)} audio file(s) (12B encoder-free, raw waveform projected)",
                file=sys.stderr,
            )
        if args.image:
            print(f"  - {len(args.image)} image(s)", file=sys.stderr)
        if args.video:
            print(f"  - {len(args.video)} video(s)", file=sys.stderr)

    # Create LLM
    print(f"Loading model: {MODEL_PATH}", file=sys.stderr)
    llm = create_llm(
        multimodal_input_count=multimodal_count,
        use_images=len(args.image) > 0,
        use_audio=len(args.audio) > 0,
        use_video=len(args.video) > 0,
    )

    # Build messages and multi_modal_data
    messages = build_messages(
        prompt=args.prompt,
        images=args.image,
        audio_files=args.audio,
        videos=args.video,
    )
    multi_modal_data = build_multi_modal_data(
        images=args.image,
        audio_files=args.audio,
        videos=args.video,
    )

    # Apply chat template
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL_PATH)
    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )

    # Generate
    print("Running inference...", file=sys.stderr)
    sampling_params = SamplingParams(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    outputs = llm.generate(
        {
            "prompt": prompt,
            "multi_modal_data": multi_modal_data if multi_modal_data else None,
        },
        sampling_params=sampling_params,
    )

    # Print result
    result = outputs[0].outputs[0].text
    print("=" * 80)
    print("INPUT:")
    print(f"  Prompt: {args.prompt}")
    if args.image:
        print(f"  Images: {', '.join(args.image)}")
    if args.audio:
        print(f"  Audio: {', '.join(args.audio)}")
    if args.video:
        print(f"  Videos: {', '.join(args.video)}")
    print("=" * 80)
    print("OUTPUT:")
    print(result)
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
