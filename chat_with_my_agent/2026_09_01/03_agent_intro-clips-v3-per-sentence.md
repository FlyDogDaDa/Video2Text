---
created: 2026-09-01
author: agent
type: agent
tags: [step7, intro-clips, edit-video, av1, mkv, libsvtav1, per-sentence, video2text]
---

# 片尾身份切片 v3：逐句獨立切片（14 片），指令碼化

## What

- 使用者澄清 v2 理解有誤：要的是**每一句各切成一個 clip**（14 個獨立檔），
  而非 4 個連續 run 合併片。
- 新指令碼 `scripts/cut_intro_sentences.py`：從 `transcript_combined.json` 以
  原文逐字匹配抓出 14 句 → 逐句切片（MKV＋libsvtav1＋AAC）→ ffprobe 驗證。
- 產出覆寫 `clips_intro/`（先清舊 4 片），重打包覆蓋 `clips_intro.zip`。

## Why

- 逐句交付讓使用者在 DaVinci Resolve 自由排列片尾順序。
- 短句「對」在全文出現多次，逐字匹配會有歧義：改用**時間順序遊標匹配**——
  依清單順序（清單本身即時間序）從上一句之後找第一筆完全相符者，天然消歧。
- 前一句緊貼下一句（間隙常僅 0.03s），對稱 0.2s padding 會擦到相鄰句：
  每邊 padding = min(0.15s, 與相鄰段間隙 × 0.4)，護欄式收斂。
- 14 片各自獨立 → ProcessPoolExecutor（max_workers=8）平行切片。

## How

- 匹配不到或遊標順序矛盾 → 指令碼直接報錯中止，不輸半成品。
- 切片模板同 log 01/02（`-ss` 前置、libsvtav1 preset5 crf24、AAC 192k、
  `-avoid_negative_ts make_zero`）。
- 檔名 `clip_NN_slug.mkv`（NN=01–14 依使用者清單順序）：
  01 date_weekday、02 time_evening、03 channel_name、04 interview_show、
  05 book_title、06 japanese_edition、07 chinese_edition、08 invited_editor、
  09 chat_together、10 invite_self_intro、11 self_intro_name、
  12 editor_of_book、13 right_dui、14 pretty_nice。
- 驗證：ffprobe 逐片 v=av1/a=aac＋時長對照。
- 打包：`zip -q -j clips_intro.zip clips_intro/*.mkv`（覆蓋）。

## Execution Results

- 排錯過程：ProcessPoolExecutor 兩處修正——lambda 不可 pickle → 改模組級
  `_work()`；formatter 重排後 `cut()` 簽名與 hit _tuple_ 不一致 → 定位階段
  預先算好 gap_before/gap_after，`cut(slug, seg, gb, ga)` 只收純值。
- 切片：**14/14 全過**，匹配→切片→驗證一氣呵成（workers=8）。
- 護欄式 padding 生效例：clip_05 頭僅留 0.048s（前句 382.120 是互動提醒尾）；
  clip_10 尾僅留 0.012s（音量測試 403.910 起）；clip_13 「對」前後各留 ≊0.05s。
- ffprobe 逐片：全部 v=av1／a=aac，時長偏差均 ≤0.06s 閾值內。
- 打包：舊 zip 先刪，**`clips_intro.zip`** 覆蓋為 19.4 MB（14 片）。
- 指令碼已歸檔至本日誌 `scripts/cut_intro_sentences.py`。完成於 09-01 16:25。

## Follow-up

- [x] 14/14 切片＋ffprobe 驗證（全 av1＋aac，偏差 ≤0.06s）
- [x] 覆蓋 `clips_intro.zip`（19.4 MB）
- [x] 歸檔指令碼＋回填結果＋轉繁體複查

## Uncertainty

- 極短句「對」（0.48s）與「蠻棒的」（1.16s）護欄後實際含語音長度很短，
  Resolve 上可能需要手動補齊呼吸空間。

## References

- v2（run 合併版，已被本版取代）：`02_agent_intro-clips-v2-sentence-precise.md`
- 指令碼：`exp/N9boWvU-KkA/scripts/cut_intro_sentences.py`
