---
created: 2026-08-27
author: agent
type: agent
tags: [fa-alignment, qwen3-forcedaligner, diagnosis, video2text]
---

# FA 預覽字幕堆疊根因：缺官方 fix_timestamp 後處理

## What

- 使用者回報長句預覽片 `p0_s173` 的逐字高亮字幕中段開始互相堆疊（預期是逐行「替換」）。
- 診斷：堆疊不是渲染 bug，是該段 FA 時間戳在重複詞群（unit 4–10）出現重疊／反轉區間，
  同一時刻多個 ASS 事件活躍，libass 垂直堆疊；截圖時刻恰好 3 個重疊 unit + baseline = 4 行。
- 全量影響：494 個肯定詞樣本中 11 個 span 反轉（80ms 一 bin），會影響步驟 6 的 clip 邊界。
- 研究官方 Qwen3-ASR 對齊器與 vLLM 範例後定位根因：官方在配對 start/end 前會對
  原始 timestamp 序列跑 `fix_timestamp`（LIS 非遞增多項式 + 異常段補整），
  本專案 `filter_align.py` 跳過此步、直接存 raw argmax。
- 使用者「token↔字元手算錯位」的假設被排除：官方中文單位切分規則（CJK 單字一個單位、
  連續字母數字一個單位、標點丟掉）與現有 `split_text_units` 一致，且官方不用 LLM BPE
  tokenizer 做單位對應，`/detokenize` 不需要。
- 修復計畫已核准：移植 `fix_timestamp` 後補處理既有 334 段（不重跑模型），修渲染 note bug，
  重渲染 p0_s173，重跑健檢。

## Why

- 步驟 6 剪輯需要精準的肯定詞時間戳；11 個反轉樣本會讓 clip 起訖偏 1 bin。
- 預覽片是唯一的肉眼檢核工具，堆疊讓中段無法檢視，必須先解決。
- 官方後處理就是為這類離群 bin 設計的（快語速、重複詞區域最集中），採用官方解法比
  自訂單調化或重跑模型都更省事、更可解釋。

## How

- 本條目僅診斷 + 研究 + 計畫核准，未改程式。
- 診斷動作：讀 `exp/N9boWvU-KkA/scripts/render_fa_preview.py`、dump `p0_s173` 的 units
  驗證區間重疊、統計 494 樣本中 11 個反轉。
- 研究動作：讀 `filter_align.py` 全量比對 vLLM 官方 online 範例；curl 伺服器 `/openapi.json`
  確認端點；fetch 模型卡與 Qwen3-ASR 原始碼（歸檔見 References）。
- 執行計畫（下一步，未動）：
  1. `exp/N9boWvU-KkA/scripts/fix_timestamps.py`：移植官方 `fix_timestamp`，
     由每段 2N 序列重構→修補→寫回 `filtered_aligned.json`（原值留 `*_raw`，
     執行前備份 `tmp/filtered_aligned_pre_fix.json`），重算 `word_matches` 與 `issues`
  2. 修 `render_fa_preview.py` note 行（`{u}` dict → `u['unit']`，補整單位加標註）
  3. 重渲染 p0_s173、重跑健檢（反轉/重疊應歸零），回報補整點數

## Follow-up

- [x] 執行上述 1–3 並回報健檢對照（2026-08-27，見 log 02：73→0、11→0、565→45）
- [x] 使用者目檢重渲染的預覽片，確認品質後再寫執行日誌（2026-08-27 已確認，見 log 02）
- [ ] 步驟 6：`scripts/edit_video.py` 從 composite.mkv 用 `-c copy` 切獨立 clips
      （注意：補整後可能出現零長或近零長 span，需最小時長保護）

## Uncertainty

- 官方 `fix_timestamp` 吃 2N+2 完整序列，我們由落檔 2N 重構；尾端異常段的補整
  與官方可能微幅不同（暫定：可接受，尾端單位的 clip 影響極小）。
- 補整值是插值/最近值重建，非模型測量值；補整後品質以預覽目檢與健檢為準。
- `chat_with_my_agent/2026_08_27/` 缺 00 主日誌檔（歸檔資料夾存在），
  成因未定（暫定：早先寫入失敗或被移走），本條起用 01 流水號。

## References

- [討論細節](references/01_agent_preview-stacking-root-cause.md)
- [官方對齊器原始碼歸檔](assets/fa-official-source/README.md)
- [vLLM token_classify 文件（Forced Alignment 範例）](https://docs.vllm.ai/en/latest/examples/pooling/token_classify/)
- [Qwen3-ForcedAligner-0.6B 模型卡](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B)
- [Qwen3-ASR 官方 repo](https://github.com/QwenLM/Qwen3-ASR)
