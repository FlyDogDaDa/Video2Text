---
created: 2026-08-26
author: agent
type: agent
tags: [moss-playground, gradio, webui]
---

# MOSS Playground：下載 JSON 檔名與橘色下載按鈕

## What

`webuis/moss-playground.py` 兩處調整：

1. 下載檔名由 `moss_<YYYYmmdd_HHMMSS>.json` 改為「上傳音訊名稱＋_transcript.json」
   （例：`meeting.mp3` → `meeting_transcript.json`）
2. 「💾 下載 JSON」按鈕加 `variant="primary"`（橘色，置於頁面最尾端）

## Why

- 時間戳檔名難以辨認來源；用音訊檔名讓使用者一看就知道 JSON 是哪段音訊的產出
- 橘色讓下載動作在頁尾更醒目（使用者指定用 Gradio 預設 `variant="primary"`，
  不自訂 CSS／主題）

## How

- `json_path = DOWNLOAD_DIR / (Path(path).stem + "_transcript.json")`
  （`with_suffix("transcript.json")` 會 ValueError，故用 `stem` 字串拼接）
- `gr.DownloadButton(..., variant="primary")`
- 驗證：`make_ui()` 離線組裝成功；pathlib 檔名行為實測；使用者已瀏覽器實測
  「上傳 → 自動處理 → 下載」全通路可用

## Follow-up

- 無（使用者已確認可用）

## Uncertainty

- 同檔名音訊重複處理會覆蓋同名 JSON（舊的時間戳做法不會）；目前視為可接受，
  若需要保留歷史可再改成追加序号

## References

- [討論細節](references/01_agent_moss-playground-download-naming-and-button-color.md)
- [Gradio Button 官方 docs](https://gradio.app/docs/gradio/button)
