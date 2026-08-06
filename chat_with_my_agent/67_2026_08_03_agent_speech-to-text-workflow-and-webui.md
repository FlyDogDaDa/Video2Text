---
title: "Speech-to-Text — Workflow complete + WebUI fixes (67)"
date: 2026-08-03
type: agent
count: 67
tags:
  - speech-to-text
  - voicetag
  - workflow
  - webui
  - gradio
  - numba
  - pyannote
  - diarization
---

# Speech-to-Text 工作流程 + WebUI 修復

## 時間

2026-07-31（工作流程完成）→ 2026-08-03（WebUI 修復）

## 一、工作流程完成（2026-07-31）

### What

完成 `workflows/speech_to_text.py` 工作流程，整合 voicetag 與 Breeze-ASR-26。

### Key features

- **`device: auto` 選項**：自動偵測 GPU 並選擇 `cuda:0` 或 `cpu`
- **端對端測試**：使用 `test-audio/保修工程會議.wav`（40 分鐘）成功輸出 JSON
- **Circular import 修復**：手動載入 `site-packages/voicetag` 到 `sys.modules`

### 測試結果（40 分鐘音訊）

| 項目 | 結果 |
|------|------|
| **device 偵測** | `auto` → `cuda:0` 正確 |
| **speaker 註冊** | 4 位（婕、文、陳、黃），各 1 個樣本 |
| **segments** | 813 個，含 OVERLAP 偵測 |
| **audio 長度** | 2404.9 秒（約 40 分鐘） |
| **處理時間** | 250.4 秒（約 4 分鐘） |
| **輸出** | `output/保修工程會議_stt.json` |

## 二、WebUI 建立（2026-07-31）

### What

建立 Gradio WebUI（`webuis/speech-to-text.py`），提供瀏覽器介面的 Speech-to-Text 功能：

- **轉錄 Tab**：上傳音訊 → 執行 pipeline → 即時顯示歷程 → 下載 JSON
- **Speaker 管理 Tab**：上傳、改名、刪除 speaker 參考音訊檔案

### 關鍵設計

- 透過 `importlib.util.spec_from_file_location` 動態載入 `workflows/speech_to_text.py`
- Background thread + `sys.stdout`/`sys.stderr` 重定向捕捉日誌（非 `builtins.print`）
- Speaker 管理：`list_speakers()`, `upload_speaker()`, `delete_speaker()`, `rename_speaker()`

### Gradio 6.0 API 調整

- `theme` 從 `Blocks()` 移到 `launch()` 參數
- 移除 `Textbox.show_copy_button`（6.0 不支援）
- 移除 `Dataframe.wrap_table`（6.0 不支援）

## 三、WebUI 完整修復（2026-08-03）

修復兩個阻斷性問題，使完整 pipeline 成功運行。

### 1. 修復 Numba `__main__.has no attribute 'capture'` crash

**問題**：`builtins.print = capture` 修改 `__main__.print`。Numba 的 `@infer_global(print)` 裝飾器在 import 時執行 `getattr(__main__, 'capture')` 失敗。

**解法**（`webuis/speech-to-text.py` L279~335）：

- 建立 `_Capture` class 實作 `write()` / `flush()` / `isatty()`
- 將 `sys.stdout` 和 `sys.stderr` 暫時替換為 capture 物件
- 不碰 `builtins.print`，numba 不受影響

### 2. 修復 Pyannote 160k sample 分塊問題

**問題**：MP3 音訊解碼後樣本數非 160,000 的整數倍，導致 diarization 階段 `ValueError`。

```
ValueError: requested chunk [00:00:00.000 --> 00:00:10.000]
from 2026_07_21_test file resulted in 478895 samples instead of 480000
```

**解法**（`workflows/speech_to_text.py` L257~290）：

- 在 Step 3 呼叫 `vt.transcribe()` 前，檢查音訊格式
- 若非 WAV，用 `librosa.load(sr=48000)` 讀取 → `sf.write()` 寫入 temp WAV
- `finally` block 清理 temp 檔案

### 3. Module rename：`speech-to-text.py` → `speech_to_text.py`

Python module 路徑不支援連字號。改用標準 `import` 並 rename 檔案。

## 最終測試結果（2026-08-03）

完整 pipeline 成功：

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
- 結果：31 segments, 3 speakers, 13.9 秒處理時間

## Follow-up

- [ ] OVERLAP 片段的 TSE（Target Speaker Extraction）尚未實作
- [ ] 測試更多不同長度的音訊檔
- [ ] Breeze-ASR-26 需要啟動才能執行 STT（`serve/vllm/launch_BreezeASR26.sh`）
- [ ] JSON 下載按鈕：確認 SSH 前端預覽器的檔案預覽限制（已確認是檢視器問題，非程式 bug）

## References

- [workflows/speech_to_text.py](../../workflows/speech_to_text.py) — Main pipeline
- [workflows/config.yaml](../../workflows/config.yaml) — 設定檔
- [webuis/speech-to-text.py](../../webuis/speech-to-text.py) — Gradio WebUI（port 7861）
- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py) — Reference implementation
- [68_2026_08_03_agent_speech-to-text-webui-final-validation.md](./68_2026_08_03_agent_speech-to-text-webui-final-validation.md) — 最終驗證
- Commit [cd99e72](https://github.com/.../commit/cd99e72) — 修復 numba crash + WAV conversion