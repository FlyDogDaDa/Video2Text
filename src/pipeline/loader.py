"""vLLM model loading with compressed-tensors quantization."""

from __future__ import annotations

import torch
from vllm import LLM


def load_model(
    model_path: str = "google/gemma-4-12B-it-qat-w4a16-ct",
    *,
    max_model_len: int = 16384,
    limit_mm_per_prompt: dict | None = None,
) -> LLM:
    """Load vLLM model with compressed-tensors quantization.

    Parameters
    ----------
    model_path:
        HuggingFace model ID or local path.
    max_model_len:
        Maximum sequence length. Default 16384 (enough for 32 images
        at 280 soft tokens each + prompt + audio).
    limit_mm_per_prompt:
        Multimodal token budget.  Defaults to ``{"image": 32, "audio": 1}``.

    Returns
    -------
    An initialised ``vllm.LLM`` instance ready for ``.generate()``.
    """
    print("=" * 60)
    print(f"LOADING MODEL: {model_path}")
    print("=" * 60)

    # Check VRAM before loading
    for i in range(torch.cuda.device_count()):
        mem_free = torch.cuda.mem_get_info(i)[0] / 1024**3
        mem_total = torch.cuda.get_device_properties(i).total_memory / 1024**3
        print(f"GPU {i} - Free: {mem_free:.1f}GB / Total: {mem_total:.1f}GB")

    num_gpus = torch.cuda.device_count()
    tp_size = min(num_gpus, 2)

    print(
        f"\nUsing tensor_parallel_size={tp_size} "
        f"(GPU count: {num_gpus}, total VRAM: "
        f"{sum(torch.cuda.get_device_properties(i).total_memory for i in range(num_gpus)) / 1024**3:.1f}GB)"
    )

    # Multimodal config
    if limit_mm_per_prompt is None:
        limit_mm_per_prompt = {"image": 32, "audio": 1}

    llm = LLM(
        model=model_path,
        quantization="compressed-tensors",
        tensor_parallel_size=tp_size,
        max_model_len=max_model_len,
        trust_remote_code=True,
        gpu_memory_utilization=0.8,
        enforce_eager=True,  # Disable torch.compile — Gemma 4 has dynamic shape issues
        limit_mm_per_prompt=limit_mm_per_prompt,
        mm_processor_kwargs={"max_soft_tokens": 280},
        # Patch num_soft_tokens to fix vLLM nightly bug (dev296)
        hf_overrides={
            "vision_config": {"num_soft_tokens": 1120},
        },
    )

    print("\n\u2713 Model loaded successfully!")
    return llm
