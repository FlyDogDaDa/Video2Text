---
title: "STT Prompt 功能研究 — voicetag / Breeze-ASR-26 支援度分析 (69)"
date: 2026-08-03
type: agent
count: 69
tags:
  - speech-to-text
  - stt
  - prompt
  - whisper
  - voicetag
  - breeze-asr-26
  - vllm
  - research
---

# STT Prompt 功能研究 — voicetag / Breeze-ASR-26 支援度分析

## 時間

2026-08-03

## 一、問題背景

`webuis/speech-to-text.py` 完整 pipeline 已測試成功，但在轉錄品質上出現同音字錯誤：

> 「逐字稿」被聽成「竹子搞」

需要研究能否透過 `prompt` 引數改善專有名詞辨識。

## 二、研究方法

啟動 4 個 sub-agent 平行研究：

| 編號 | 子任務 | 分析目標 |
|------|--------|----------|
| A | voicetag `openai_stt.py` 內部實作 | 是否已有 prompt 引數？ |
| B | OpenAI / Whisper API prompt 規格 | 格式、限制、使用方式 |
| C | Breeze-ASR-26 部署與 API | vLLM 是否支援 prompt？ |
| D | voicetag `pipeline.py` 流程 | `transcribe()` 如何傳遞引數給 provider？ |

## 三、研究結果

### A. voicetag `openai_stt.py` 內部實作

**`transcribe()` 目前接受的引數：**

| 引數 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `audio` | `np.ndarray` | （必填） | 音訊資料 |
| `sr` | `int` | 16000 | 取樣率 |
| `language` | `Optional[str]` | None | 語言程式碼 |

**❌ 沒有 `prompt` 引數。**

`kwargs` 只包含 `model`、`file`、有條件的 `language`。其他 provider 結構類似。

> ⚠️ **注意：** `openai_stt.py` 是第三方套件 (`site-packages/voicetag/providers/`)，
> 不能直接修改（`uv sync` 會被覆蓋）。需透過 fork / patch 機制修改。

### B. OpenAI / Whisper API Prompt 規格

`prompt` 是**文字範本（非指令）**，讓 Whisper 模仿其用詞風格。

**用途：**
- 修正專有名詞拼法（品牌名、人名、縮寫）
- 切檔後延續上下文（前一段的最後幾句）
- 指定標點符號與口語習慣

**錯誤 vs 正確示範：**

```
❌ "Please correctly spell 逐字稿 instead of 竹子搞"
✅ "逐字稿, 竹科, 政府公文, 檔案, 紀錄, 報告"
```

**限制：**
- `whisper-1` 上限 **224 tokens**
- 停用字元：`<`, `>`, `\r`, `\n`
- prompt 語言必須與音檔主要語言一致
- 超過限制 → 超出部分被忽略；格式錯誤 → 400 錯誤

### C. Breeze-ASR-26 部署與 API 支援度

**部署方式：** vLLM ASR 服務，`vllm serve "MediaTek-Research/Breeze-ASR-26"`

**API 端點：** `POST /v1/audio/transcriptions`（OpenAI 相容格式）

**✅ 完整支援 `prompt` 引數。**

vLLM Transcriptions API 規格：
```
prompt: Optional text to guide the transcription style (optional)
```

**❌ 不支援 grammar / constrained decoding**（這些功能僅存在於 vLLM Chat Completions API）。

**部署引數備註：** `--gpu-memory-utilization 0.035` 異常低（通常 Whisper 至少需要 2-6GB VRAM），可能為了低視訊記憶體環境共存。

### D. voicetag `pipeline.py` 引數傳遞

`transcribe()` 方法：
```python
def transcribe(
    self,
    audio_path: str | Path,
    provider: str = "openai",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    language: Optional[str] = None,
    **provider_kwargs,
) -> TranscriptResult:
```

**可以透過 `**provider_kwargs` 傳遞**，但各 provider 的 `__init__` / `transcribe()` 尚未定義 `prompt` 引數，所以目前會被無視。

## 四、結論

| 專案 | 現況 | 支援度 |
|------|------|--------|
| Breeze-ASR-26 (vLLM) 支援 prompt | vLLM ASR API | ✅ 完整支援 |
| OpenAI-compatible 格式一致 | `/v1/audio/transcriptions` | ✅ 一致 |
| voicetag 目前實作 prompt | `openai_stt.py` | ❌ 目前沒有 |
| Whisper prompt 限制 | 224 tokens，無 `< > \r \n` | 需注意 |

## 五、實作規劃

需要修改的檔案（由外而內）：

| 檔案 | 修改內容 | 優先順序 |
|------|----------|--------|
| `webuis/speech-to-text.py` | 新增 prompt 輸入框（textarea） | 🟡 前端 |
| `workflows/speech_to_text.py` | `run_pipeline()` 接受 `prompt` 引數 | 🟡 橋接 |
| `voicetag/providers/openai_stt.py` | `__init__` / `transcribe()` 新增 `prompt` | 🔴 核心 |
| `voicetag/pipeline.py` | `transcribe()` 接受 `prompt` 並傳遞 | 🔴 核心 |

## 六、Follow-up

- [ ] 實作 `openai_stt.py` 的 prompt 支援
- [ ] 實作 `pipeline.py` 的 prompt 傳遞
- [ ] 實作 `speech_to_text.py` 工作流的 prompt 橋接
- [ ] 實作 WebUI 的 prompt 輸入介面
- [ ] 測試 prompt 對同音字錯誤的改善效果

## References

- [workflows/speech_to_text.py](../../workflows/speech_to_text.py) — Main pipeline
- [webuis/speech-to-text.py](../../webuis/speech-to-text.py) — Gradio WebUI
- [serve/voicetag/.venv/.../voicetag/providers/openai_stt.py](../../serve/voicetag/.venv/lib/python3.10/site-packages/voicetag/providers/openai_stt.py) — OpenAI STT provider
- [serve/voicetag/.venv/.../voicetag/pipeline.py](../../serve/voicetag/.venv/lib/python3.10/site-packages/voicetag/pipeline.py) — Pipeline orchestration
- [serve/vllm/launch_BreezeASR26.sh](../../serve/vllm/launch_BreezeASR26.sh) — Breeze-ASR-26 vLLM launch script
- [68_2026_08_03_agent_speech-to-text-webui-all.md](./68_2026_08_03_agent_speech-to-text-webui-all.md) — WebUI 完整修復紀錄