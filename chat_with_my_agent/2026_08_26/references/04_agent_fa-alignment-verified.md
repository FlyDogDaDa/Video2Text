# 討論細節：FA 對齊跑通 + 字幕預覽驗證（04）

## 脈絡

接續 03 條目：03 卡在 FA 伺服器未開 `--trust-request-chat-template`，
預設模板丟掉 text part（`/tokenize` 只有 42 tokens 全是模板+audio_pad，無
`<timestamp>`），對齊結果不可信。

## 本次討論與決策

1. **使用者以 `--trust-request-chat-template` 重啟 FA 伺服器**（選項 1）。
2. 照 vLLM 官方 online 範例
   （`examples/pooling/token_classify/forced_alignment_online.py`）改
   `test_fa.py`：`/pooling` 與 `/tokenize` 都帶
   `chat_template="{{ messages[0]['content'] }}"`（raw-content 模板，讓伺服器
   直接把 messages[0] 的 content 當 prompt，不套預設模板）。
   同時加入 `usage.prompt_tokens` 與 predictions 長度的交叉驗證。
3. **先用 `output/是我用AI跑出來的.opus`（1.532s，緊貼剪輯）測試**：
   - 46 tokens，audio_pad 在 index 1，`audio_token_shift=0`，text part 正常存在
   - 對齊：是 0.000–0.160、我 0.160–0.320、用 0.320–0.480、AI 0.480–0.800、
     跑 0.800–0.880、出 0.960–1.120、來 1.120–1.280、的 1.360–1.440
   - sanity check OK（單調、在音訊長度內）
4. **產黑底白字字幕預覽**：`exp/N9boWvU-KkA/subs_preview.ass`
   （1920x1080、Noto Sans CJK TC 80pt、Alignment=2 置中底端、累積式逐字顯示），
   ffmpeg `color=black` + ASS + opus 音訊 → `output/2026-08-26_FA對齊字幕預覽.mp4`。
5. **使用者觀察到「攤開」特性**：音訊頭尾有留空（剪輯不夠貼合）時，靠近該端的
   token 預測會被均勻攤開。對比：aac（前導靜音 0.2s）→「是」0.160–0.400 被撐寬；
   opus（無前導靜音）→「是」0.000–0.160 釘在開頭。判斷為訓練特性（訓練資料都是
   貼合語音剪輯），非 bug。對主流程的啟示：切段送對齊時 padding 要小
   （~100–200ms）。
6. **使用者初判「時機完全沒對到」，要求用簡體輸入再跑一次**：
   `--text "是我用AI跑出来的。"` → 時間戳與繁體版**完全一致**
   （只有 来/來 token ID 不同：36407 vs 99498），排除簡繁問題。
7. **客觀交叉驗證**：
   - `ffmpeg silencedetect`（-30dB）：opus 0.0s 起即語音、1.4617s 靜音起
     → 與 FA「是」0.000 起、「的」1.440 止吻合
   - MOSS ASR（`asr_crosscheck.py`，8750）獨立轉錄：`[0.00][S01]是我用AI跑出来的。[1.50]`
     整句 0.00–1.50，與 FA 吻合
8. **最終結論（使用者逐幀確認）**：偏移是 VLC 播放器音畫分離造成的，
   用剪輯程式逐幀檢查，繁體/簡體兩版對齊**皆準確**。FA 支線驗證通過。

## 踩過的坑

- 中文字檔名在 terminal 指令中會被簡繁轉換 → input 檔名用 `output/*.opus`
  glob 避開；輸出檔名寫入不受影響。
- 第一次產出的 mp4 用錯音源（aac 2.017s），重產後 ffprobe 驗證：
  video 1.500s / aac 1.525s（opus 音訊）才正確。

## 技術重點

- 對齊公式：`pred_idx = i + audio_token_shift`（僅當 `i > audio_pad_index`）；
  本例 shift=0（raw-content 模板下 /tokenize 已反映 audio pad 展開）。
- 時間戳 = `argmax(5000 bins) × 80ms`（`timestamp_token_id=151705`、
  `timestamp_segment_time=80`、`classify_num=5000`）。
