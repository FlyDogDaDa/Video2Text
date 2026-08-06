---
created: 2026-06-11
author: agent
type: agent
status: final
tags: [vllm, offline-inference, structured-output, reasoning, gemma4, delayed-guided-decoding]
---

# vLLM Delayed Guided Decoding: Offline Inference with Gemma-4 Reasoning

## What

Researched how to use vLLM's delayed guided decoding (structured output) together with reasoning/thinking mode in **offline inference** (i.e., `LLM.generate()`, not OpenAI server API).

Produced a complete working example targeting the actual model used in the project: `google/gemma-4-12B-it-qat-w4a16-ct`.

## Why

Our system uses `SliceResult` (Pydantic model with flat schema) as the structured output target. We want to ensure vLLM can enforce this JSON schema **while also allowing the model to think first** — the delayed guided decoding mechanism should skip structured output enforcement during `</think>` blocks and only apply it to the final JSON output.

Key questions:
- Does `LLM.generate()` support `--reasoning-parser` equivalent?
- How does Gemma 4's thinking mode integrate with `StructuredOutputsParams`?
- How to extract both reasoning steps and the structured JSON from the raw output?

## How

### Server vs Offline: reasoning + structured outputs

| Aspect | Server Mode | Offline Mode |
|--------|-------------|--------------|
| Enable reasoning | `--reasoning-parser gemma4` on `vllm serve` | `LLM(model=..., reasoning_parser="gemma4")` |
| Enable thinking | `extra_body={"chat_template_kwargs": {"enable_thinking": True}}` | `llm.get_tokenizer().apply_chat_template(..., chat_template_kwargs={"enable_thinking": True})` |
| Structured output | `extra_body={"structured_outputs": {"json": schema}}` | `SamplingParams(structured_outputs=StructuredOutputsParams(json=schema))` |
| Reasoning extraction | `response.choices[0].message.reasoning` | `parse_thinking_output(raw_text)` |

### Working example (Gemma-4-12B)

```python
import json
from pydantic import BaseModel, Field
from decimal import Decimal
from vllm import LLM, SamplingParams
from vllm.sampling_params import StructuredOutputsParams
from vllm.reasoning.gemma4_utils import parse_thinking_output

class SliceResult(BaseModel, frozen=True):
    start_at: Decimal = Field(ge=0, description="Start timestamp in seconds")
    end_at: Decimal = Field(ge=0, description="End timestamp in seconds")
    visual: str | None = Field(default=None, description="What happens visually")
    dialogue: str | None = Field(default=None, description="Spoken dialogue, [Speaker]: format")
    sound: str | None = Field(default=None, description="Music, SFX, ambient sounds")

# 1. Initialize model (offline, Gemma-4)
llm = LLM(
    model="google/gemma-4-12B-it-qat-w4a16-ct",
    max_model_len=262144,          # match launch script
    tensor_parallel_size=2,         # match TP_SIZE:2
    trust_remote_code=True,         # match --trust-remote-code
    quantization="compressed-tensors", # match --quantization
    reasoning_parser="gemma4",      # enables reasoning token parsing
)

# 2. Extract JSON Schema
json_schema = SliceResult.model_json_schema()

# 3. Configure structured output + thinking
sampling_params = SamplingParams(
    temperature=0.0,
    max_tokens=2048,
    structured_outputs=StructuredOutputsParams(json=json_schema),
)

# 4. Build prompt with thinking enabled
messages = [{"role": "user", "content": "Describe the visual and audio content of this 30-second video slice."}]

prompt = llm.get_tokenizer().apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    chat_template_kwargs={"enable_thinking": True},  # Gemma-4: thinking disabled by default
)

# 5. Generate
outputs = llm.generate(prompt, sampling_params=sampling_params)
raw_text = outputs[0].outputs[0].text

# 6. Split reasoning → JSON
parsed = parse_thinking_output(raw_text)
print("Reasoning:", parsed.reasoning)

result = SliceResult.model_validate_json(parsed.text)
print("SliceResult:", result.model_dump(mode="json"))
```

### How delayed guided decoding works internally

1. Gemma-4 outputs reasoning inside `<|channel|>thinking<|channel|>` blocks
2. `xgrammar` (structured output backend) **detects the thinking delimiter** and **temporarily disables** JSON masking
3. Once `</think>`/thinking end is reached, `xgrammar` **re-enables** JSON schema enforcement
4. The final JSON output is guaranteed to match `SliceResult` schema

### Parameters matching `launch_Gemma4-12b.sh`

| Shell flag | Offline equivalent | Purpose |
|---|---|---|
| `--reasoning-parser gemma4` | `LLM(..., reasoning_parser="gemma4")` | Parse Gemma-4 thinking blocks |
| `--max-model-len 262144` | `LLM(..., max_model_len=262144)` | Sequence length |
| `--tensor-parallel-size 2` | `LLM(..., tensor_parallel_size=2)` | Multi-GPU |
| `--trust-remote-code` | `LLM(..., trust_remote_code=True)` | Load custom model code |
| `--quantization compressed-tensors` | `LLM(..., quantization="compressed-tensors")` | QAT quantized model |

### Notes

- Gemma 4 reasoning is **disabled by default** (unlike Qwen3 which enables it by default). Must pass `enable_thinking=True`.
- `parse_thinking_output()` from `vllm.reasoning.gemma4_utils` strips `<|channel>` delimiters and returns a `ParsedReasoning` named tuple with `.reasoning` and `.text` (JSON portion).
- Server mode has `--structured-outputs-config.enable_in_reasoning=True` for Qwen3 Coder, but **Gemma 4 does not need this flag** — it's only required for Qwen3 Coder models (v0.11.2+).

## Follow-up

- Write a concrete `generate_slice()` function using this pattern
- Test with an actual video slice to validate structured output quality
- Consider batching multiple slices in a single `llm.generate()` call

## References

- [src/models.py](../src/models.py)
- [src/vllm_launch/launch_Gemma4-12b.sh](../src/vllm_launch/launch_Gemma4-12b.sh)
- [vLLM Structured Outputs docs](https://docs.vllm.ai/en/latest/features/structured_outputs.html)
- [vLLM Reasoning Outputs docs](https://docs.vllm.ai/en/latest/features/reasoning_outputs.html)
- [vLLM offline + reasoning example](https://github.com/vllm-project/vllm/blob/main/examples/features/structured_outputs/structured_outputs_offline.py)
