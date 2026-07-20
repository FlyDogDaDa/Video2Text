"""Two-stage output: Free-form thinking → Structured anchoring.

Design
------
| Phase | tool_choice | thinking | 目的 |
|-------|-------------|----------|------|
| 1 | ``"none"`` | ✅ | 自由思考，拿到自然語言描述 |
| 2 | ``"required"`` | ❌ | 帶第一輪輸出，強制結構化 tool call |

驗證 vLLM 在 Phase 2 的 `tool_choice="required"` 是否能在**不帶 thinking**
的情況下正確回傳 tool_calls。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from openai import AsyncOpenAI

BASE_URL = "http://localhost:8746/v1"
MODEL_NAME = "google/gemma-4-12B-it-qat-w4a16-ct"

TOOL = {
    "type": "function",
    "function": {
        "name": "extract_relationships",
        "description": "Extract all relationships from the story.",
        "parameters": {
            "type": "object",
            "properties": {
                "stories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "predicate": {"type": "string"},
                            "object": {"type": "string"},
                        },
                        "required": ["subject", "predicate", "object"],
                    },
                },
            },
            "required": ["stories"],
        },
    },
}

STORY = (
    "Alice runs a bakery in downtown Portland and is married to Bob, "
    "who works as a software engineer at a startup. "
    "Charlie is Alice's brother and also lives in Portland; "
    "he fears public speaking but is secretly a talented poet. "
    "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
    "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
)

BASE_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are a knowledge-graph extractor. "
            "Think step by step about the relationships between characters. "
            "After thinking, describe the relationships in natural language."
        ),
    },
    {"role": "user", "content": f"Extract all relationships:\n\n{STORY}"},
]


async def main():
    client = AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")

    print("\n" + "#" * 60)
    print("# Two-Stage Output: Free-form → Structured Anchoring")
    print(f"# Server : {BASE_URL}")
    print("#" * 60 + "\n")

    # ── Phase 1: Free-form thinking ──────────────────────────────────
    print("── Phase 1: Free-form thinking (tool_choice='none') ──")
    r1 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=BASE_MESSAGES,
        max_tokens=4096,
        temperature=0.7,
        seed=42,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        tool_choice="none",
    )

    c1 = r1.choices[0].message
    reasoning = getattr(c1, "reasoning", None) or c1.content or ""
    print(f"💭 Reasoning ({len(reasoning)} chars):")
    print(f"   {reasoning[:300]}")
    print(f"\n📝 Output ({len(c1.content or '')} chars):")
    print(f"   {c1.content[:300] if c1.content else '(None)'}")

    # ── Phase 2: Structured anchoring ────────────────────────────────
    print("\n" + "-" * 60)
    print("── Phase 2: Structured anchoring (tool_choice='required') ──")
    r2 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=BASE_MESSAGES
        + [{"role": "assistant", "content": c1.content}],  # 第一輪輸出
        tools=[TOOL],
        tool_choice="required",
        max_tokens=1024,
        temperature=0.1,
        seed=42,
    )

    c2 = r2.choices[0].message
    tool_calls = getattr(c2, "tool_calls", None) or []
    print(f"🔧 Tool calls: {len(tool_calls)}")
    print(
        f"📊 Usage: prompt={r2.usage.prompt_tokens} "
        f"completion={r2.usage.completion_tokens} "
        f"total={r2.usage.total_tokens}"
    )

    if tool_calls:
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc, "function") else "?"
            args = tc.function.arguments if hasattr(tc, "function") else "{}"
            try:
                parsed = json.loads(args)
                print(f"   {name} → {len(parsed.get('stories', []))} relationships")
                print(
                    f"   JSON:\n{json.dumps(parsed, indent=2, ensure_ascii=False)[:400]}"
                )
            except json.JSONDecodeError:
                print(f"   {name} → raw:\n{args[:300]}")
    else:
        print("❌ No tool calls")
        print(f"   content={c2.content!r}")
        print(f"   finish_reason={r2.choices[0].finish_reason}")

    print("\n" + "#" * 60)
    print("# DONE")
    print("#" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
