---
created: 2026-06-11
author: Agent
type: agent
status: draft
tags: [swarm-extraction, structured-output, vllm-parameters, gemma4-sampling]
---

# 蜂群式結構化提取 — 單輪測試與 vLLM 引數調校

## What

實作 `swarm_extract()` 函式並整合 vLLM 結構化輸出，完成單輪蜂群提取全流程測試。取得階段性成果：模型能正確理解影片內容、輸出合理 JSON（雖有格式瑕疵）。

## Why

- 需要將「影音提取」升級為「結構化內容提取」——即對每個視窗送 vLLM 進行視覺 + 音訊分析，產出 `SliceResult` 格式的 JSON。
- 之前 `temperature=0.1` 設定過低，導致輸出速度極慢（26.72 秒/片）且 JSON 被截斷。需改用 Google 官方推薦引數。

## How

### 1. 修正 `load_model()` — 修復版本相容性問題

**檔案：** `main.py` `load_model()` 函式

| 修復專案 | 做法 |
|---------|------|
| `num_soft_tokens` 缺失 | 加入 `hf_overrides={"vision_config": {"num_soft_tokens": 1120}}`（與 `multimodal_infer.py` 同） |
| `limit_mm_per_prompt` 不足 | 預設值改設 `{"image": 4, "audio": 1}`（29 幀 → 取代表性幀） |
| `max_model_len` 過小 | 2048 → 16384，容納 29 張圖片 + audio + prompt |

### 2. 修正 `extract_structured()` — vLLM 多模態呼叫

**檔案：** `main.py` `extract_structured()` 函式

| 修正專案 | 之前 | 之後 |
|---------|------|------|
| `llm.generate()` API | 錯誤格式 `llm.generate("", sampling_params, multi_modal_data=...)` | 正確格式 `llm.generate({"prompt": prompt, "multi_modal_data": ...}, sampling_params)` |
| Chat template | 手動建構 base64 image | 使用 `AutoProcessor.apply_chat_template()` |
| Audio placeholder | 未放入 prompt | 加入 `{"type": "audio"}` placeholder |

### 3. 測試指令碼 `test_swarm.py` — 官方引數驗證

**檔案：** `test_swarm.py`

```python
SamplingParams(
    temperature=1.0,        # Google 官方標準
    top_p=0.95,             # Google 官方標準
    top_k=64,               # Google 官方標準
    repetition_penalty=1.1, # 緩解 Gemma 4 重複問題
    max_tokens=2048,
    seed=42,
)
```

## 測試結果（Phase 1: 單輪，short_test.mp4，60 秒）

### 單輪提取（無 vLLM）

```
✅ 3 slices extracted
  Slice 0: [0.0-30.0s] frames=(29, 1082, 1920, 3), audio_clips=1
  Slice 1: [28.0-58.0s] frames=(29, 1082, 1920, 3), audio_clips=1
  Slice 2: [56.0-60.0s] frames=(3, 1082, 1920, 3), audio_clips=1
```

### 結構化提取（含 vLLM）

| 指標 | 結果 |
|------|------|
| 速度 | 16.88 秒/片（比 `temperature=0.1` 時快 ~40%） |
| JSON 解析 | ❌ 格式錯誤（引號問題：`"man' with`、`"Man""`） |
| 重複問題 | ✅ 改善（只有 `"這裡是我"` 一句，未無限重複） |
| 內容品質 | ✅ 描述了 DAW 介面、Google Meet、男聲中文等 |

### 模型輸出範例

```json
{
  "description": {
    "visual": "The video displays a recording of a screen split into two sections...",
    "audio": "The audio features a male speaker who is explaining something..."
  },
  "transcription": {
    "audio": [{"text": "這裡是我", "speaker": "Man"}],
    "visual": "A person talking in a meeting..."
  },
  "time_range": {"start": 0.0, "end": 30.0}
}
```

## Follow-up

- [ ] **加上 guided decoding** — 使用 vLLM Structured Outputs 強制合法 JSON，修復引號格式錯誤
- [ ] **測試多輪蜂群** — 對 3 個 slice 全部跑 vLLM 結構化提取
- [ ] **長影片測試** — 用 57.7 分鐘的 `2026_05_11-19_18_26_louder4x.mp4` 實機驗證
- [ ] **最佳化 prompt** — 目前 prompt 較簡短，可加入更多引導語提升描述品質

## References

- [main.py](23_2026_06_11_references_swarm-structured-extraction/main.py) — `swarm_extract()`, `extract_structured()`, `load_model()`
- [test_swarm.py](23_2026_06_11_references_swarm-structured-extraction/test_swarm.py) — 單輪測試指令碼
- [src/utils/slice.py](../src/utils/slice.py) — `IOCacheVideo`, `SliceParams`
- [src/models.py](../src/models.py) — Pydantic `SliceResult` schema
- [chat_wtih_my_agent/18_vllm_audio_extraction_logic.md](./18_vllm_audio_extraction_logic.md) — vLLM 音訊/影片行為分析
- [chat_wtih_my_agent/15_2026_06_09_agent_vllm-offline-inference-script.md](./15_2026_06_09_agent_vllm-offline-inference-script.md) — `multimodal_infer.py`
- vLLM Structured Outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/
- Google Gemma 4 audio: https://ai.google.dev/gemma/docs/capabilities/audio
- HuggingFace Gemma 4 E4B sampling: temperature=1.0, top_p=0.95, top_k=64
