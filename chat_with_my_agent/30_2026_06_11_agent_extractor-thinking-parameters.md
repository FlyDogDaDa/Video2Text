---
created: 2026-06-11
author: agent
type: agent
status: final
tags: [vllm, extractor, thinking, two-stage, guided-decoding]
---

# Extractor: `thinking` + `thinking_max_tokens` parameters

## What

在 `extract_structured()` 新增 `thinking` 與 `thinking_max_tokens` 兩個引數，提供兩階段生成（two-stage generation）的切換開關。

## Why

根據 vLLM GitHub #17638 討論的 consensus：offline 模式無法在 `StructuredOutputsParams` 的同時啟用 reasoning parser 和 thinking。`enable_in_reasoning` 僅有 server 端 CLI flag 對應，offline API 無對應引數。

因此採用 community 建議的 workaround：**兩階段生成**——Stage 1 自由生成收集思考，Stage 2 帶入思考結果後用 guided JSON 產出最終結構化輸出。

## How

### 引數

| 引數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `thinking` | `bool` | `False` | `True` 啟用兩階段生成 |
| `thinking_max_tokens` | `int` | `512` | Stage 1 最大 token 數 |

### 流程

```
thinking=False（預設，single-pass）
├─ chat template: enable_thinking=False
└─ llm.generate() → 直接產出 JSON

thinking=True（two-stage）
├─ Stage 1
│   ├─ SamplingParams(temperature=0.7, max_tokens=thinking_max_tokens, seed=42)
│   ├─ chat template: enable_thinking=True
│   └─ llm.generate() → 自由生成思考文字
│
└─ Stage 2
    ├─ 將 Stage 1 文字作為 assistant role 插入 context
    ├─ chat template: enable_thinking=False
    ├─ 帶入圖片 + 系統 prompt + 思考結果
    └─ llm.generate(structured_outputs=...) → 導出生成 JSON
```

### 輸出

成功時，thinking 模式會顯示 `(two-stage)` 標記：

```
[  0] [   0.0s –  30.0s] 32 frames, 1 audio clips
 ✅ Extracted (two-stage) | reasoning=256 chars

[  1] [  30.0s –  60.0s] 32 frames, 1 audio clips
 ✅ Extracted | reasoning=0 chars
```

## Follow-up

- 實際跑一段影片測試兩階段的 JSON 品質是否有提升
- 評估 KV cache 在 Stage 2 的 reuse 效率（理論上 Stage 1 的 prompt tokens 會被 cache）
- 考慮在 `main.py` 或上游呼叫處暴露這兩個引數

## References

- [src/pipeline/extractor.py](../src/pipeline/extractor.py) — `extract_structured()`
- [GitHub #17638](https://github.com/vllm-project/vllm/discussions/17638) — vLLM structured generation + reasoning in offline mode
- [29_2026_06_11_agent_experiment-delayed-guided-decoding.md](./29_2026_06_11_agent_experiment-delayed-guided-decoding.md) — 前次實驗結果
