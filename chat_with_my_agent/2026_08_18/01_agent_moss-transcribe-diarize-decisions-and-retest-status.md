---
date: 2026-08-18
topics: [moss-transcribe-diarize, stt-architecture, decisions]
status: final
author: agent
---

# MOSS-Transcribe-Diarize 整合方向拍板與重測狀態

## 時間

2026-08-18

## 做了什麼

- 使用者拍板四項決策（取代日誌 73、75 的「方向修正建議」，正式定案）：
  1. **正式推翻日誌 73 的整合結論**：`modules/asr.py` 重寫為呼叫 MOSS-Transcribe-Diarize microservice；TargetDiarization 降級為參考實作／fallback，非整合對象
  2. **串流輸入缺口不用補**：當前場景是會議整理，輸入與輸出皆 offline；若支援結構化輸出，是後續銜接的一大優勢（語者音色分類、LLM 潤稿等）
  3. **GPU 資源配置由使用者自行分配**，本專案不負責
  4. **崩潰證據交由另一工作空間的 AI 處理**，本端只提供證據摘要
- 使用者提供會議音訊 ground truth：`test-audio/meeting_20260721.mp3` 共 **4 人**，主要 2 人發言、另 2 人短暫附和；能偵測出附和者代表模型厲害；無逐句 ground truth
- 使用者表達架構偏好：模型計算交給**統一、專用的推理引擎**，客戶端只做 API 呼叫（此偏好正被市場帶動）
- 修復 `.python-version`（`3.` → `3.12`），uv 的 `Ignoring unsupported Python request 3.` 警告解除
- 第三輪 live 探測：`/v1/models` 正常；首個 transcription POST（5 秒短音訊）回 **HTTP 500**：`'OmniScheduler' has no attribute '_prev_decode_launch_ts'`（0.08s 即回），**server 過程未離線**
- Live 驗證仍受阻於此 500；`scratch/moss_test.py` 四組測試保持即戰力

## 為什麼

- 會議整理屬 offline 場景，無串流輸入需求，不必等上游 sglang RFC #22474 的 `/v1/realtime` 落地
- 第三輪錯誤從「TCP 層崩潰」變成「Python AttributeError」，指向 sgl-omni 程式碼版本／patch 不一致（`_prev_decode_launch_ts` 像 profiling／time-stamp 欄位），是比 OOM 猜测更明確的修復入手點，可直接交給伺服器端 AI

## How

- 探測：`curl -s -X POST http://10.46.219.5:8750/v1/audio/transcriptions`（`file=test-audio/query_to_cars.wav`、`response_format=verbose_json`）→ 500，0.08s
- `.python-version` 改寫為 `3.12`
- 日誌 75 補記第三輪結果

## Follow-up

- ~~【阻斷中】伺服器端 500（OmniScheduler AttributeError）~~ 已解決：使用者改以 **vLLM ＋ vllm[audio]** 部署（根因：vllm[audio]/soundfile 未裝）；live 驗證全數完成，結果見 77
- ~~重測順序（sgl-omni 版）~~ 已改以 vLLM 版完成：openai SDK json、httpx SSE 串流、hotwords、prompt、並發、diarization 對照 4 人 ground truth
- 重點驗證：diarization 品質（對照 4 人 ground truth，尤其 2 位附和者是否分出）、verbose_json segments 欄位完整性（start/end/speaker 前綴）、latency／TTFT
- 通過後：重寫 `modules/asr.py` 整合計畫（MOSS-TD client，offline-only，結構化輸出為設計前提）；正式 `uv add openai`
- 延後：≥10 分鐘音訊的 speaker 標籤跨塊一致性；運行中版本是否含伺服器端自動分塊

## References

- [75 MOSS-Transcribe-Diarize 研究](75_2026_08_18_agent_moss-transcribe-diarize-research.md)
- [73 TargetDiarization 研究與整合計畫](73_2026_08_14_agent_target-diarization-research-and-integration-plan.md)
- [74 TargetDiarization vs Video2Text 比較](74_2026_08_14_agent_target-diarization-vs-video2text-comparison-research.md)
- [scratch/moss_test.py](../../scratch/moss_test.py)
- `modules/asr.py`、`modules/vad.py`、`test-audio/`
