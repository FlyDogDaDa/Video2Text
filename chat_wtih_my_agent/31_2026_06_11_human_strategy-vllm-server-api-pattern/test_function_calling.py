"""Quick test: Gemma-4 Thinking + Function Calling via vLLM OpenAI API.

Goal
----
Verify whether Gemma-4 on vLLM supports **thinking mode + function calling**
natively — the hypothesised "positive path" for structured extraction
(#33, #34).

Design
------
| Test |  What |  Expectation |
|------|-------|--------------|
| F1 | function-calling only (no thinking) | model returns tool_call |
| F2 | thinking only (no function-calling) | model returns reasoning |
| F3 | **thinking + function-calling** | model returns reasoning + tool_call |

Server launch (must be running before this script):

.. code-block:: bash

   vllm serve google/gemma-4-12B-it-qat-w4a16-ct \\
     --reasoning-parser gemma4 \\
     --tool-call-parser gemma4 \\
     --enable-auto-tool-choice \\
     --attention-backend TRITON_ATTN \\
     --structured-outputs-config.enable_in_reasoning=True \\
     --enforce-eager
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).parent / "references"

BASE_URL = "http://localhost:8746/v1"
MODEL_NAME = "google/gemma-4-12B-it-qat-w4a16-ct"

# Gemma-4 stop token for reasoning channel
_STOP_REASONING = ["<channel|>"]

# ------------------------------------------------------------------
# Tool definition — relation extraction (same story as Tasks 4a-4c)
# ------------------------------------------------------------------

_EXTRACT_RELATIONSHIP_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_relationships",
        "description": (
            "Extract all relationships from the provided story text. "
            "Return every relationship you find as a structured list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {
                                "type": "string",
                                "description": "Person or entity",
                            },
                            "predicate": {
                                "type": "string",
                                "description": (
                                    "Relationship type, e.g. is_spouse_of, "
                                    "works_at, fears, is_sibling_of"
                                ),
                            },
                            "object": {
                                "type": "string",
                                "description": "Target person or entity",
                            },
                        },
                        "required": ["subject", "predicate", "object"],
                    },
                    "description": "List of relationship triplets",
                },
            },
            "required": ["stories"],
        },
    },
}

# ------------------------------------------------------------------
# Shared data — avoid re-creating per-task
# ------------------------------------------------------------------

STORY = (
    "Alice runs a bakery in downtown Portland and is married to Bob, "
    "who works as a software engineer at a startup. "
    "Charlie is Alice's brother and also lives in Portland; "
    "he fears public speaking but is secretly a talented poet. "
    "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
    "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
)

# Single shared prompt — all tasks use this identical list.
# Only the API parameters (tools, thinking, stop) differ.
_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are a knowledge-graph extractor. "
            "Read the story and extract all relationships between characters. "
            "Think step by step, then call extract_relationships to return "
            "your findings as structured data."
        ),
    },
    {"role": "user", "content": f"Extract all relationships:\n\n{STORY}"},
]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")


def _get_reasoning(message: Any) -> str:
    """Extract reasoning, falling back to content."""
    return getattr(message, "reasoning", None) or message.content or ""


def _get_tool_calls(message: Any):
    """Extract tool_calls, handling vLLM/OpenAI attribute quirks."""
    tc = getattr(message, "tool_calls", None)
    if tc is None:
        tc = message.tool_calls if hasattr(message, "tool_calls") else None
    return tc


def _format_tool_calls(tool_calls):
    """Format tool_calls list for display."""
    results = []
    for tc in tool_calls:
        name = tc.function.name if hasattr(tc, "function") else "?"
        args_text = tc.function.arguments if hasattr(tc, "function") else "{}"
        try:
            args = json.loads(args_text)
            results.append(
                {"name": name, "args": args, "raw": args_text, "error": None}
            )
        except json.JSONDecodeError:
            results.append(
                {"name": name, "args": None, "raw": args_text, "error": "invalid JSON"}
            )
    return results


def _print_result(label: str, *, story_prefix: str, data: dict) -> None:
    """Pretty-print a single test result."""
    print("=" * 60)
    print(f"{label}")
    print("=" * 60)
    print(f"📖 Story : {story_prefix}")

    # tool_calls
    if data.get("tool_calls"):
        print(f"\n🔧 Tool calls: {len(data['tool_calls'])}")
        for i, tc in enumerate(data["tool_calls"]):
            print(f"  [{i + 1}] {tc['name']}")
            if tc["args"]:
                print(
                    f"      {json.dumps(tc['args'], indent=4, ensure_ascii=False)[:300]}"
                )
            if tc["error"]:
                print(f"      ⚠ {tc['error']}")
    elif data.get("no_tool_calls"):
        print(f"\n⚠ No tool calls (content: {data.get('content', '(empty)')[:200]})")

    # reasoning
    if data.get("reasoning"):
        print(f"\n💭 Reasoning ({len(data['reasoning'])} chars):")
        print(f"   {data['reasoning'][:500]}")
    elif data.get("no_reasoning") and not data.get("tool_calls"):
        print("\n⚠ No reasoning received")

    # debug only when both empty
    if not data.get("reasoning") and not data.get("tool_calls"):
        raw = data.get("content") or "(None)"
        print(f"\n🔍 RAW content ({len(raw)} chars): {raw[:400]}")
        usage = data.get("usage", {})
        print(
            f"\n📊 Usage: prompt={usage.get('prompt_tokens', '?')}",
            f"completion={usage.get('completion_tokens', '?')}",
            f"total={usage.get('total_tokens', '?')}",
        )
        print(f"    finish_reason={data.get('finish_reason', '?')}")
        print(
            f"    attrs: content={data.get('content')!r},",
            f"reasoning={data.get('reasoning_raw', 'MISSING')!r},",
            f"tool_calls={data.get('tool_calls_raw', 'MISSING')!r}",
        )

    print()


def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")


# vLLM response helper — normalise getattr for tool_calls / reasoning


def _get_reasoning(message) -> str:
    return getattr(message, "reasoning", None) or message.content or ""


def _get_tool_calls(message):
    """Extract tool_calls, handling vLLM/OpenAI attribute quirks."""
    tc = getattr(message, "tool_calls", None)
    # Double-check: some vLLM builds expose it as a non-existent attr
    if tc is None:
        tc = message.tool_calls if hasattr(message, "tool_calls") else None
    return tc


# ------------------------------------------------------------------
# F1 — Function Calling Only (no thinking)
# ------------------------------------------------------------------


async def task_f1_function_only() -> None:
    """F1 — Function-calling without thinking mode.

    Uses ``tool_choice="required"`` to force the model to call
    the tool.  ``max_tokens`` bumped to 2048 to give it room.
    """
    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=_MESSAGES,
        tools=[_EXTRACT_RELATIONSHIP_TOOL],
        tool_choice="required",
        max_tokens=2048,
        temperature=0.7,
        seed=42,
    )

    choice = r.choices[0].message
    print("=" * 60)
    print("F1: Function Calling Only (no thinking)")
    print("=" * 60)
    print(f"📖 Story : {STORY[:60]}...")

    tool_calls = _get_tool_calls(choice)
    if tool_calls:
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc, "function") else "?"
            args_text = tc.function.arguments if hasattr(tc, "function") else "{}"
            try:
                args = json.loads(args_text)
                print(
                    f"   {name} → {json.dumps(args, indent=2, ensure_ascii=False)[:400]}"
                )
            except json.JSONDecodeError:
                print(f"   {name} → raw: {args_text[:200]}")
    else:
        print(f"⚠ No tool calls. Content: {choice.content or '(empty)'}")

    print()


# ------------------------------------------------------------------
# F2 — Thinking Only (no function calling)
# ------------------------------------------------------------------


async def task_f2_thinking_only() -> None:
    """F2 — Thinking mode without function calling — baseline."""
    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=_MESSAGES,
        max_tokens=2048,
        temperature=0.7,
        seed=42,
        stop=_STOP_REASONING,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    choice = r.choices[0].message
    reasoning = _get_reasoning(choice)

    print("=" * 60)
    print("F2: Thinking Only (no function calling)")
    print("=" * 60)
    print(f"📖 Story : {STORY[:60]}...")
    if reasoning:
        print(f"💭 Reasoning ({len(reasoning)} chars):\n{reasoning[:500]}")
    else:
        print("⚠ No reasoning received")
    print()


# ------------------------------------------------------------------
# F3 — Thinking + Function Calling (THE KEY TEST)
# ------------------------------------------------------------------


async def task_f3_thinking_plus_function() -> None:
    """F3 — **The critical test**: thinking mode + function calling.

    Uses ``tool_choice="required"`` to force a tool call and
    bumps ``max_tokens`` to 4096 for the full reasoning chain.

    Expected (per Gemma-4 design docs):
    1. Model outputs reasoning between ``<|channel>`` and ``<channel|>``
    2. Model outputs ``<|tool_call>`` with structured arguments
    3. vLLM reasoning parser separates reasoning; tool_calls appear on message
    """
    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=_MESSAGES,
        tools=[_EXTRACT_RELATIONSHIP_TOOL],
        tool_choice="required",
        max_tokens=4096,
        temperature=0.7,
        seed=42,
        stop=_STOP_REASONING,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    choice = r.choices[0].message
    reasoning = _get_reasoning(choice)
    tool_calls = _get_tool_calls(choice)

    print("=" * 60)
    print("F3: Thinking + Function Calling ⭐")
    print("=" * 60)
    print(f"📖 Story : {STORY[:60]}...")

    if reasoning:
        print(f"\n💭 Reasoning ({len(reasoning)} chars):")
        print(f"   {reasoning[:500]}")
        if len(reasoning) > 500:
            print(f"   ... ({len(reasoning)} total)")
    else:
        print("\n⚠ No reasoning received (reasoning=None)")

    if tool_calls and len(tool_calls) > 0:
        print(f"\n🔧 Tool calls: {len(tool_calls)}")
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc, "function") else "?"
            args_text = tc.function.arguments if hasattr(tc, "function") else "{}"
            try:
                args = json.loads(args_text)
                print(
                    f"   {name} → {json.dumps(args, indent=2, ensure_ascii=False)[:400]}"
                )
            except json.JSONDecodeError:
                print(f"   {name} → raw: {args_text[:200]}")
    else:
        print("\n⚠ No tool calls received")

    # Debug: always inspect the full response when both reasoning and tool_calls are empty
    if not reasoning and not tool_calls:
        raw = choice.content or "(None)"
        print(f"\n🔍 RAW message.content ({len(choice.content or '')} chars):")
        print(f"   {raw[:600]}")
        # Dump full response attributes for debugging
        print(f"\n📋 Full message attrs: content={choice.content!r}")
        print(f"    reasoning={getattr(choice, 'reasoning', 'MISSING')!r}")
        print(f"    tool_calls={getattr(choice, 'tool_calls', 'MISSING')!r}")
        # Print response usage info
        usage = r.usage
        print(
            f"\n📊 Usage: prompt_tokens={usage.prompt_tokens if usage else '?'}",
            f"completion_tokens={usage.completion_tokens if usage else '?'}",
            f"total_tokens={usage.total_tokens if usage else '?'}",
        )
        print(f"    finish_reason={r.choices[0].finish_reason}")

    print()


# ------------------------------------------------------------------
# F4 — Thinking + Function Calling (without stop token)
# ------------------------------------------------------------------


async def task_f4_thinking_plus_function_no_stop() -> None:
    """F4 — Same as F3 but without ``stop=["<channel|>"]``.

    Tests whether vLLM auto-handles the ``<channel|>`` stop when
    ``--reasoning-parser`` is set at server launch time.
    Uses ``tool_choice="required"`` and ``max_tokens=4096``.
    """
    client = _make_client()

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=_MESSAGES,
        tools=[_EXTRACT_RELATIONSHIP_TOOL],
        tool_choice="required",
        max_tokens=4096,
        temperature=0.7,
        seed=42,
        # No stop token — let vLLM handle it via --reasoning-parser
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    choice = r.choices[0].message
    reasoning = _get_reasoning(choice)
    tool_calls = _get_tool_calls(choice)

    print("=" * 60)
    print("F4: Thinking + Function Calling (no stop token)")
    print("=" * 60)
    print(f"📖 Story : {STORY[:60]}...")

    if reasoning:
        print(f"\n💭 Reasoning ({len(reasoning)} chars):")
        print(f"   {reasoning[:500]}")
    else:
        print("\n⚠ No reasoning received")

    if tool_calls and len(tool_calls) > 0:
        print(f"\n🔧 Tool calls: {len(tool_calls)}")
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc, "function") else "?"
            args_text = tc.function.arguments if hasattr(tc, "function") else "{}"
            try:
                args = json.loads(args_text)
                print(
                    f"   {name} → {json.dumps(args, indent=2, ensure_ascii=False)[:400]}"
                )
            except json.JSONDecodeError:
                print(f"   {name} → raw: {args_text[:200]}")
    else:
        print("\n⚠ No tool calls received")

    print()


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------


async def main() -> None:
    print("\n" + "#" * 60)
    print("# Function Calling + Thinking Test")
    print(f"# Server : {BASE_URL}")
    print(f"# Model  : {MODEL_NAME}")
    print("#" * 60 + "\n")

    # F1: baseline — function calling alone
    await task_f1_function_only()

    # F2: baseline — thinking alone
    await task_f2_thinking_only()

    # F3: the critical test — thinking + function calling (with stop)
    await task_f3_thinking_plus_function()

    # F4: variant — thinking + function calling (no explicit stop)
    await task_f4_thinking_plus_function_no_stop()

    print("#" * 60)
    print("# ALL FUNCTION CALLING TESTS COMPLETE")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
