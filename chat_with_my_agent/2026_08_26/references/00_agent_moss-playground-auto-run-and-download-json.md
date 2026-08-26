# 討論細節：MOSS Playground 上傳自動處理＋下載 JSON 按鈕

## 需求（使用者原話）

對 `webuis/moss-playground.py` 兩個功能新增：

1. 把「🚀 處理」按鈕取代掉，讓「上傳音訊」上傳成功的時候自動執行。
2. 在結尾添加一個下載 JSON 的按鈕，當處理完成，可以在最尾端按下載。

## 環境

- Gradio `6.22.0`（根 workspace `.venv`，Python 3.12；`webuis/.venv` 為歷史殘留，見日誌 78）
- 啟動：`uv run --project webuis webuis/moss-playground.py`

## 查證（依使用者指示優先查官方 docs，非原始碼）

1. [Gradio DownloadButton 官方 docs](https://gradio.app/docs/gradio/downloadbutton)
   - `value: str | Path | Callable | None`：接受**本機檔案路徑**或 URL
   - 作為輸出元件：handler 回傳 `str | Path` 檔案路徑即可
   - `interactive=False` → disabled 狀態
2. [Gradio File Access 官方 guide](https://gradio.app/guides/file-access)
   - prediction function 回傳的檔案路徑，若位於 `allowed_paths`、CWD、或 `tempfile.gettempdir()` 內，Gradio 會拷貝進 cache 並透過 `/gradio_api/file=` URL 提供
   - 結論：JSON 寫到 `tempdir` 子目錄即可，**不用加 `allowed_paths`、不用自訂 FastAPI route**
3. `gr.File` 的 `upload` 事件：上傳成功時觸發（Gradio 6.22 確認存在）——即「上傳成功自動執行」的鉤子

## 設計

- 事件綁定：`run_btn.click(...)` → `audio_input.upload(fn=on_run, inputs=[audio_input, hotwords_input], outputs=[raw_output, final_group, tw_output, json_output, download_btn, status_md])`（輸出 5 → 6 個）
- 下載按鈕：`gr.DownloadButton(label="💾 下載 JSON", value=None, interactive=False)`，放在 `status_md` 之後、整頁最末端
- 檔案：成功時寫 `tempdir/moss_playground_downloads/moss_<YYYYmmdd_HHMMSS>.json`，再 `gr.update(value=str(path), interactive=True)`
- 狀態遷移：處理中 → disabled；成功 → enabled＋指向該檔；失敗／清空全部 → `value=None, interactive=False`（避免指向已無對應輸出的舊檔）
- `on_clear_all` 輸出 7 → 8 個
- module docstring「頁面流程」與頁面頂端 Markdown 同步更新

## 順手修的既有 bug

`on_run` 的 guard 分支：

```python
if not path:
    yield ("", ..., "❌ 請先上傳音訊檔案")
# 原本這裡沒有 return，會繼續往下執行
```

即顯示「請先上傳音訊檔案」後仍會跑 `process(None, ...)` → `open(None)` 崩掉，UI 最後顯示「處理失敗」。已補 `return`。副作用：同時消除 diagnostics 兩個型別 error（`str | None` 傳入 `Path`／`process`）。

## 驗證

- `python -m py_compile webuis/moss-playground.py` 通過
- `make_ui()` 離線組裝成功（`make_ui OK: Blocks`，未啟動 server）
- Diagnostics：上述兩 error 消失；剩餘 warning 全為既有（opencc 無 stub、bare `dict` generic、Gradio 組件回傳值未使用等）

## 未驗證

- 瀏覽器端到端：上傳 → 自動處理 → 按下載（需 vLLM server 在跑）
- 下載回應的 content-disposition（attachment vs inline）

## 流程備忘

- 使用者指示：編輯數量較多時，直接整檔重寫一次套用多個編輯，而非逐小塊 `edit_file`
- 查證 API 行為時，優先查網路官方 docs 而非翻原始碼
