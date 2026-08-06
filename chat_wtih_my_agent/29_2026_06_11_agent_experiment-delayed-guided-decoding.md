---
created: 2026-06-11
author: agent
type: agent
status: final
tags: [vllm, guided-decoding, reasoning, gemma4, structured-output, experimental]
---

# Experiment: vLLM Delayed Guided Decoding + Gemma-4 Reasoning — Result

## What

實驗性驗證 vLLM offline 模式下 `StructuredOutputsParams`（guided JSON）與 Gemma-4 思考模式（reasoning/thinking）能否同時啟用。

## Why

之前研究指出 vLLM 的 `StructuredOutputsConfig` 會記錄 `reasoning_parser='gemma4'`，理論上應支援「延遲引導解碼」——thinking 階段關閉 JSON 遮罩、結束後才重新介入。但需要實機驗證。

## How

使用 `test_vllm_delayed_guided_decoding.py`：

1. `LLM(reasoning_parser="gemma4")` + `StructuredOutputsParams(json=schema)`
2. `chat_template_kwargs={"enable_thinking": True}`
3. 在 prompt 中明確要求 model 先思考再輸出 JSON
4. 用 `parse_thinking_output()` 分離思考與 JSON

## Results

### ✅ 成功部分

| 項目 | 結果 |
|------|------|
| `reasoning_parser` 參數載入 | ✅ Engine 正確識別 `reasoning_parser='gemma4'` |
| `StructuredOutputsParams` | ✅ JSON 輸出完全符合 schema |
| Pydantic 驗證 | ✅ `SliceResult.model_validate_json()` 通過 |
| `parse_thinking_output` | ✅ 可用，回傳 dict 格式（非 named tuple） |

### ❌ 失敗部分

**Thinking mode 從未觸發。** Raw output 僅 428 字元，直接輸出 JSON，沒有任何 `</think>` 或思考標籤。

### 根本原因分析

從 vLLM log 可以看到：

```
structured_outputs_config=StructuredOutputsConfig(
    backend='auto',
    disable_any_whitespace=False,
    disable_additional_properties=False,
    reasoning_parser='gemma4',
    reasoning_parser_plugin='',
    enable_in_reasoning=False  # ← 注意！
)
```

**關鍵發現：`StructuredOutputsParams` + `reasoning_parser` 無法同時運作。**

原因推測：
1. xgrammar 的 guided JSON grammar 從 token 1 就開始強制 JSON 結構
2. 這擋住了模型輸出思考標籤（如 `</think>`）的空間
3. `enable_in_reasoning=False` 表示預設不啟用 reasoning 內的結構化輸出
4. 即使 server 模式有 `--structured-outputs-config.enable_in_reasoning=True`，offline 模式目前無對應參數

## Conclusion

- **可以同時傳兩個參數**（不會 crash）
- **但 thinking 不會實際產生**——guided JSON 從 token 1 就開始 enforcing
- **這表示 delayed guided decoding 在 Gemma-4 上不生效**（或尚未實作完成）

## Follow-up

- 檢查 vLLM 是否有 `enable_in_reasoning=True` 的 offline API 對應
- 或考慮用兩階段 approach：先 free generation 收集思考，再 guided JSON 產生結果
- 對本專案來說，**不需要 thinking 模式**——結構化輸出本身就夠了

## References

- [src/types.py](../src/types.py) — `SliceResult` 模型
- [test_vllm_delayed_guided_decoding.py](../test_vllm_delayed_guided_decoding.py) — 測試腳本
- [vLLM Structured Outputs docs](https://docs.vllm.ai/en/latest/features/structured_outputs.html)
