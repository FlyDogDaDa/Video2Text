---
created: 2026-06-12
author: Human + Agent
type: human
status: draft
tags: [vllm, gemma-4, server-api, function-calling, two-stage, structured-output, pipeline, async]
---

# 策略總結：vLLM Server API + 兩階段穩定輸出

## 背景

Video2Text 專案一直在尋找最穩定的結構化輸出方案。從離線推理轉向 Server API，再從 guided JSON 轉向兩階段 free-form + function calling，歷經多次試錯。以下是完整的決策脈絡。

---

## 一、策略轉向：離線推理 → Server API

### 問題

離線模式 (`LLM.generate()`) 的痛點：

| 痛點 | 說明 |
|------|------|
| 載入開銷 | 每次啟動 4-5s 載入 + 16s init，頻繁重啟頻繁重付 |
| 多模態 bug | 文字輸出亂碼、audio numpy array 格式不匹配、視覺+音訊同時用觸發錯誤 |
| 無並行 | 全部串列執行 |
| guided decoding | 需要手動 `StructuredOutputsParams` |
| reasoning 分離 | 需要手動 `parse_thinking_output()` |

### 決策

**Server API 模式確定為最終架構方向。**

```
main.py → slice_video → AsyncOpenAI → vllm serve (:8746)
```

關鍵差異：
- 離線模式：`main.py` 負責所有事（載入、template、推理、parse）
- Server 模式：`main.py` 只做切片 + HTTP 傳送 + 結果收集，所有多模態處理由 vLLM server 內部完成

---

## 二、Thinking + Structured Output 的 bug

### 發現

Server API 驗證時發現：

| 設定 | 結果 |
|------|------|
| `enable_thinking=True` 單獨 | ✅ reasoning 正常分離 |
| `response_format` 單獨 | ✅ JSON 正常 |
| **兩者並用** | ❌ `reasoning=None`，JSON 被截斷 + 大量重複 `AI is a AI` |

**診斷：** vLLM 沒有正確處理 `reasoning` + `structured output` 並用的情況，即使有 `--structured-outputs-config.enable_in_reasoning=True` flag 也不生效。

---

## 三、三變體探索與 Function Calling 曙光

### 三變體

將 Task 4 拆成三個獨立變體並行跑通：

| 變體 | 策略 | 結果 |
|------|------|------|
| 4a | 推理 Only（stop at `<channel|>`） | ✅ 完整 chain-of-thought |
| 4b | 純結構化輸出（guided JSON） | ✅ 12 triplets，直接 JSON |
| 4c | 兩次呼叫：先推理 → 再結構化輸出 | ✅ 帶推理輸出 9 triplets |

### 關鍵洞察

**Function Calling 是模型原生能力，thinking + tool use 是原生相容的**（Gemma-4 設計思考模式的真正用途就是配合 Function Calling）。

```
<|channel|>thought...
<channel|>
<|tool_call>extract_relationships { ... }
<tool_call|>
```

---

## 四、Reasoning 注入等價性實驗

### 實驗設計

| 組別 | 做法 | 目的 |
|------|------|------|
| T1 | 提問 → 純文字回覆（無思考） | 基線 |
| T2 | 提問 → enable_thinking → 純文字回覆 | 原始連續思考的輸出 |
| T3 | 提問 → thinking → 抽離 reasoning 注入 `assistant.content` → 純文字回覆 | 兩階段注入 |

### 結論

**兩階段注入推理 ≠ 原生連續思考。**

- T3 Variant A（直接塞 raw text）：風格接近 T2，但仍有微小差異
- T3 Variant B（手動包 channel 標籤）：風格更接近 T1（長篇幅分析），完全不等價

`<|channel>` / `<channel|>` 是 vLLM reasoning parser 用於從 output 提取 thinking 的，**不支援在 input 中手動包來恢復模型的 thinking 狀態**。

兩階段注入推理只是 vLLM 支援不周時的替代方案，無法完全等價於原生連續思考→輸出。

---

## 五、Function Calling 實測

### 測試設計

| 測試 | 內容 | 目的 |
|------|------|------|
| F1 | Function Calling only（無 thinking） | 確認 baseline |
| F2 | Thinking only（無 function calling） | 確認 baseline |
| F3 | **Thinking + Function Calling** | 關鍵測試 |

### 發現 1：`tool_choice="required"` 會阻塞 thinking

當同時設定 `enable_thinking=True` 和 `tool_choice="required"` 時：
- `finish_reason=tool_calls` ✅
- `completion_tokens=511` ✅
- **但 `tool_calls=[]`（空 list）❌**

模型確實呼叫了 tool（vLLM server 端產生了 tool call），但 SDK 解析時 tool_calls 沒有回傳到 Python 物件。這是 vLLM 的 bug。

### 發現 2：`stop=["<channel|>"]` 會阻止 tool call

在 F3 加了 `stop=["<channel|>"]` 後，模型在 `<channel|>` 就停了，沒有機會輸出 tool call。只有移除 stop token 才能拿到 tool_calls。

### 發現 3：兩階段是唯一可行方案

| 設定 | 能拿到 reasoning? | 能拿到 tool_calls? |
|------|:-:|:-:|
| thinking ✅ + `tool_choice="required"` | ✅ | ❌ bug |
| thinking ✅ + `stop` token + tool_choice=`auto` | ✅ | ❌ 被截斷 |
| thinking ✅ + tool_choice=`auto` | ✅ | ⚠️ 不穩定 |
| **thinking ❌ + `tool_choice="required"`** | N/A | ✅ **穩定** |

---

## 六、兩階段穩定輸出策略（Final）

### 設計

```
Phase 1: Free-form thinking
  enable_thinking=True, tool_choice="none"
  → 拿到完整推理 + 自然語言描述

Phase 2: Structured anchoring
  enable_thinking=False, tool_choice="required"
  → 帶第一輪輸出，強制工具呼叫，保證 JSON 格式
```

### 驗證結果

用 `test_two_stage_output.py` 驗證：

| Phase | 設定 | 結果 |
|-------|------|------|
| Phase 1 | thinking ✅, tool_choice=`none` | ✅ reasoning (2611 chars) + 自然語言 (993 chars) |
| Phase 2 | thinking ❌, tool_choice=`required` | ✅ tool_call (8 relationships, clean JSON) |

**結論：兩階段策略可行！**

### 適用場景

```python
async def extract_structured(client, slice_input, params):
    # Phase 1: 自由思考，拿到自然語言描述
    r1 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=[system_prompt, slice_input],
        max_tokens=4096,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        tool_choice="none",
    )
    
    # Phase 2: 帶第一輪結果，強制結構化輸出
    r2 = await client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": slice_input},
            {"role": "assistant", "content": r1.content},  # 第一輪輸出
        ],
        tools=[_VIDEO_ANALYSIS_TOOL],
        tool_choice="required",
        max_tokens=1024,
    )
    
    tool_call = r2.choices[0].message.tool_calls[0]
    return SliceResult.model_validate_json(tool_call.function.arguments)
```

---

## 七、並行處理原則

每次 HTTP 請求都是 **I/O bound**（網路往返 + GPU 推論），完全可以用 `asyncio.gather` 把多個請求平行送出：

```python
async def extract_all(video_path, params):
    slices = await slice_video(video_path, params)
    async with AsyncOpenAI(base_url=...) as client:
        tasks = [extract_structured(client, s, params) for s in slices]
        return await asyncio.gather(*tasks)  # 並行！不是 for loop 順序 await
```

> **原則：** I/O bound 任務用 `asyncio.gather` 並行。並行數受限時用 `asyncio.Semaphore(16)` 控制 max_concurrent_requests。

---

## 總結

```
離線推理 (bug 多、無並行)
    → Server API (穩定、並行)
        → guided JSON + thinking (❌ bug)
        → Function Calling + thinking (⚠️ vLLM bug: tool_calls=[] 回傳失敗)
        → **兩階段 Free-form → Structured Anchoring** (✅ 驗證通過)
```

---

## Follow-up

- [ ] 實作兩階段模式在 `src/pipeline/extractor.py`
- [ ] 比較 guided JSON vs 兩階段的輸出品質
- [ ] 在 Swarm Mode 中，Round 1 用兩階段、Round 2+ 帶 context sandwich
- [ ] 測試 `asyncio.gather` 並行多個 slice 的效能提升

---

更新日期：2026-06-12
