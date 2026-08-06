#!/usr/bin/env python3
"""
Test: vLLM two-stage thinking + guided decoding with Gemma-4 reasoning + structured output.

Two-stage approach:
  Stage 1 — freeform reasoning  (no structured-output mask, temperature=0.7)
  Stage 2 — guided JSON         (StructuredOutputsParams, temperature=0.0)

The thinking text from Stage 1 is fed back as assistant context so Stage 2
can generate JSON **based on** the model's reasoning.

Usage:
    uv run -- python test_vllm_delayed_guided_decoding.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from vllm import LLM, SamplingParams
from vllm.reasoning.gemma4_utils import parse_thinking_output
from vllm.sampling_params import StructuredOutputsParams

from src.types import SliceResult

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a video analyst. For the given video window slice, produce a structured description.

Output ONLY the JSON object. The JSON must have these fields:
- start_at: float, start timestamp in seconds
- end_at: float, end timestamp in seconds
- visual: string (optional) — what happens visually (actions, scenes, text on screen)
- dialogue: string (optional) — spoken dialogue, use [Speaker]: format when speaker is identifiable
- sound: string (optional) — music, SFX, ambient sounds

Missing fields may be null. All other fields are optional.
"""

USER_PROMPT = """\
Video slice from 0.0s to 30.0s.

Visual frames:
- 0.0s - 5.0s: Wide shot of a forest with sunlight filtering through trees
- 5.0s - 15.0s: A deer walks into the clearing, pauses to listen
- 15.0s - 25.0s: The deer grazes peacefully
- 25.0s - 30.0s: A distant wolf howl, the deer bolts off-screen

Audio:
- Gentle wind, birds chirping
- Soft footstep sounds
- At 27s, a wolf howl is heard in the distance

--- INSTRUCTIONS ---
Before producing JSON, reason step by step:
1. What is the sequence of events? Identify cause and effect.
2. Which audio events are spatially correlated with visual changes?
3. Summarize your reasoning in 3-5 sentences.
4. Then output the JSON below.
"""

THINKING_MAX_TOKENS = 512


def _run_stage1(llm: LLM, messages: list, thinking_max_tokens: int) -> str:
    """Stage 1 — freeform reasoning, no structured-output mask."""
    sp = SamplingParams(
        temperature=0.7,
        max_tokens=thinking_max_tokens,
        seed=42,
    )
    prompt = llm.get_tokenizer().apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        chat_template_kwargs={"enable_thinking": True},
    )
    outputs = llm.generate(prompt, sampling_params=sp)
    return outputs[0].outputs[0].text.strip()


def _run_stage2(
    llm: LLM,
    messages: list,
    thinking_text: str,
    structured_params: SamplingParams,
) -> str:
    """Stage 2 — guided JSON, using reasoning as additional context."""
    # Build a 4-turn conversation: system → user → assistant (thinking) → user (instruction)
    slice_desc = "Video slice from 0.0s to 30.0s."
    stage2_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": [{"type": "text", "text": slice_desc}]},
        {"role": "assistant", "content": thinking_text},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Based on the reasoning above, output ONLY the "
                        "JSON object matching the schema."
                    ),
                }
            ],
        },
    ]
    prompt = llm.get_tokenizer().apply_chat_template(
        stage2_messages,
        tokenize=False,
        add_generation_prompt=True,
        chat_template_kwargs={"enable_thinking": False},
    )
    outputs = llm.generate(prompt, sampling_params=structured_params)
    return outputs[0].outputs[0].text.strip()


def main() -> None:
    model_id = "google/gemma-4-12B-it-qat-w4a16-ct"

    print(f"[1/6] Loading model: {model_id} ...")
    llm = LLM(
        model=model_id,
        max_model_len=4096,
        tensor_parallel_size=2,
        trust_remote_code=True,
        quantization="compressed-tensors",
        reasoning_parser="gemma4",
        hf_overrides={"vision_config": {"num_soft_tokens": 1120}},
    )

    json_schema = SliceResult.model_json_schema()
    print(f"[2/6] JSON Schema ({len(json_schema)} bytes):")
    print(json.dumps(json_schema, indent=2, ensure_ascii=False)[:600])

    # Stage-2 sampling params: structured output, greedy decode
    structured_params = SamplingParams(
        temperature=0.0,
        max_tokens=2048,
        structured_outputs=StructuredOutputsParams(json=json_schema),
    )
    print("[3/6] SamplingParams configured for both stages")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]

    # ---- Stage 1: freeform reasoning ----
    print("[4/6] Stage 1 — generating freeform reasoning ...")
    thinking_text = _run_stage1(llm, messages, THINKING_MAX_TOKENS)
    print(f"  Thinking output ({len(thinking_text)} chars):")
    print(thinking_text[:1200])
    print("=" * 60)

    # ---- Stage 2: guided JSON using reasoning ----
    print("[5/6] Stage 2 — generating guided JSON ...")
    raw_text = _run_stage2(llm, messages, thinking_text, structured_params)
    print(f"  Raw output ({len(raw_text)} chars):")
    print(raw_text[:2000])
    print("=" * 60)

    # Parse reasoning from stage 1 output
    parsed = parse_thinking_output(thinking_text)
    if isinstance(parsed, dict):
        reasoning = parsed.get("reasoning", "") or "(none)"
    else:
        reasoning = parsed.reasoning if hasattr(parsed, "reasoning") else "(none)"
    print("STAGE-1 REASONING:")
    print(reasoning)
    print("=" * 60)

    # Validate the stage-2 JSON output against SliceResult
    try:
        result = SliceResult.model_validate_json(raw_text)
        print("STAGE-2 VALIDATION: ✅ SliceResult accepted by Pydantic")
        print(
            json.dumps(
                result.model_dump(mode="json", exclude_none=True),
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as e:
        print(f"STAGE-2 VALIDATION: ❌ Pydantic validation failed — {e}")
        print("Raw text could not be parsed:", raw_text[:500])


if __name__ == "__main__":
    main()
