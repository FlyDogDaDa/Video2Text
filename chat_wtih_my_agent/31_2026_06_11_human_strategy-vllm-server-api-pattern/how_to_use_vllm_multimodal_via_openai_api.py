"""Demonstration: vLLM multimodal via OpenAI-compatible API.

This script shows how to call a vLLM server running Gemma-4 with
the OpenAI SDK (`openai` package).  Tasks 1-3 cover text, image, and
audio.  Task 4 has **three variants** to explore Gemma-4's reasoning
pipeline:

| Variant | Name | Strategy |
|---------|------|----------|
| 4a | ``task_reasoning_only()`` | Enable thinking + stop at ``<channel|>`` to see raw chain-of-thought |
| 4b | ``task_structured_output()`` | No thinking, only ``response_format`` guided JSON decoding |
| 4c | ``task_double_call_reason_then_structured()`` | Call 1: reason (stop at ``<channel|>``), Call 2: structured output with reasoning injected |

Tasks 1-3 + 4a-4c all run concurrently via ``asyncio.gather``.  The vLLM server handles scheduling.

Prerequisites
-------------
1. vLLM server running on ``localhost:8746``:

   .. code-block:: bash

      vllm serve google/gemma-4-12B-it-qat-w4a16-ct \\
        --reasoning-parser gemma4 \\
        --tool-call-parser gemma4 \\
        --enable-auto-tool-choice \\
        --attention-backend TRITON_ATTN \\
        --structured-outputs-config.enable_in_reasoning=True \\
        --enforce-eager

2. Test media extracted from ``short_test.mp4``:

   .. code-block:: bash

      runtime/ffmpeg -ss 5  -t 1 -i short_test.mp4 -update 1 -q:v 2 \
        references/test_image_1.jpg
      runtime/ffmpeg -ss 25 -t 1 -i short_test.mp4 -update 1 -q:v 2 \
        references/test_image_2.jpg
      runtime/ffmpeg -ss 45 -t 1 -i short_test.mp4 -update 1 -q:v 2 \
        references/test_image_3.jpg
      runtime/ffmpeg -ss 5 -t 30 -i short_test.mp4 -vn -ac 1 -ar 16000 -y \
        references/test_audio.wav

Usage
-----
::

    uv run python how_to_use_vllm_multimodal_via_openai_api.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import List

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# ==================================================================
# Official Gemma-4 recommended generation parameters (vLLM Recipes)
# ==================================================================
#
# From https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html
# ┌───────────────────┬──────────────────────────────────────────┐
# │ Parameter         │ Recommended value                        │
# ├───────────────────┼──────────────────────────────────────────┤
# │ temperature       │ 0.7  (creative) / 0.1 (deterministic)    │
# │ top_p             │ 0.95                                     │
# │ top_k             │ 64                                       │
# │ max_tokens        │ 512 (default) / 1024 (detailed)          │
# │ seed              │ 42 (reproducibility)                     │
# └───────────────────┴──────────────────────────────────────────┘
#
# Server-level flags (launch time):
#   --mm-processor-kwargs '{"max_soft_tokens": 280}'
#     Vision token budget per image: 70/140/280(default)/560/1120
#   --reasoning-parser gemma4
#     Automatic <|think>...<|end|> separation into reasoning + content
#   --tool-call-parser gemma4
#     Dedicated tool-call special tokens
#   --structured-outputs-config.enable_in_reasoning=True
#     ⚠️ Required to combine thinking + structured output in one request
#
# Thinking mode (per-request):
#   extra_body={"chat_template_kwargs": {"enable_thinking": True}}
#   → server separates reasoning (message.reasoning) from content
#
# Structured output (per-request):
#   response_format={"type": "json_schema", "json_schema": {...}}
#   → server guides decoding to produce valid JSON matching schema
#
# Per-request image resolution override:
#   mm_processor_kwargs={"max_soft_tokens": 1120}
# ==================================================================

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).parent / "references"

BASE_URL = "http://localhost:8746/v1"
MODEL_NAME = "google/gemma-4-12B-it-qat-w4a16-ct"

# Default sampling params aligned with vendor recommendations
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 64
DEFAULT_MAX_TOKENS = 512
DEFAULT_SEED = 42


# ------------------------------------------------------------------
# Pydantic models (define the JSON schema for Task 4)
# ------------------------------------------------------------------


class RelationTriple(BaseModel):
    """A single relation triplet extracted from a story."""

    subject: str = Field(..., description="The person or entity doing the action")
    predicate: str = Field(
        ...,
        description="Relationship type, e.g. is_parent_of, is_spouse_of, works_at, fears",
    )
    object: str = Field(..., description="The person or entity being acted upon")


class StoryAnalysis(BaseModel):
    """Structured output for the knowledge-graph extraction task."""

    triples: List[RelationTriple] = Field(
        ...,
        description="List of extracted relation triplets",
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _b64(path: Path) -> str:
    """Read *path* and return a ``data:...;base64,...`` URI."""
    raw = path.read_bytes()
    mime = "image/jpeg" if path.suffix == ".jpg" else "audio/wav"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _make_client() -> AsyncOpenAI:
    """Return an AsyncOpenAI client connected to our vLLM server."""
    return AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")


# ------------------------------------------------------------------
# Task 1 — Pure text
# ------------------------------------------------------------------


async def task_text() -> None:
    """Send a text-only prompt and print the reply."""
    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": "Describe a sunset over the ocean in one sentence.",
            },
        ],
        max_tokens=128,
        temperature=DEFAULT_TEMPERATURE,
    )

    reply = r.choices[0].message.content
    print("=" * 60)
    print("Task 1: Pure Text")
    print("=" * 60)
    print(f"📝 Prompt : Describe a sunset over the ocean in one sentence.")
    print(f"🤖 Reply  : {reply}")
    print()


# ------------------------------------------------------------------
# Task 2 — Image(s)
# ------------------------------------------------------------------


async def task_image() -> None:
    """Send text + 3 image base64 URIs and print the reply."""
    img_paths = [
        REFERENCE_DIR / "test_image_1.jpg",
        REFERENCE_DIR / "test_image_2.jpg",
        REFERENCE_DIR / "test_image_3.jpg",
    ]

    for p in img_paths:
        if not p.exists():
            print(f"⚠ Image not found: {p}", file=sys.stderr)
            return

    messages = [
        {
            "role": "system",
            "content": "You are a video analyst. Describe what you see in the images.",
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "What happens in these three frames from a video?",
                },
                *[
                    {"type": "image_url", "image_url": {"url": _b64(p)}}
                    for p in img_paths
                ],
            ],
        },
    ]

    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=256,
        temperature=DEFAULT_TEMPERATURE,
    )

    reply = r.choices[0].message.content
    print("=" * 60)
    print("Task 2: Multi-Image")
    print("=" * 60)
    print(f"📝 Prompt : What happens in these three frames?")
    print(f"🖼 Images : {len(img_paths)}")
    print(f"🤖 Reply  : {reply}")
    print()


# ------------------------------------------------------------------
# Task 3 — Audio
# ------------------------------------------------------------------


async def task_audio() -> None:
    """Send text + 1 audio base64 URI and print the reply."""
    wav_path = REFERENCE_DIR / "test_audio.wav"

    if not wav_path.exists():
        print(f"⚠ Audio not found: {wav_path}", file=sys.stderr)
        return

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Transcribe the speech in this audio exactly.",
                },
                {"type": "audio_url", "audio_url": {"url": _b64(wav_path)}},
            ],
        },
    ]

    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=256,
        temperature=0.1,
    )

    reply = r.choices[0].message.content
    print("=" * 60)
    print("Task 3: Audio")
    print("=" * 60)
    print(f"📝 Prompt : Transcribe the speech exactly.")
    print(f"🎵 Audio  : {wav_path.name}")
    print(f"🤖 Reply  : {reply}")
    print()


# ------------------------------------------------------------------
# Task 4 — Reasoning + Structured Output (Triples) — 3 variants
# ------------------------------------------------------------------

_SYSTEM_PROMPT_TRIPLES = """\
You are a knowledge-graph extractor. Read the short story, think step
by step about the relationships between characters, and then output a
JSON list of relation triplets following the provided schema."""

# Gemma-4 special token that ends the reasoning/thinking channel.
# See: https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4
_STOP_REASONING = ["<channel|>"]


# ------------------------------------------------------------------
# Task 4a — Reasoning Only (stop at <channel|>)
# ------------------------------------------------------------------


async def task_reasoning_only() -> None:
    """Reasoning-only task.

    Sends a prompt with thinking enabled, but stops generation right at
    ``<channel|>`` so we only see the model's chain-of-thought,
    not the final JSON answer.
    """
    story = (
        "Alice runs a bakery in downtown Portland and is married to Bob, "
        "who works as a software engineer at a startup. "
        "Charlie is Alice's brother and also lives in Portland; "
        "he fears public speaking but is secretly a talented poet. "
        "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
        "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TRIPLES},
        {
            "role": "user",
            "content": f"Read this story and extract all relationships:\n\n{story}",
        },
    ]

    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=2048,
        temperature=0.7,
        seed=42,
        stop=_STOP_REASONING,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    m1 = r.choices[0].message
    # The vLLM reasoning parser separates <channel|> content
    # into message.reasoning; message.content is empty after stop.
    reasoning = getattr(m1, "reasoning", None) or m1.content or ""
    print("=" * 60)
    print("Task 4a: Reasoning Only (stop at <channel|>)")
    print("=" * 60)
    print(f"📖 Story : {story[:80]}...")
    if reasoning:
        print(f"💭 Reasoning:\n{reasoning}")
    else:
        print("⚠ No reasoning content received")
    print()


# ------------------------------------------------------------------
# Task 4b — Pure Structured Output (no thinking)
# ------------------------------------------------------------------


async def task_structured_output() -> None:
    """Pure structured output — no thinking enabled.

    Relies only on ``response_format`` (guided decoding) to produce
    valid JSON without any intermediate reasoning tokens.
    """
    story = (
        "Alice runs a bakery in downtown Portland and is married to Bob, "
        "who works as a software engineer at a startup. "
        "Charlie is Alice's brother and also lives in Portland; "
        "he fears public speaking but is secretly a talented poet. "
        "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
        "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TRIPLES},
        {
            "role": "user",
            "content": f"Read this story and extract all relationships:\n\n{story}",
        },
    ]

    client = _make_client()

    json_schema = StoryAnalysis.model_json_schema()
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "story_analysis",
            "schema": json_schema,
        },
    }

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
        seed=42,
        response_format=response_format,
    )

    content = r.choices[0].message.content
    print("=" * 60)
    print("Task 4b: Structured Output Only (no thinking)")
    print("=" * 60)
    print(f"📖 Story : {story[:80]}...")

    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[-1].strip()

    try:
        parsed = StoryAnalysis.model_validate_json(cleaned)
        print(
            f"🤖 JSON:\n{json.dumps(parsed.model_dump(mode='json'), indent=2, ensure_ascii=False)}"
        )
        print(f"📊 Extracted : {len(parsed.triples)} triplets")
    except Exception as e:
        print(f"⚠ Could not parse: {e}")
        print(f"⚠ Raw sample: {cleaned[:300]}")
    print()


# ------------------------------------------------------------------
# Task 4c — Double Call: Reason → then Structured Output
# ------------------------------------------------------------------


async def task_double_call_reason_then_structured() -> None:
    """Two-call pattern for Gemma-4 reasoning + structured output.

    Call 1 — Reasoning only:
        Thinking is enabled; ``stop=["<channel|>"]`` stops generation
        right after the model finishes its chain-of-thought.

    Call 2 — Structured output:
        The reasoning from Call 1 is injected as an assistant message
        so the model only needs to produce JSON (guided decoding via
        ``response_format``).
    """
    story = (
        "Alice runs a bakery in downtown Portland and is married to Bob, "
        "who works as a software engineer at a startup. "
        "Charlie is Alice's brother and also lives in Portland; "
        "he fears public speaking but is secretly a talented poet. "
        "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
        "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
    )

    base_messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TRIPLES},
        {
            "role": "user",
            "content": f"Read this story and extract all relationships:\n\n{story}",
        },
    ]

    client = _make_client()

    # ── Call 1: reasoning only, stop at <channel|> ───────────────
    r1 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=base_messages,
        max_tokens=2048,
        temperature=0.7,
        seed=42,
        stop=_STOP_REASONING,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    m1 = r1.choices[0].message
    reasoning = getattr(m1, "reasoning", None) or m1.content or ""

    print("=" * 60)
    print("Task 4c: Double Call — Reason → Structured Output")
    print("=" * 60)
    print(f"📖 Story : {story[:80]}...")
    print(f"\n📞 Call 1 (reasoning, stop at <channel|>):")
    print(f"💭 Reasoning:\n{reasoning}")

    # ── Call 2: structured output, reasoning as context ──────────
    json_schema = StoryAnalysis.model_json_schema()
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "story_analysis",
            "schema": json_schema,
        },
    }

    # Inject reasoning into the context so the model doesn't need to
    # think again — it just outputs JSON.
    messages_with_reasoning = base_messages[:2] + [
        {"role": "assistant", "content": reasoning},
    ]

    r2 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages_with_reasoning,
        max_tokens=1024,
        temperature=0.7,
        seed=42,
        response_format=response_format,
    )

    content = r2.choices[0].message.content
    print(f"\n📞 Call 2 (structured output, no thinking):")

    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[-1].strip()

    try:
        parsed = StoryAnalysis.model_validate_json(cleaned)
        print(
            f"🤖 JSON:\n{json.dumps(parsed.model_dump(mode='json'), indent=2, ensure_ascii=False)}"
        )
        print(f"📊 Extracted : {len(parsed.triples)} triplets")
    except Exception as e:
        print(f"⚠ Could not parse: {e}")
        print(f"⚠ Raw sample: {cleaned[:300]}")
    print()


# ------------------------------------------------------------------
# main — run all four tasks in parallel with asyncio.gather
# ------------------------------------------------------------------


async def main() -> None:
    print("\n" + "#" * 60)
    print("# vLLM Multimodal Demo — OpenAI API")
    print(f"# Server : {BASE_URL}")
    print("#" * 60 + "\n")

    # Run all tasks concurrently — vLLM server handles scheduling
    await asyncio.gather(
        task_text(),
        task_image(),
        task_audio(),
        task_reasoning_only(),  # Task 4a: reasoning only
        task_structured_output(),  # Task 4b: structured output only
        task_double_call_reason_then_structured(),  # Task 4c: double-call
    )

    print("#" * 60)
    print("# ALL TASKS COMPLETE")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
