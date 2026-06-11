"""Structured extraction with delayed guided decoding + reasoning.

For each video slice this module:
1. Builds a chat prompt with images + audio via ``AutoProcessor``.
2. Sends the prompt to vLLM with ``StructuredOutputsParams`` (Gemma-4
   delayed guided decoding) and ``reasoning_parser="gemma4"``.
3. Parses the raw output with ``parse_thinking_output()`` to separate
   reasoning steps from the final JSON.
4. Validates the JSON against ``SliceResult`` schema.

Usage
-----
    from vllm import LLM
    from src.pipeline.extractor import extract_structured
    from src.utils.slice import IOCacheVideo, SliceParams

    llm = LLM("google/gemma-4-12B-it-qat-w4a16-ct", reasoning_parser="gemma4")
    with IOCacheVideo("video.mkv") as video:
        results = extract_structured(llm, video, SliceParams())
"""

from __future__ import annotations

import logging

from PIL import Image
from transformers import AutoProcessor
from vllm import LLM, SamplingParams
from vllm.reasoning.gemma4_utils import parse_thinking_output
from vllm.sampling_params import StructuredOutputsParams

from src.pipeline.slicer import slice_video
from src.types import SliceResult
from src.utils.video import IOCacheVideo, SliceParams

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a video analyst. For the given video window slice, produce a structured description.

Output ONLY the JSON object. The JSON must have these fields:
- start_at: float, start timestamp in seconds
- end_at: float, end timestamp in seconds
- visual: string (optional) — what happens visually (actions, scenes, text on screen)
- dialogue: string (optional) — spoken dialogue, use [Speaker]: format when speaker is identifiable
- sound: string (optional) — music, SFX, ambient sounds

Missing fields may be null. All other fields are optional."""


def extract_structured(
    llm: LLM,
    video: IOCacheVideo,
    *,
    params: SliceParams | None = None,
    sampling_params: SamplingParams | None = None,
) -> list[dict]:
    """Extract structured ``SliceResult`` for every slice of a video.

    Uses vLLM **delayed guided decoding** (``StructuredOutputsParams``)
    together with **Gemma-4 reasoning** (``parse_thinking_output``)
    to obtain valid JSON that matches the ``SliceResult`` schema.

    Parameters
    ----------
    llm:
        vLLM ``LLM`` instance with ``reasoning_parser="gemma4"``
        already configured.
    video:
        An **open** ``IOCacheVideo`` instance (caller owns the lifecycle).
        The caller should use ``with IOCacheVideo(...) as video:`` and
        pass the context-managed object here.
    params:
        Slicing parameters from ``src.utils.slice.SliceParams``.
        Defaults to 30 s window, 2 s overlap.
    sampling_params:
        vLLM ``SamplingParams``.  If ``None``, a default with
        temperature=0.1, max_tokens=512, seed=42 is used.
        Pass a ``StructuredOutputsParams``-backed one if you need
        custom temperature / top_p etc.

    Returns
    -------
    A list of dicts, one per slice.  On success the dict is the
    ``SliceResult.model_dump(mode="json")``.  On failure the dict
    contains ``{"error": ..., "time_range": ...}``.
    """
    if params is None:
        params = SliceParams()

    if sampling_params is None:
        sampling_params = SamplingParams(
            temperature=0.1,
            max_tokens=512,
            seed=42,
        )

    # Ensure the sampling params carry the structured output spec.
    if sampling_params.structured_outputs is None:
        json_schema = SliceResult.model_json_schema()
        sampling_params.structured_outputs = StructuredOutputsParams(json=json_schema)

    processor = AutoProcessor.from_pretrained(llm.llm_engine.model_config.model)

    info = video.info
    duration = info.duration

    print(f"\n\U0001f916 Structured extraction via vLLM (delayed guided decoding)")
    print(
        f"   Video: {info.path} | {duration:.1f}s | "
        f"{info.fps:.1f}fps | {info.width}\u00d7{info.height}"
    )
    print(
        f"   Strategy: {params.window_seconds}s window, "
        f"{params.step_seconds:.1f}s step, "
        f"{params.max_frames} frames/slice"
    )

    results: list[dict] = []
    slice_num = 0

    for inp in slice_video(video, params):
        start, end = inp.time_range
        n_frames = inp.frames.shape[0]

        print(
            f"\n  [{slice_num:3d}] [{start:6.1f}s \u2013 {end:6.1f}s] "
            f"{n_frames} frames, {len(inp.audio_clips)} audio clips",
            end="",
        )

        try:
            # Build chat messages with images and text prompt
            slice_desc = (
                f"Video slice from {start:.1f}s to {end:.1f}s "
                f"({int(end - start)} second{'' if end - start == 1 else 's'}). "
            )
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": slice_desc},
                        *[{"type": "image"} for _ in range(n_frames)],
                    ],
                },
            ]

            # Apply chat template (enable thinking for Gemma-4)
            prompt = processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                chat_template_kwargs={"enable_thinking": True},
            )

            # Prepare multimodal data
            multi_modal_data = {}
            if n_frames > 0:
                multi_modal_data["image"] = [Image.fromarray(f) for f in inp.frames]
            if inp.audio_clips:
                multi_modal_data["audio"] = [inp.audio_clips[0]]

            # vLLM offline v1 API: {"prompt": ..., "multi_modal_data": ...}
            inputs = {
                "prompt": prompt,
                "multi_modal_data": multi_modal_data if multi_modal_data else None,
            }

            outputs = llm.generate(inputs, sampling_params=sampling_params)
            raw_text = outputs[0].outputs[0].text.strip()

            # Split reasoning → JSON using Gemma-4 utility
            parsed = parse_thinking_output(raw_text)

            # Validate against Pydantic model
            result = SliceResult.model_validate_json(parsed.text)
            result_dict = result.model_dump(mode="json", exclude_none=True)
            results.append(result_dict)
            print(
                f" \u2705 Extracted | "
                f"reasoning={len(parsed.reasoning) if parsed.reasoning else 0} chars"
            )

        except Exception as e:
            print(f"\n   \u26a0 vLLM error: {e}")
            results.append({"error": str(e), "time_range": (start, end)})

        slice_num += 1

    print(f"\n\u2705 {len(results)} structured results extracted")
    return results
