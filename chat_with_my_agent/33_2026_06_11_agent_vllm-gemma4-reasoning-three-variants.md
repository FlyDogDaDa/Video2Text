---
created: 2026-06-11
author: Agent
type: agent
status: final
tags: [vllm, gemma-4, reasoning, structured-output, openai-api]
---

# vLLM Server API — Gemma-4 推理三變體實作與驗證

## What

將 `how_to_use_vllm_multimodal_via_openai_api.py` 的 Task 4 拆成三個獨立變體，分別測試 Gemma-4 推理模式的不同使用方式，並全部一次並行跑通。

## Why

原 Task 4 將 thinking + structured output 合併在單一請求中，存在兩個問題：

1. 透過 `stop="<channel|>"` 提前停止後，`message.content` 為 `None`，必須讀 `message.reasoning` 欄位（vLLM reasoning parser 的行為）。
2. 單次請求同時要求 thinking + guided JSON 時，max_tokens 1024 可能不夠，且 server 端的 `<channel|>` 停止行為不如預期。

拆成三個變體可分別測試：
- 4a：純推理（看 chain-of-thought）
- 4b：純結構化輸出（無 thinking）
- 4c：兩次呼叫（先推理 → 再帶推理結果做結構化輸出）

## How

### 檔案修改

`chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/how_to_use_vllm_multimodal_via_openai_api.py`

**1. 新增 `_STOP_REASONING` 常數**

```python
_STOP_REASONING = ["<channel|>"]
```

Gemma-4 的 token 定義（來自 Google 官方文件）：
- `<|think|>` — 啟動思考模式
- `<|channel>` — 思考內容開始
- `<channel|>` — 思考內容結束（stop token）

**2. 拆成三個 async function**

| 函式 | 策略 | stop tokens | thinking | response_format |
|------|------|------------|----------|-----------------|
| `task_reasoning_only()` | 思考 + 在 `<channel|>` 停止 | `["<channel|>"]` | ✅ (via `extra_body`) | ❌ |
| `task_structured_output()` | 無思考，直接 guided JSON | 無 | ❌ | ✅ |
| `task_double_call_reason_then_structured()` | 兩次呼叫：Call1 推理 → Call2 結構化輸出 | Call1: `["<channel|>"]` | Call1: ✅ | Call2: ✅ |

**3. 修正 `stop` 參數位置**

`stop` 必須放在 `create()` 外層（OpenAI SDK 標準參數），不是 `extra_body`：

```python
# ❌ 錯誤
extra_body={"stop": _STOP_REASONING, ...}

# ✅ 正確
stop=_STOP_REASONING,
extra_body={"chat_template_kwargs": {"enable_thinking": True}},
```

**4. 修正 reasoning 讀取方式**

vLLM reasoning parser 把 `<channel|>` 之間的內容拆到 `message.reasoning`，而非 `message.content`：

```python
m = r.choices[0].message
reasoning = getattr(m, "reasoning", None) or m.content or ""
```

**5. 跑全部 6 個任務並行**

```python
await asyncio.gather(
    task_text(),
    task_image(),
    task_audio(),
    task_reasoning_only(),                  # Task 4a
    task_structured_output(),               # Task 4b
    task_double_call_reason_then_structured(),  # Task 4c
)
```

**6. 印出格式改善**

標題移到 API 呼叫後，框住生成結果：
```
============================================================
Task 4c: Double Call — Reason → Structured Output
============================================================
📖 Story : Alice runs a bakery...
📞 Call 1 (reasoning, stop at <channel|>):
💭 Reasoning:
*   Input: A short story about Alice, Bob, Charlie, Diana, and Eve.
    ...
📞 Call 2 (structured output, no thinking):
🤖 JSON:
{ "triples": [...] }
📊 Extracted : 9 triplets
```

### 驗證結果

| Task | 狀態 | 關鍵結果 |
|------|------|---------|
| Task 1: Pure Text | ✅ | 日落描寫完成 |
| Task 2: Multi-Image | ✅ | 正確描述 3 張圖 |
| Task 3: Audio | ✅ | 音訊為中文（原始影片 short_test.mp4 第 5 秒提取 30s），模型輸出韓語為幻覺 |
| Task 4a: Reasoning Only | ✅ | 完整 chain-of-thought（約 4100+ 字），停於 `<channel|>` |
| Task 4b: Structured Output | ✅ | 12 triplets，直接 JSON 輸出 |
| Task 4c: Double Call | ✅ | Call 1 思考 → Call 2 帶思考輸出 9 triplets |

所有 6 個任務並行執行成功，vLLM server 自動調度。

## Follow-up

- 考慮把 `task_structured_output()` 作為生產模式（最快、token 最省）
- 4c double-call 雖然多一次呼叫但能確保思考品質，適合複雜推理場景
- Task 3 音訊為中文（`short_test.mp4` 第 5 秒提取 30s），模型輸出「네, 저는 100% 긍정적인…」韓語重覆為明顯幻覺。音訊內容可能是影片中的背景音或雜訊，需要檢查原始音訊。
- **Function Calling 方向**：`response_format` 無法與 `enable_thinking` 同時使用（思考為空或 `do. do. do.` 幻覺）。Function Calling 是模型原生能力，思考 + 工具調用是原生兼容的（`<channel>` → `tool_call` → `tool_response`），建議後續實作探索此方向。

## References

- [34_2026_06_11_agent_vllm-reasoning-injection-equivalence.md](./34_2026_06_11_agent_vllm-reasoning-injection-equivalence.md)

- [how_to_use_vllm_multimodal_via_openai_api.py](../chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/how_to_use_vllm_multimodal_via_openai_api.py)
- [Gemma-4 Prompt Formatting](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- [Gemma4 Reasoning Parser](https://docs.vllm.ai/en/latest/api/vllm/reasoning/gemma4_reasoning_parser/)
- [30_2026_06_11_agent_extractor-thinking-parameters.md](./30_2026_06_11_agent_extractor-thinking-parameters.md)
