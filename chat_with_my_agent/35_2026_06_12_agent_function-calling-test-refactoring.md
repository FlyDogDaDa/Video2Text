---
created: 2026-06-12
author: Agent
type: agent
status: draft
tags: [function-calling, thinking-mode, test-script, vllm]
---

# Function Calling 測試指令碼重構：統一 prompt、tool_choice、max_tokens

## What

重構 `test_function_calling.py`（Thinking + Function Calling 測試指令碼），統一四組測試的 prompt、固定 `tool_choice="required"`、提高 `max_tokens`，確保 F1/F3/F4 一定呼叫 tool。

## Changes

### 1. 單一 shared prompt（`_MESSAGES`）

F1～F4 全部共用同一個 `_MESSAGES` 變數，不再各自定義：

```python
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
```

### 2. `tool_choice="required"`（F1/F3/F4）

之前 `tool_choice="auto"` 讓模型選擇「不呼叫 tool」，F1 完全沒 tool_call。
現在全部改為 `"required"` 強制呼叫。

### 3. `max_tokens` 調整

| 測試 | 調整前 | 調整後 | 原因 |
|------|--------|--------|------|
| F1 | 1024 | 2048 | 讓模型有空間輸出完整 tool args |
| F2 | 2048 | 2048 | 維持（只有 thinking） |
| F3 | 2048 | 4096 | reasoning + tool_call 需要更多 token |
| F4 | 2048 | 4096 | 同上 |

### 4. 共享 helper 函式

- `_get_reasoning(msg)` — 統一讀取 `reasoning` / `content`
- `_get_tool_calls(msg)` — 統一處理 vLLM 的 `tool_calls` attribute

### 5. F3 加上 debug dump

當 `reasoning` 和 `tool_calls` 都為空時，印出：
- `message.content` 原始內容
- response usage（prompt/completion/total tokens）
- `finish_reason`
- 完整 message attrs

## Follow-up

- 執行測試，確認 F1/F3/F4 都能拿到 tool_call
- 如果 F3/F4 仍然 `reasoning=None` + `tool_calls=None`，確認 vLLM 的 thinking + function calling 是否有 bug（類似之前 thinking + structured output 的情況）
