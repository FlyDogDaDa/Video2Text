---
date: 2026-08-18
topics: [moss-transcribe-diarize, sglang-omni, stt-server-module, streaming]
status: research-complete
author: agent
---

# MOSS-Transcribe-Diarize 研究：對 TargetDiarization 整合決斷的衝擊

## 時間

2026-08-18

## 做了什麼

- 研究 OpenMOSS-Team/MOSS-Transcribe-Diarize 0.9B 規格與使用方法（HF model card、GitHub、sglang-omni 官方 cookbook 與原始碼）
- 查詢運行中服務 http://10.46.219.5:8750/v1：`/v1/models`、`/openapi.json`
- 下載官方測試音訊至 `test-audio/`（gaokao-listening.wav 雙語者、query_to_cars.wav）
- 撰寫 live 測試腳本 `scratch/moss_test.py`（openai 庫非串流、extra_body 串流、httpx SSE 三組測試；因伺服器中途重啟未跑完）
- 評估此模型對日誌 73、74 整合決斷的衝擊

## 為什麼

使用者已用 sgl-omni 部署 MOSS-Transcribe-Diarize，要求研究其規格、openai 庫可用性、雙向串流能力，並指出可能顛覆日誌 73、74「整合 TargetDiarization 為 STT 伺服器模組」的決斷。

## 關鍵發現

### 規格

- 0.9B Audio LLM：Whisper-medium encoder（80 mel bins、16 kHz、4x time merge + MLP adaptor）＋ Qwen3 風格 decoder（28L、hidden 1024），128K context
- 單次推理完成：轉寫 ＋ 說話人 diarization（[S01]、[S02]… 匿名標籤）＋ 起訖時間戳 ＋ 聲學事件
- 50+ 語言、單次最長 ~90 分鐘音訊
- INTERSPEECH 2026 MLC-SLM 第一；AISHELL-4 / Alimeeting / Podcast / Movies 的 CER 與 cpCER 優於 GPT-4o、Gemini 3 Pro、Doubao、ElevenLabs
- Apache-2.0

### API（運行中服務已確認）

- `POST /v1/audio/transcriptions`（OpenAI 相容 multipart）
- 參數：`file`、`model`、`language`、`prompt`（hotword/instruction）、`response_format`（json / verbose_json / text）、`temperature`、`max_new_tokens`、`stream`（bool，OpenAPI 已確認存在）
- `verbose_json` 回傳 parsed segments（start、end、speaker 前綴 text）；`json` / `text` 回傳原始 transcript
- `max_new_tokens` 省略時伺服器依音訊長度自動縮放：`max(5120, 10 tokens/sec)`
- main 分支另有伺服器端長音訊自動分塊並行轉寫（verbose_json 每塊一段）；運行中版本是否有此功能未驗證

### openai 庫

- 非串流可行：`client.audio.transcriptions.create(model=..., file=..., response_format="verbose_json")`
- SDK 無 transcriptions 串流 API，SSE 需改用 httpx 處理
- verbose_json 的 segments 經 SDK pydantic 解析後欄位是否完整（start/end/speaker 前綴）待 live 驗證

### 雙向串流

- **串流輸出：支援**。`stream=true` → SSE：`transcript.text.delta`（增量，50ms 節流）→ `transcript.text.done`（全文＋usage）→ `[DONE]`；僅 `json` / `text` 格式（不含 verbose_json）；chunked prefill 期間抑制輸出
- **串流輸入：目前部署不支援**。端點只接受完整檔案；運行中服務 OpenAPI 無 `/v1/realtime` 路由
- 上游狀態：sgl-project/sglang RFC #22474（已 close）＋ M1 PR #22848 實作 WS `/v1/realtime` 增量 PCM 輸入（16/24/48 kHz pcm16，OpenAI Realtime 轉寫事件）；sglang-omni main 另有 `serve/realtime`（Realtime 協議＋server-side VAD auto-commit＋背景 verbatim transcription），但設計給 omni 語音助理 session，未在此部署
- 官方 cookbook 原話：ASR「streaming input is possible via cumulative chunking but not yet optimized」，原生 streaming in/out 的 encoder 架構開發中

### 對日誌 73、74 的衝擊

- **被取代**：ASR ＋ diarization ＋ 時間戳三合一 → `modules/asr.py` stub 可直接改叫此 microservice；`modules/vad.py` 主流程角色大減（單次 ~90 分鐘免分段）；日誌 74 Phase 4 雙層 diarization（CAM++/Pyannote）降為校驗／精修層
- **不能被取代**：串流輸入（即時場景仍是缺口，TargetDiarization 的 WebSocket 串流仍是唯一現成選項）、音訊後處理管線（降噪/分離/修復，Phase 2）、影片理解與摘要（Video2Text 多模態定位）、真實身份對應（speaker 標籤匿名且相對於輸入音訊）
- **關鍵風險**：長音訊分塊轉寫時 speaker 標籤跨塊一致性未驗證；0.9B 需獨佔 GPU，與現有 vllm 環境並存策略待規劃
- **方向修正建議**：STT 主路徑改為 MOSS-TD sgl-omni microservice；TargetDiarization 降為參考實作／即時串流 fallback，而非整合對象

## Live 驗證（2026-08-18 两轮）

### 已確認（server 存活期間）

- `/v1/models`：模型 ID `OpenMOSS-Team/MOSS-Transcribe-Diarize`，owned_by `sglang-omni`
- `/openapi.json`：`/v1/audio/transcriptions` 的 form 欄位含 `stream`（bool, default false），參數與 main 分支文件一致
- 端點清單：無 `/v1/realtime`（串流輸入不可用，如上述）

### 阻塞問題：伺服器在第一個轉寫請求時崩潰

- 第一轮：`/v1/models`、`/openapi.json` 成功後，第一個 transcription POST 即 connection refused（TCP 層，請求未送出），server 後續完全離線
- 第二轮（使用者重啟 server 後）：`/v1/models` 成功 → 第一個 transcription POST（2 分鐘 mp3, verbose_json）→ connection refused → server 再度離線
- 第三輪（同日、使用者修復後）：`/v1/models` 正常 → 第一個 transcription POST（5 秒短音訊 query_to_cars.wav, verbose_json）→ **HTTP 500：`'OmniScheduler' has no attribute '_prev_decode_launch_ts'`**（0.08s 即回）→ **server 過程未離線**；模式從「TCP 層崩潰」轉為「推理路徑 AttributeError」，疑似 sgl-omni 版本／patch 不一致，決策與後續見 76
- 模式：**GET 類輕量請求正常，第一個實際推理請求到達時崩潰**；疑似首次推理時 CUDA graph capture / encoder 初始化 / OOM
- 已備好測試資產：`test-audio/meeting_20260721.mp3`（48 kHz stereo, 2:00）與 16 kHz mono wav 版；`scratch/moss_test.py` 四組測試（openai 非串流 verbose_json、httpx SSE 串流、extra_body stream、stream+verbose_json 負測）待 server 穩定後執行

### 需要使用者端資訊

- 崩潰時 sgl-omni 主控台 / 容器日誌（CUDA error? OOM? traceback?）
- `dmesg` / `journalctl -k` 是否有 OOM killer
- 崩潰前後 `nvidia-smi`
- 用 5 秒短音訊重試，區分「首個請求必崩」與「長 prefill / 大檔案才崩」

## Follow-up

- ~~【阻斷中】修復 sgl-omni 推理解析失敗~~ 已解決：使用者改以 vLLM ＋ vllm[audio] 部署，live 驗證全數完成，見 77
- 伺服器穩定後執行 `scratch/moss_test.py`：驗證 openai 庫請求、SSE 串流、verbose_json 欄位完整性
- 驗證長音訊分塊轉寫的 speaker 標籤一致性
- 確認運行中 sgl-omni 版本是否含伺服器端自動分塊
- 依驗證結果重新撰寫 `modules/asr.py` 整合計畫（取代日誌 73 的下一步）
- 附帶：`.python-version` 內容異常（uv 警告 `Ignoring unsupported Python request 3.`），待確認

## References

- [MOSS-Transcribe-Diarize HF model card](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)
- [sglang-omni cookbook: MOSS-Transcribe-Diarize](https://sgl-project.github.io/sglang-omni/cookbook/moss_transcribe_diarize.html)
- [sglang RFC #22474: Real-Time Streaming Audio Input for ASR](https://github.com/sgl-project/sglang/issues/22474)
- [73 TargetDiarization 研究與整合計畫](73_2026_08_14_agent_target-diarization-research-and-integration-plan.md)
- [74 TargetDiarization vs Video2Text 比較](74_2026_08_14_agent_target-diarization-vs-video2text-comparison-research.md)
- [76 整合方向拍板與重測狀態](76_2026_08_18_agent_moss-transcribe-diarize-decisions-and-retest-status.md)
- [scratch/moss_test.py](../../scratch/moss_test.py)
- `modules/asr.py`、`modules/vad.py`、`workflow.py`、`test-audio/`
