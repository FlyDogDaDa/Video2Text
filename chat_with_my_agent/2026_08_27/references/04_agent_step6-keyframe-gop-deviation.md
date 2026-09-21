# 步驟 6 keyframe GOP 偏離調查與決策空間

## 背景

TODO.md 步驟 6 原假設 `-c copy` 模式精度「可能差 0.1~0.5 秒」。本回合以實際量測挑戰該假設。

## 量測 1：Keyframe GOP

- 方法：`ffprobe -v error -select_streams v:0 -show_packets -show_entries packet=pts_time,flags -of csv exp/N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv`
- 結果：全片共 940 個 keyframe（K flag），間隔**固定 6.0 秒**。
- 結論：GOP 遠大於 TODO 假設的 0.1–0.5s。`-c copy` 切片的起點必然拉回到前一個 keyframe，lead-in 最壞 6s、平均 3s。

## 量測 2：`-c copy` 試切

- 指令：`ffmpeg -ss 675.63 -i N9boWvU-KkA/download/N9boWvU-KkA_composite.mkv -t 0.24 -c copy exp/N9boWvU-KkA/tmp/test_clip_copy.mkv`
- 結果（ffprobe 回讀）：
  - 容器時長 3.9s
  - 影片 117 幀，first_pts 0.0，last_pts 3.867s
  - 音訊 194 幀，first_pts 0.008s，last_pts 3.861s
  - 起點 675.63 被拉回 672.0（前一個 keyframe），lead-in = 3.63s
  - 音畫互相同步（相對偏移 < 8ms）
  - 目標 0.24s 內容在影片最尾
- 證據檔：`assets/step6-keyframe-gop/test-clip-copy-report.json`

## 量測 3：零長 raw 審計

fix 後 43 個零長「對」詞，逐個比對 `start_s_raw`/`end_s_raw`：

| 分組 | 數量 | 說明 |
|------|------|------|
| raw 有可用窗口（0.08–0.32s） | 33 | 零長是 fix 壓共享邊界的人工產物；raw 可用 |
| raw 也是反轉（end < start） | 9 | raw 不可用 |
| raw 異常（1.44s） | 1 | 離群值；fix 修掉是對的 |

→ 可從 raw 取回 33/43；其餘 10 需 fallback 策略（暫定 T ± 0.2s 邊距）。

## 偏離定性

TODO 假設 0.1–0.5s 偏差基於「keyframe 密集（~2s 以內）」的常見影片。本片 GOP 6.0s 使 `-c copy` 起點不精確達 3.63s（本次）到 6.0s（最壞）。這是**重大偏離**，影響所有 334 個 clip 的起點精度。

## 選項分析

### 選項 A：維持 `-c copy`

- 優點：零重編碼成本；音畫同步由容器保證；速度極快（334 片秒級完成）。
- 缺點：
  - 每片前多 0–6s 不相關內容（lead-in 到前一個 keyframe）
  - 起點不精確（最壞偏差 6s），不符合「精準剪出」目標
  - 零長 span（10 個無 raw 可用）需特別處理
  - 剪輯軟體導入時需人工 trim 或自動 trim 前段
  - 檔案體積偏大（AV1 6s 片段 vs 0.24s 目標）

### 選項 B：逐片重編碼（agent 推薦）

- 方法：`ffmpeg -ss <start> -i composite.mkv -t <duration> -c:v libx264 -crf 18 -c:a aac clip.mkv`
- 優點：
  - 幀精確起點（-ss 在 input 前可精確到 1/30s）
  - 檔案小（只含目標內容）
  - 零長 span 可用 T±0.2s 策略處理
  - 剪輯軟體導入即精確，不需後處理
- 缺點：
  - 334 片重編碼（AV1 解碼 → H.264 編碼），估計 5–15 分鐘
  - 有微小壓縮損耗（crf18 幾乎不可見）
  - 需確認剪輯軟體支援 H.264（幾乎全支援）

### 選項 C：混合策略

- 起點精確需求高（短片段 < 2s）→ 重編碼
- 起點精確需求低（長片段 > 5s）→ `-c copy` 並 trim
- 複雜度高，不推薦

## 暫定建議

**選項 B**：一致性最佳，334 片統一重編碼，無須逐片判斷策略。crf18 品質對剪輯用途充足。
若使用者對時間敏感（不想等），可先跑前 10 片驗證同步後再全量。

## 待決

- 使用者尚未定案 A/B/C。定案後方可寫 `edit_video.py` 並執行步驟 6。
