---
created: 2026-09-16
author: agent
type: agent
tags: [video2text, long-audio, diarization, speaker-embedding, ek7qdwwxz6a, execution-blocked, vllm]
---

# Ek7qDwwXZ6A 新管線執行：前置全就緒，ASR 伺服器 CUDA OOM 阻塞

## What

依使用者指示「一次做到底；過程每產出一點不論成敗都記錄；完成後一次性匯報」執行新管線，結果如下：

- ✅ **下載完成**：`audio.webm` 119.93MiB（format 251）＋ `video.mp4` 640.31MiB（format 399/AV1 成功）
- ✅ **composite 合流**：`ffmpeg -c copy` → MKV，av1＋opus，7823.828s
- ✅ **`audio_full.wav`** 抽出：pcm_s16le／16kHz／mono，7823.812813s
- ✅ **embedding 環境**：`torch 2.14.0+cpu` ＋ resemblyzer（含 webrtcvad 2.0.10 編譯成功），import 驗證通過
- ✅ **兩支管線腳本寫入＋py_compile 通過**：`transcribe_iterative.py`（迭代切分轉錄，含 per-part 輸出與續跑）、`speaker_unify.py`（centroid 相似度矩陣＋constrained union-find）
- ✅ **`speaker_unify.py` 煙霧測試通過**（舊資料 N9boWvU-KkA 唯讀、輸出至 `validate_on_n9bo/`）：
  G01/G02 兩個全域語者、963 段全數指派、0 未定案，與舊片實際 2 位語者吻合
- ❌ **ASR 伺服器四次啟動均失敗**：#1 KV cache 不足（max_model_len 131072 需 14GiB，
  僅剩 9.14GiB）→ 加 `--max-model-len 81920` 修正；#2/#3/#4 仍在 `init_device` 階段
  CUDA OOM。根因：SGLang qwen176b 佔 ~97GB／128GB（8/31 日誌已知環境限制）
- 新增 `serve/vllm/launch_MOSS_TD.sh`（此前 MOSS 伺服器由使用者手動啟動、無腳本存檔）

## Why

- 使用者指示一次做到底；遇硬阻塞（需釋放 GPU 才能起 ASR 伺服器）依偏離處理規則停止，
  不擅自停用使用者的 SGLang 176B 服務
- 煙霧測試價值實證：阻擋式 ambiguous flag 在 resemblyzer 空間過嚴
  （cross-person 基線 0.77–0.81 > τ=0.75），8 組全數被 flag → 改為合併時
  次優替代 margin 審查（事後記錄、不擋合併），τ 上調 0.90

## How

- 關鍵檔案：`exp/Ek7qDwwXZ6A/`（TODO.md、execution-log.md、audio_full.wav、
  scripts/、validate_on_n9bo/）、`serve/vllm/launch_MOSS_TD.sh`
- 伺服器啟動：`nohup bash serve/vllm/launch_MOSS_TD.sh > exp/Ek7qDwwXZ6A/asr_server.log 2>&1 &`
- 煙霧測試：`exp/Ek7qDwwXZ6A/.venv/bin/python exp/Ek7qDwwXZ6A/scripts/speaker_unify.py
  exp/N9boWvU-KkA exp/Ek7qDwwXZ6A/validate_on_n9bo`

## Follow-up

- [ ] **使用者裁決 GPU**：停 SGLang qwen176b（或其他釋放方式）
- [ ] 啟動 ASR 伺服器 → health 檢查
- [ ] 跑 `transcribe_iterative.py`（估 ~6 段、每段 ~2.5min、串行）
- [ ] 跑 `speaker_unify.py` → 處理 low_margin_merges（若有）
- [ ] s2twp 轉繁體 → 統計驗證 → 日誌收尾＋腳本歸檔

## Uncertainty

- 直播檔 BGM／掌聲／長沉默對 diarization／embedding 的干擾程度
- 實際語者人數（片名 ≥5 人，可能有進出）
- max-model-len 81920 對 24min 音訊 token 數是否足（vLLM 估計上限 85600，未經實測）
- 「無輸出=結束」在長直播中段的誤判風險（離片尾遠的無輸出暫定「前進 NOMINAL 繼續」）

## References

- [討論細節](references/02_agent_ek7-pipeline-execution.md)
- [執行日誌（時間軸）](../../exp/Ek7qDwwXZ6A/execution-log.md)
- [實驗 TODO](../../exp/Ek7qDwwXZ6A/TODO.md)
- [煙霧測試報告](../../exp/Ek7qDwwXZ6A/validate_on_n9bo/speaker_unify_report.json)
