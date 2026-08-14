---
title: "Speech-to-Text WebUI — 建立 + 完整修復 + 最終驗證 (68)"
date: 2026-08-03
type: agent
count: 68
tags:
  - speech-to-text
  - webui
  - gradio
  - voicetag
  - numba
  - pyannote
  - diarization
  - stt
  - breeze-asr-26
---

# Speech-to-Text WebUI — 建立 + 完整修復 + 最終驗證

## 時間

2026-07-31（WebUI 建立）→ 2026-08-03（修復 + 驗證）

## 一、WebUI 建立（2026-07-31）

### What

建立 Gradio WebUI（`webuis/speech-to-text.py`），提供瀏覽器介面的 Speech-to-Text 功能：

- **轉錄 Tab**：上傳音訊 → 設定引數 → 執行 pipeline → 即時顯示歷程 → 下載 JSON
- **Speaker 管理 Tab**：上傳、改名、刪除 speaker 參考音訊檔案（`test-audio/speaker-ref/`）

Server 跑在 `0.0.0.0:7861`。

### 關鍵設計決策

**直接 import `run_pipeline()`**
- 透過 `importlib.util.spec_from_file_location` 動態載入 `workflows/speech_to_text.py`
- 同場處理 voicetag circular import 問題（預先載入 site-packages 版本到 `sys.modules`）

**Background 執行 + 即時 log 更新**
- `on_run()` 在 Gradio event handler 中啟動 `threading.Thread` 執行 pipeline
- 透過 `sys.stdout`/`sys.stderr` 重定向捕捉輸出
- 每 0.5 秒檢查 thread 狀態，即時更新 `gr.Textbox`

**Speaker 管理**
- `list_speakers()`：掃描目錄，回傳 DataFrame（名稱、檔名、大小、路徑）
- `upload_speaker()`：支援多檔案上傳，自動避同名衝突
- `delete_speaker()`：依 speaker 名稱刪除所有同名音訊檔
- `rename_speaker()`：批次改名（保留副檔名）

### Gradio 6.0 API 調整

- `theme` 從 `Blocks()` 移到 `launch()` 引數
- `Textbox.show_copy_button` 已移除（6.0 不支援）
- `Dataframe.wrap_table` 已移除（6.0 不支援）

## 二、完整修復（2026-08-03）

修復兩個阻斷性問題，使完整 pipeline（Enroll → Diarization → STT）成功執行。

### 1. 修復 Numba `__main__.has no attribute 'capture'` crash

**問題**：`builtins.print = capture` 會修改 `__main__.print`。Numba 的 `@infer_global(print)` 裝飾器在 import 時執行 `getattr(__main__, 'capture')`，但 `capture.__module__ = '__main__'` 且 `capture.__name__ = 'capture'`，導致 `AttributeError`。

**解法**（`webuis/speech-to-text.py`）：

- 建立 `_Capture` class 實作 `write()` / `flush()` / `isatty()`
- 將 `sys.stdout` 和 `sys.stderr` 暫時替換為 capture 物件
- 不碰 `builtins.print`，numba 不受影響
- 在 `run_pipeline` 結束後還原 `sys.stdout` / `sys.stderr`

### 2. 修復 Pyannote 160k sample 分塊問題

**問題**：MP3 音訊解碼後樣本數非 160,000 的整數倍，導致 diarization 階段 `ValueError`。

**解法**（`workflows/speech_to_text.py`）：

- 在 Step 3 呼叫 `vt.transcribe()` 前，檢查 `input_audio_path.suffix.lower() != ".wav"`
- 若為非 WAV 格式，用 `librosa.load(sr=48000)` 讀取 → `sf.write()` 寫入 temp WAV
- `finally` block 清理 temp 檔案
- 此解法與 `serve/voicetag/voicetag_core.py` 的 `identify()` 方法使用的流程完全相同

### 3. Module rename：`speech-to-text.py` → `speech_to_text.py`

Python module 路徑不支援連字號（hyphen），使用 `importlib.util.spec_from_file_location` 可繞過但會產生獨立 namespace 導致 voicetag sub-module 不一致。改用標準 `import` 並將檔案 rename。

## 三、最終驗證（2026-08-03）

完整 pipeline 測試成功：

| 步驟 | 狀態 |
|------|------|
| Step 1 初始化 VoiceTag | ✅ |
| Step 2 Enroll 3 位 speaker | ✅ |
| Step 3 MP3 → WAV 轉換 | ✅ |
| Step 3 Diarization（pyannote） | ✅ 120s 音訊，31 segments |
| Step 3 STT（Breeze-ASR-26） | ✅ 13.9s 完成 |

**測試環境：**
- 音訊：`test-audio/2026_07_21_test.mp3`（120 秒，3 位 speaker）
- Speaker 參考：`test-audio/speaker-ref/`（文.wav, 陳.wav, 黃.wav）
- STT 提供者：Breeze-ASR-26 at `localhost:8750`
- 裝置：CUDA:0
- 結果：31 segments, 3 speakers, 13.9 秒處理時間

### JSON 下載按鈕疑點

使用者回報下載按鈕內容為空，檢查後確認：
- 輸出檔案確實存在且內容正確（`output/2026_07_21_test_stt.json`, 6827 bytes）
- 程式邏輯正確
- **問題原因**：SSH 前端預覽器無法在本機預覽遠端 JSON 檔案
- **結論**：沒有程式 bug，是檢視器限制

## Follow-up

- [ ] OVERLAP 片段的 TSE（Target Speaker Extraction）尚未實作
- [ ] 測試更多不同長度的音訊檔
- [ ] Breeze-ASR-26 需要啟動才能執行 STT（`serve/vllm/launch_BreezeASR26.sh`）
- [ ] 目前 WebUI 測試成功，所有功能正常運作

## References

- [workflows/speech_to_text.py](../../workflows/speech_to_text.py) — Main pipeline
- [workflows/config.yaml](../../workflows/config.yaml) — 設定檔
- [webuis/speech-to-text.py](../../webuis/speech-to-text.py) — Gradio WebUI（port 7861）
- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py) — Reference implementation
- [67_2026_08_03_agent_speech-to-text-workflow-and-webui.md](./67_2026_08_03_agent_speech-to-text-workflow-and-webui.md) — 工作流程 + WebUI 修復
- Commit [cd99e72](https://github.com/.../commit/cd99e72) — 修復 numba crash + WAV conversion