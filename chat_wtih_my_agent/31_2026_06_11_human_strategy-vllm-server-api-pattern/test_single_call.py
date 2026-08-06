"""Quick test: Can we get BOTH reasoning and content in ONE call?"""

import asyncio
import json
from typing import List

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

BASE_URL = "http://localhost:8746/v1"
MODEL_NAME = "google/gemma-4-12B-it-qat-w4a16-ct"


class RelationTriple(BaseModel):
    subject: str = Field(..., description="The person or entity doing the action")
    predicate: str = Field(..., description="Relationship type")
    object: str = Field(..., description="The person or entity being acted upon")


class StoryAnalysis(BaseModel):
    triples: List[RelationTriple] = Field(..., description="List of triplets")


story = (
    "Alice runs a bakery in downtown Portland and is married to Bob, "
    "who works as a software engineer at a startup. "
    "Charlie is Alice's brother and also lives in Portland; "
    "he fears public speaking but is secretly a talented poet. "
    "Diana is Charlie's girlfriend and they plan to move to Seattle next spring. "
    "Eve is Bob's mentor at work and Alice sometimes bakes cookies for her office."
)


_SYSTEM_PROMPT_TRIPLES = """\
You are a knowledge-graph extractor. Read the short story, think step
by step about the relationships between characters, and then output a
JSON list of relation triplets following the provided schema."""


async def test_single_call_full_response():
    """Test: thinking + structured JSON in ONE request, no stop."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_TRIPLES},
        {
            "role": "user",
            "content": f"Read this story and extract all relationships:\n\n{story}",
        },
    ]

    client = AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY")

    json_schema = StoryAnalysis.model_json_schema()
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "story_analysis", "schema": json_schema},
    }

    r = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=4096,
        temperature=0.7,
        seed=42,
        response_format=response_format,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    m = r.choices[0].message
    reasoning = getattr(m, "reasoning", None) or ""
    content = m.content or ""

    print(f"len(reasoning)={len(reasoning)}")
    print(f"len(content)={len(content)}")
    print(f"content[:200]={content[:200]!r}")
    print(f"reasoning[:200]={reasoning[:200]!r}")


if __name__ == "__main__":
    asyncio.run(test_single_call_full_response())
