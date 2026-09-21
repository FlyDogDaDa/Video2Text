# n9bo-transcribe

實驗剪輯流程（`exp/N9boWvU-KkA`）的轉錄＋串接腳本。

## 做什麼

- 讀 `exp/N9boWvU-KkA/audio_parts.json` 取得 4 份音訊切分資訊（檔名 / offset / 時長）
- 依序（嚴格串行）將 `audio_part_0..3.wav` POST 到 ASR 伺服器
  `http://10.46.219.5:8750/v1/audio/transcriptions`
  - model：`OpenMOSS-Team/MOSS-Transcribe-Diarize`
  - `response_format=json`；不送自訂 prompt（用 server 端 default prompt）
- 以 regex 解析各份原始輸出 `[start][Sxx]text[end]` → segments
- 各份寫出 `transcript_part_N.json`（含原始簡體 `raw`）
- 各段 start/end 加上該份 `offset_s` → 影片絕對時間 → 依序合併寫出 `transcript_combined.json`

## 怎麼跑

```
cd /home/freespace/文件/Video2Text
exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/transcribe.py
```

## 依賴

- Python 3.10+、`httpx`（隔離 venv `exp/N9boWvU-KkA/.venv` 已裝）
- 前置輸入：`exp/N9boWvU-KkA/audio_part_0..3.wav`、`exp/N9boWvU-KkA/audio_parts.json`

## 注意

- 串行請求：vLLM build 有併發回應錯位風險（參 `webuis/moss-playground.py` 的 `SERIAL_LOCK` 教訓），不可併發
- 可續跑：`transcript_part_N.json` 已存在 → 跳過該份
- 單份 timeout 1800s；失敗重試最多 2 次；仍失敗則 exit 1（偏離信號，停止等裁決）
- segment end 超出該份時長 5s 以上或 start 為負 → log warning（時間戳異常信號）

## 實測（2026-08-26）

- 4 份全一次成功：part0=247 segs/150.4s、part1=197/142.9s、part2=233/149.6s、part3=286/175.1s；共 963 segs
