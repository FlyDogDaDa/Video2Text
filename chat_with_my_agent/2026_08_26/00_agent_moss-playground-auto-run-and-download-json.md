---
created: 2026-08-26
author: agent
type: agent
tags: [moss-playground, gradio, webui]
---

# MOSS Playground：上傳自動處理＋下載 JSON 按鈕

## What

修改 `webuis/moss-playground.py` 兩個功能：

1. 移除「🚀 處理」按鈕，改由音訊**上傳成功時自動執行**處理管線（`audio_input.upload` 事件取代 `run_btn.click`）
2. 頁面最尾端新增「💾 下載 JSON」`DownloadButton`，處理完成後啟用，點擊下載 segments JSON

順手修一個既有 bug：`on_run` 的 guard 分支沒有 `return`，會繼續執行 `process(None)` 崩掉。

## Why

- 上傳後自動處理省掉一個互動步驟，處理按鈕多餘
- 下載按鈕放最尾端，符合「看完結果再下載」的流程
- Gradio 官方支援：`DownloadButton` 的 `value` 接受本機檔案路徑，且 `tempfile.gettempdir()` 下的檔案會被自動收進 cache、經 `/file=` URL 提供——不用自訂 route、不用加 `allowed_paths`

## How

- 事件：`audio_input.upload(fn=on_run, ...)`，`on_run` 輸出 5→6（新增 `download_btn`）
- 下載：成功時寫 `tempdir/moss_playground_downloads/moss_<YYYYmmdd_HHMMSS>.json`，`gr.update(value=str(path), interactive=True)`；失敗／清空時重置 `value=None, interactive=False`
- `on_clear_all` 輸出 7→8；docstring 與頁面頂端文案同步更新
- 驗證：`py_compile` 通過、`make_ui()` 組裝成功；diagnostics 兩個型別 error 隨 `return` 修復消失（剩餘 warning 皆為既有）

## Follow-up

- 瀏覽器實測：上傳 → 自動處理 → 按下載（需 vLLM 端在跑）
- 確認下載是 attachment（直接存檔）還是 inline（開 JSON 頁面）

## Uncertainty

- 下載回應的 content-disposition 未在瀏覽器驗證；最壞情況是点开 JSON 頁面而非直接存檔（頁面可另存），待實測

## References

- [討論細節](references/00_agent_moss-playground-auto-run-and-download-json.md)
- [Gradio DownloadButton 官方 docs](https://gradio.app/docs/gradio/downloadbutton)
- [Gradio File Access 官方 guide](https://gradio.app/guides/file-access)
- [78 MOSS Playground（前情）](../78_2026_08_18_agent_moss-transcribe-diarize-playground.md)
