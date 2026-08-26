---
created: 2026-06-13
author: Agent
type: agent
status: done
tags: [vllm, breeze-asr-26, transcription, openai-api, audio-processing]
---

# ASR 音訊轉錄工具：Breeze-ASR-26 via vLLM /v1/audio/transcriptions API

## 時間

2026-06-13

## 工作專案

建立一個 ASR 音訊轉錄工具，讓使用者可以透過 OpenAI-compatible API 呼叫 vLLM server 上的 Breeze-ASR-26 模型，進行音訊轉錄。

## 背景

專案需要音訊轉錄功能，但 vLLM 的 Whisper/ASR 模型使用 `/v1/audio/transcriptions` API，而非 `chat.completions` API。這是與 Gemma-4 多模態 API 完全不同的端點。

## 決策

### 1. API 端點選擇

**問題：** 原本假設 Breeze-ASR-26 可以像 Gemma-4 一樣用 chat.completions + multimodal 呼叫。

**研究過程：**
- 先查 vLLM 官方檔案 → 發現 vLLM 支援 speech-to-text via `/v1/audio/transcriptions`
- 查 vLLM blog 文章 → 確認 Whisper 系列模型需要 `--task transcription` flag
- 檢查 vLLM 版本（0.22.1rc1）→ 發現這個版本還不支援 `--task transcription`
- 直接 curl 測試 → 確認伺服器已經在跑，`/v1/audio/transcriptions` 可以正常運作

**結論：**
- vLLM 的 Whisper/ASR 模型使用 **獨立的 Transcription API**，不是 chat completions
- API 端點：`POST /v1/audio/transcriptions`
- 支援的 response format：`text`, `json`, `verbose_json`
- `verbose_json` 的 segments 欄位是空的（目前 vLLM 0.22.1 版本沒有內建 timestamp 回傳）

### 2. 回傳格式

| 格式 | 回傳內容 | timestamp 支援 |
|------|----------|----------------|
| `text` | `{ "text": "..." }` | ❌ |
| `json` | `{ "text": "...", "usage": {"seconds": N} }` | ❌ |
| `verbose_json` | `{ "text": "...", "segments": [], "words": null, "duration": "N" }` | ❌（segments 空）|

**結論：** 目前 vLLM 版本不支援 sentence/word-level timestamps，這個功能需要等到 vLLM 未來版本支援 Whisper 的 VAD（Voice Activity Detection）或 forced alignment。

### 3. 長音訊處理策略

**問題：** 如果音檔很長（>30s），如何處理？

**策略：**
- 使用 `split_audio_into_segments()` 將音檔切成分段
- 每段使用重疊（overlap）避免在句子中間切斷
- 提示詞（prompt）包含分段位置資訊，讓模型只轉錄該時間窗的內容
- 合併結果：直接拼接文字

## 實作細節

### 核心元件

- `chat_wtih_my_agent/38_2026_06_13_asr_audio_transcription/asr_transcribe.py`

### 類別與函式

- **`BreezeASRClient`**: 封裝 `/v1/audio/transcriptions` API 呼叫
  - `transcribe(audio_path, language, prompt)` → `TranscriptionResult`
  - 使用 `openai.AsyncOpenAI().audio.transcriptions.create()`

- **`LongAudioProcessor`**: 長音訊分段轉錄
  - `split_audio_into_segments()`: 將音檔切成分段，使用 overlap
  - 合併結果：拼接文字

- **`get_audio_duration()`**: 使用 `runtime/ffprobe` 取得音檔長度

- **`wait_for_server()`**: 等待 vLLM server 準備好

- **`launch_server()`**: 自動啟動 vLLM server（使用 `launch_BreezeASR26.sh`）

### 使用方式

```bash
# 基本轉錄
uv run -- python asr_transcribe.py intro_voice_cover.wav

# 測試所有音檔
uv run -- python asr_transcribe.py --test-all

# 長音訊（自訂分段和重疊）
uv run -- python asr_transcribe.py long.wav --segment 20 --overlap 5

# 輸出 JSON
uv run -- python asr_transcribe.py intro_voice_cover.wav --output result.json

# 跳過自動啟動伺服器（假設已執行）
uv run -- python asr_transcribe.py intro_voice_cover.wav --no-launch
```

## 測試結果

成功轉錄兩個音檔：

### intro_voice_cover.wav (20.1s)
```
讓我們進入正題 可以看到Craft Panel由三個部分組成 主要的Craft 用來處理選項的分類系統 用來將物品歸位的復原系統 這三個部件 可以用任意的形式蓋出來 可是依我的經驗 我建議他們要反應得越快越好 這樣使用者才可以有最好的體驗
```

### test_audio.wav (30s)
```
沒錯 那個他們公司的關係 他們公司 如果有資金部門 這個資金部門的組長 就是方啟秋 他最厲害的 然後他們公司還蠻傳統 因為做電梯的 做電梯要到現場施工 對啊 志明早我早覺得進去 是要找電器工程師的 也沒有找AI 但是他後來他找我 說要做AI 我就說 那我們都是AI的 那你要那個
```

## 加分項狀態

### 1. 過長聲音處理 ✅

- 已實作 `split_audio_into_segments()` 自動分段
- 使用 overlap（預設 3s）避免句子被切斷
- 長音檔自動切分並拼接結果

### 2. 時間戳記 ❌（目前版本不支援）

- 嘗試 `verbose_json` format → segments 是空的
- 嘗試 VTT/SRT format → vLLM 回報不支援
- 目前 vLLM 0.22.1 的 Whisper 實現沒有內建 VAD/segmentation
- 需要未來版本或 forced alignment 才能實現

## 後續待辦

- [ ] 追蹤 vLLM Whisper 的 timestamp 支援進度
- [ ] 如果未來支援 forced alignment，更新工具以支援 sentence/word-level timestamps
- [ ] 考慮使用 OpenAI Whisper API 作為備案（有 timestamp 支援）

## 參考

- [vLLM Speech-to-Text 檔案](https://docs.vllm.ai/en/latest/contributing/model/transcription/)
- [vLLM Whisper 實作範例](https://davidgao7.github.io/posts/vllm-v1-whisper-transcription/)
- [Breeze-ASR-26 HuggingFace](https://huggingface.co/MediaTek-Research/Breeze-ASR-26)
- `src/vllm_launch/launch_BreezeASR26.sh`: vLLM launch script
- `runtime/ffprobe`: 音檔分析工具
- `intro_voice_cover.wav`: 測試音檔
- `chat_wtih_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/references/test_audio.wav`: 參考音檔
