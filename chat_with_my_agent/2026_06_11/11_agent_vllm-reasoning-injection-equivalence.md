---
created: 2026-06-11
author: Agent
type: agent
status: final
tags: [vllm, gemma-4, reasoning, injection-equivalence, two-stage, function-calling]
---

# vLLM Gemma-4 推理注入等價性驗證實驗

## What

驗證「兩階段推理注入」是否等價於「原始連續思考→輸出」。

設計三組實驗（全部 `temperature=0`）：

| 組別 | 做法 | 目的 |
|------|------|------|
| **T1** | 提問 → 純文字回覆（無思考） | 無思考的基線 |
| **T2** | 提問 → `enable_thinking=True` → 純文字回覆 | 原始連續思考的輸出 |
| **T3** | 提問 → thinking → 抽離 reasoning 注入 `assistant.content` → 純文字回覆 | 插入思考的輸出 |

比較 **T2 和 T3** 的純文字回覆是否一致，評估兩階段方法是否等價於原始連續思考。

## Why

vLLM 目前在單一請求中同時支援 `reasoning` + `structured output` 有侷限性（如 `enable_thinking` + `response_format` 組合時 `reasoning` 欄位可能為空）。

為了在 API 模式下實現推理引導，通常採用「兩階段方法」：
1. 第一次呼叫開啟思考，停產於 `<channel|>`，抽離 reasoning
2. 第二次呼叫將 reasoning 注入 `assistant.content`，強制輸出結構化內容

需要驗證：這種兩階段注入是否真的能復現模型「原生連續思考」的效果，還是隻是有額外效果或等效。

## How

### 實驗程式碼

`chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/test_two_stage_equivalence.py`

**1. T1（基線）：**
```python
r1 = await client.chat.completions.create(
    model=MODEL_NAME, messages=base_messages,
    max_tokens=1024, temperature=0, seed=42,
)
reply1 = r1.choices[0].message.content
```

**2. T2（原始連續思考）：**
```python
r2 = await client.chat.completions.create(
    model=MODEL_NAME, messages=base_messages,
    max_tokens=4096, temperature=0, seed=42,
    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
)
reasoning_len = len(getattr(r2.choices[0].message, "reasoning", "") or "")
reply2 = r2.choices[0].message.content
```

**3. T3（兩階段注入，兩種注入方式）：**

**Variant A（直接塞 raw text）：**
```python
reasoning = getattr(r3a.choices[0].message, "reasoning", None) or ...
messages_with_reasoning = [
    {"role": "assistant", "content": reasoning},
]
r3b = await client.chat.completions.create(
    model=MODEL_NAME, messages=messages_with_reasoning,
    max_tokens=1024, temperature=0, seed=42,
)
```

**Variant B（手動包 channel 標籤）：**
```python
channel_injected = f"<|channel>thought\n{reasoning}\n<channel|>"
messages_with_reasoning = [
    {"role": "assistant", "content": channel_injected},
]
```

### 實驗結果

| 組別 | 注入方式 | 輸出長度 | 是否等價於 T2 |
|------|---------|---------|-------------|
| T1 基線 | 無思考 | 1279 chars | — |
| T2 原始連續思考 | `enable_thinking=True` | 654 chars | — |
| T3 Variant A | `content = reasoning` | 604 chars | ✗ 不等價 |
| T3 Variant B | `content = <|channel>thought\n{reasoning}\n<channel|>` | 1118 chars | ✗ 不等價 |

**觀察：**
- T3 Variant A 的風格最接近 T2（精簡輸出），但仍有微小差異
- T3 Variant B 的風格更接近 T1（長篇幅分析），完全不等價

### 結論

**`<|channel>` / `<channel|>` 是 vLLM reasoning parser 用於從 output 提取 thinking 的，不支援在 input 中手動包來恢復模型的 thinking 狀態。**

兩階段注入推理只是 vLLM 支援不周時的替代方案，無法完全等價於原生連續思考→輸出。

## 展望：Function Calling (工具呼叫) 作為結構化輸出的替代方案

### 問題背景

我們剛驗證了 `response_format` (guided JSON decoding) 無法與 `enable_thinking` 同時正常工作：開啟後 reasoning 欄位變空，或產出 `do. do. do.` 幻覺。這使得「思考 → 結構化輸出」的唯一可行路徑變為兩階段注入（且已證明不等價於原生連續思考）。

### 為什麼 Function Calling 才是正解

Gemma-4 設計思考模式的 **真正用途** 就是配合 Function Calling。Google 官方 Prompt Formatting 明確指出 thinking + tool use 是原生相容的：

```
<|turn>user ...what happens in these frames?<turn|>
<|turn>model
<|channel>thought
Thinking Process: 1. Analyze each frame... 2. Extract relationships...
<channel|>
<|tool_call>extract_relationships { "story": "Alice runs a bakery..." }
<tool_call|>
<|tool_response> { "triples": [{"subject":"Alice","predicate":"married","object":"Bob"}] }
<tool_response|>
<|turn>model
<|tool_response> Final answer here.
<|tool|>
```

**與 `response_format` 的關鍵差異：**

| 特性 | `response_format` (guided JSON) | `tools` (Function Calling) |
|------|------|------|
| thinking 相容 | ❌ `reasoning` 變空或幻覺 | ✅ 原生支援，先思考再呼叫 |
| JSON 生成方式 | 模型 token by token 硬寫 JSON | vLLM 自動將 tool response 解析為 JSON |
| 推理幹擾 | 從 token 1 強制 JSON 格式，幹擾思考過程 | `<|channel|>` 內部自由推理，不受 JSON 綁架 |
| 結構化程度 | 依賴模型寫出合法 JSON（可能失敗） | 工具定義強制結構，輸出可靠 |
| vLLM 支援 | ⚠️ 與 thinking 互斥 | ✅ `--tool-call-parser gemma4` 原生支援 |

**Function Calling 的工作流程：**

1. 開啟 `enable_thinking=True` 讓模型自由思考
2. 模型在 `<|channel|>` 內完成推理後，輸出 `<|tool_call>` 標籤
3. vLLM 自動解析 tool response 並轉為結構化資料
4. 不需要手動注入 reasoning、不需要兩次呼叫

### 未來方向

- [ ] 建立 Function Calling 測試：驗證 Gemma-4 + vLLM 的 thinking + tool use 是否正常工作
- [ ] 以 Function Calling 取代目前兩階段 `task_double_call_reason_then_structured()`
- [ ] 考慮這作為生產環境的首選結構化輸出方案

## Follow-up

- 接受兩階段是 API 模式下的 fallback 方案
- 生產環境可根據需求選擇：
  - 追求速度：使用純 `task_structured_output()`（無思考）
  - 需要推理品質：使用 `task_double_call_reason_then_structured()`（兩階段，直接塞 reasoning 到 content）
  - **長期首選：Function Calling（待驗證）** — 原生支援 thinking + 結構化輸出

## References

- [test_two_stage_equivalence.py](../chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/test_two_stage_equivalence.py)
- [how_to_use_vllm_multimodal_via_openai_api.py](../chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/how_to_use_vllm_multimodal_via_openai_api.py)
- [33_2026_06_11_agent_vllm-gemma4-reasoning-three-variants.md](./33_2026_06_11_agent_vllm-gemma4-reasoning-three-variants.md)
