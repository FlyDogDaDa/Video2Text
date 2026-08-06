import asyncio

from openai import AsyncOpenAI

async def test():
    client = AsyncOpenAI(base_url="http://localhost:8746/v1", api_key="EMPTY")

    # Simple test first
    print("=== Test 1: response_format only ===")
    r = await client.chat.completions.create(
        model="google/gemma-4-12B-it-qat-w4a16-ct",
        messages=[{"role": "user", "content": "Answer: Hello"}],
        max_tokens=64,
        temperature=0.1,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            },
        },
    )
    m = r.choices[0].message
    print(f"reasoning: {getattr(m, 'reasoning', None)}")
    print(f"content: {m.content}")

    # Test 2: thinking only
    print("\n=== Test 2: thinking only ===")
    r2 = await client.chat.completions.create(
        model="google/gemma-4-12B-it-qat-w4a16-ct",
        messages=[{"role": "user", "content": "Think then say hello"}],
        max_tokens=64,
        temperature=0.7,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    m2 = r2.choices[0].message
    print(f"reasoning: {m2.reasoning}")
    print(f"content: {m2.content}")

    # Test 3: both together
    print("\n=== Test 3: thinking + structured output ===")
    r3 = await client.chat.completions.create(
        model="google/gemma-4-12B-it-qat-w4a16-ct",
        messages=[{"role": "user", "content": "Think then output JSON"}],
        max_tokens=256,
        temperature=0.7,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "test",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
            },
        },
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    m3 = r3.choices[0].message
    print(f"reasoning: {m3.reasoning}")
    print(f"content: {m3.content}")
    print(f"all fields: {m3.model_dump(exclude_none=True)}")

    print(f"content: {m3.content}")
    print(f"all fields: {m3.model_dump(exclude_none=True)}")

asyncio.run(test())
