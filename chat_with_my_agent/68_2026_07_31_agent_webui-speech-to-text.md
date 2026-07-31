---
created: 2026-07-31
author: Agent
type: agent
status: final
tags: [webui, gradio, speech-to-text, speaker-management]
---

# WebUI — Speech-to-Text Gradio 介面

## What

建立 Gradio WebUI（`webuis/speech-to-text.py`），提供瀏覽器介面的 Speech-to-Text 功能：

- **轉錄 Tab**：上傳音訊 → 設定參數 → 執行 pipeline → 即時顯示歷程 → 下載 JSON
- **Speaker 管理 Tab**：上傳、改名、刪除 speaker 參考音訊檔案（`test-audio/speaker-ref/`）

Server 跑在 `0.0.0.0:7861`，任何人可連入。

## Why

之前 `workflows/speech-to-text.py` 只能從 CLI 執行，需要手動拼指令、改參數。WebUI 讓非技術使用者也能：

- 上傳音訊檔案即可轉錄
- 管理 speaker 參考檔案不需要手動操作檔案系統
- 即時看到處理進度與結果

## How

### 檔案結構

```
webuis/
├── __init__.py          # 空包標記
└── speech-to-text.py    # Gradio WebUI（~560 行）
```

### 關鍵設計決策

**直接 import `run_pipeline()`**
- 透過 `importlib.util.spec_from_file_location` 動態載入 `workflows/speech-to-text.py`
- 原因：副檔名有連字號（`speech-to-text.py`），不能用一般 `import`
- 同場處理 voicetag circular import 問題（預先載入 site-packages 版本到 `sys.modules`）

**Background 執行 + 即時 log 更新**
- `on_run()` 在 Gradio event handler 中啟動 `threading.Thread` 執行 pipeline
- 透過 `builtins.print` 重新導向捕捉 stdout 輸出
- 每 0.5 秒檢查 thread 狀態，即時更新 `gr.Textbox`
- 完成後自動啟用 `gr.DownloadButton`

**Speaker 管理**
- `list_speakers()`：掃描目錄，回傳 DataFrame（名稱、檔名、大小、路徑）
- `upload_speaker()`：支援多檔案上傳，自動避同名衝突
- `delete_speaker()`：依 speaker 名稱刪除所有同名音訊檔
- `rename_speaker()`：批量改名（保留副檔名）

### 啟動指令

```bash
VIRTUAL_ENV=serve/voicetag/.venv \
PYTHONPATH=. \
serve/voicetag/.venv/bin/python webuis/speech-to-text.py
```

### 依賴

- `gradio`（已透過 `uv pip install` 裝入 voicetag venv）
- `yaml`（pyyaml，voicetag venv 已包含）
- 所有 voicetag / torch / resemblyzer 等依賴（來自 voicetag venv）

### Gradio 6.0 API 調整

- `theme` 從 `Blocks()` 移到 `launch()` 參數
- `Textbox.show_copy_button` 已移除（6.0 不支援）
- `Dataframe.wrap_table` 已移除（6.0 不支援）

## Follow-up

- **實際測試**：需透過瀏覽器上傳真實音訊檔案測試完整流程
- **進度指示器**：目前用 log text 顯示，未來可加 `gr.Progress()` 或 progress bar
- **多檔案上傳**：Speaker 管理支援多檔案上傳，但轉錄 Tab 僅單檔案
- **設定持久化**：目前參數都是臨時輸入，未來可加入設定記憶/存檔
- **stt_provider / stt_api_key / stt_language**：目前用 gr.State 硬編碼預設值，應改為可編輯欄位

## References

- [workflows/speech-to-text.py](../../workflows/speech-to-text.py) — 主工作流程
- [workflows/config.yaml](../../workflows/config.yaml) — 設定檔
- [webuis/speech-to-text.py](../../webuis/speech-to-text.py) — WebUI 本體