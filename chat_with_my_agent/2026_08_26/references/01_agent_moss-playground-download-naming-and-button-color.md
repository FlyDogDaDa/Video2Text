# 討論細節：下載檔名＋橘色下載按鈕

## 需求（使用者提出）

1. 下載檔名改用上傳音訊的「名稱＋transcript.json」，提示用 pathlib 處理。
   - 初版需求寫的是「名稱+transcript.json」，後經使用者澄清：`+` 指「有底線的串接」，
     範例為 `meeting.mp3` → `meeting_transcript.json`。
2. 下載按鈕改橘色。

## 過程

### 橘色按鈕的探索（走了點弯路）

- 先查 Gradio 官方 Button docs（gradio.app/docs/gradio/button）：`variant` 只有
  `primary / secondary / stop / huggingface`，沒有「橘色」選項；自訂顏色需
  `elem_classes`＋`css=`。
- 又去查本機 Gradio 6.22.0 預設主題：`button_primary_background_fill = *primary_500`
  （即跟隨主題主色，預設為藍），`stop` 變體為紅色（#ef4444）。另外發現 Gradio 6.0
  起 `theme` 參數從 `Blocks()` 移到 `launch()`。
- 使用者裁決：「沒那麼複雜，不用想太多，改 variant=primary 就是答案了」→
  不弄主題/CSS，直接用 `variant="primary"`。

### 檔名

- 舊：`moss_{time.strftime('%Y%m%d_%H%M%S')}.json`（時間戳，難以辨認來源）。
- 新：`DOWNLOAD_DIR / (Path(path).stem + "_transcript.json")`。
- 注意：`Path.with_suffix("transcript.json")` 會 ValueError（suffix 須以 `.` 開頭），
  所以用 `stem + "_transcript.json"` 字串串接。
- 實測：meeting.mp3 → meeting_transcript.json；interview_final.wav →
  interview_finaltranscript.json；v2.final.m4a → v2.finaltranscript.json。

## 最終 diff 摘要（webuis/moss-playground.py）

```diff
-                # 寫出 JSON 到 tempdir，供 DownloadButton 下載
-                filename = f"moss_{time.strftime('%Y%m%d_%H%M%S')}.json"
-                json_path = DOWNLOAD_DIR / filename
+                # 檔名＝上傳音訊名稱＋「_transcript.json」（如 meeting.mp3 → meeting_transcript.json）
+                json_path = DOWNLOAD_DIR / (Path(path).stem + "_transcript.json")
                 json_path.write_text(r["json_text"], encoding="utf-8")
```

```diff
         download_btn = gr.DownloadButton(
             label="💾 下載 JSON",
             value=None,
             interactive=False,
+            variant="primary",
         )
```

## 驗證

- `make_ui()` 離線組裝成功；pathlib 檔名行為實測；diagnostics 無新增問題。
- 使用者已在瀏覽器端到端實測：上傳 → 自動處理 → 下載成功。

## 副作用／提醒

- 同檔名音訊重複處理會覆蓋舊 JSON（時間戳版本會各自獨立）；目前視為可接受。
