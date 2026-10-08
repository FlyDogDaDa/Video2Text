# 06 Agent transcribe-s2twp-affirmative-inventory 討論細節

## 背景

- 實驗剪輯流程（`exp/N9boWvU-KkA/`）：把 YouTube 影片 N9boWvU-KkA 中所有「肯定語氣」的句子精準剪出、串成短片。
- 本條目前狀態：步驟 0（環境）、FA 支線（日誌 03/04）、步驟 1（下載＋MKV 合流，日誌 05）已完成。
- 本條目涵蓋：步驟 2（音訊切分）、步驟 3（轉錄＋串接）、使用者中途改指令「轉錄完直接轉繁體」、步驟 4（肯定詞盤點，sub-agent 執行）。

## 步驟 2：音訊切分（決策記錄）

- 音訊來源：直接從 `download/N9boWvU-KkA_audio.webm`（原始 Opus 48kHz stereo，yt-dlp format 251）抽出；不用 composite.mkv，避免碰重封裝檔。
- 格式選擇：16kHz mono PCM s16le WAV（`audio_full.wav`，181MB，5667.015688s）。
  - 理由：ASR 模型訓練於 16kHz；PCM 解碼無損、切分樣本精確。
  - 偏離說明：原企劃檔名寫 m4a，但 Opus→AAC 屬二次壓縮，改用 WAV；已註記在 TODO。
- 切點計算：總時長 5667.015688 ÷ 4 = 1416.753922s；offsets = 0 / 1416.753922 / 2833.507844 / 4250.261766。
- ffmpeg 對 WAV 用 `-ss`＋`-c copy` 切分（PCM 無 keyframe 問題，樣本精確）。
- ffprobe 實測各段：part_0..2 = 1416.832s，part_3 = 1416.753938s。
  前 3 段比名義長約 78ms（seek/容器取整）→ 記為 uncertainty；timecode 映射一律以 `audio_parts.json` 名義值為準，各段 offset 對齊不受影響。
- 元數據：`exp/N9boWvU-KkA/audio_parts.json`（source、total_duration_s、每段 index/file/offset_s/end_s/duration_s）。

## 步驟 3：轉錄

- 參考 `webuis/moss-playground.py` 的請求格式：POST multipart 到 `http://10.46.219.5:8750/v1/audio/transcriptions`；
  model `OpenMOSS-Team/MOSS-Transcribe-Diarize`、`response_format=json`、不送 prompt（用 server 端 default prompt）。
- 設計決策：
  - 串行：vLLM build 有併發回應錯位風險（playground `SERIAL_LOCK` 教訓），嚴禁併發
  - 可重試：每份最多 3 次嘗試；可續跑：`transcript_part_N.json` 已存在即跳過
  - 出界檢查：seg.end 超出該份時長 5s 以上或 start<0 → log warning（偏離信號）
  - 串接：start/end 各加該份 offset_s，依 start 排序寫 combined
- 執行：nohup 背景跑（環境 tmux 不可用），輸出寫 `exp/N9boWvU-KkA/transcribe.log`。
- 結果：4 份全一次成功、無出界 warning。
  part0=247 segs/150.4s、part1=197/142.9s、part2=233/149.6s、part3=286/175.1s；共 963 segs → `transcript_combined.json`。

## 中途轉變（使用者指示）

- 原企劃：`transcript_combined.json` 保留原始簡體。
- 使用者改指令：「現在轉錄完直接轉繁體」，並要求把此轉變補進 TODO。
- 執行：技能 `chinese-conversion-for-files`（OpenCC s2twp，`uv run .agents/skills/tool-file-chinese-conversion/scripts/convert.py <file> --apply`）。
- 只轉 `transcript_combined.json`；各 `transcript_part_N.json` 的 `raw` 欄保留原始簡體，無資訊遺失。
- 同步更新 combined json 的 `note` 欄：標明 text 已轉繁體、原始簡體在 part raw 欄。

## 步驟 4：肯定詞盤點

- 使用者指示：開 sub-agent「直接讀原始文件」盤點，**不用程式白名單過濾**——
  白名單只能找到預先想到的詞，會漏掉實際出現的其他肯定用語。
- sub-agent 方法：分段讀完 963 段全文 → 依語義分類 → 唯讀命令驗證計數 → 回傳分級詞表。
- 主 agent 抽驗：
  - 發現 `grep` 搜尋工具不搜 `exp/`（gitignore 目錄被跳過）→ 改 Python `str.count`。
  - `沒錯`=20、`好嘞`=1 與回報一致；`OK` 字面計 9 vs 回報 7（口徑差：獨立語氣 vs 子串出現）。
- 結果分級：
  - 高置信：`對`(421 safe)、`對啊`(54)、`嗯`(118)、`沒錯`(20)、`OK`(7)、`確實`(5)、`好嘞`(1)
  - 待使用者決定：`是`(383)、`可以`(94)、`好`(~29)、`有`(~20)、`對吧`、`沒關係`(3)、`好的`(5，建議排除)
- 回報歸檔：`assets/n9bo-affirmative-word-inventory/affirmative-word-report.md`。

## 未決事項

- 最終肯定詞表待使用者確認（`是`、`可以` 若納入誤抓量大；`嗯` 屬 backchannel 未必等同同意）。
- 步驟 5 執行前需依 TODO 既定規則向使用者索取 Qwen3-ForcedAligner 的確切使用方式。

## 工具環境備註（本日觀察）

- `grep` 工具對 gitignore 的 `exp/` 無效；`create_directory` 對專案內深層新目錄報 "outside the project" → 一律改用 terminal `mkdir -p` / `cp`。
- `list_directory` 對 gitignore 目錄可能誤報空。
