---
created: 2026-08-31
author: agent
type: agent
tags: [日誌補寫, 指令碼盤點, video2text, N9boWvU-KkA]
---

# 補寫日誌：scripts/ 指令碼歸檔盤點與三隻無日誌指令碼補檔

## What

- 使用者懷疑「`fix_timestamps.py` 與其他指令碼已有進度是日誌遺漏的」。逐檔比對
  `exp/N9boWvU-KkA/scripts/`（12 檔）與 `chat_with_my_agent/` 各日誌的歸檔與提及，
  結論：**核心進度沒有遺漏**，但有 3 隻輔助指令碼從未被日誌提及（其中 1 隻連歸檔也沒有）。
- 補檔：`inspect_words.py`、`download_yt.sh` 歸檔至本資料夾 `scripts/`。

## Why

- 比對結果（詳表見 references）：11/12 檔與歸檔版**逐字元相同**；唯一 DIFF 是
  `edit_video.py`，差異全部來自本次 log 00 的 av1_nvenc 改裝（`--encoder`／
  `--outdir`／`--workers`／`--retries` 與 `ENCODERS`），已有 log 00 追蹤、待全量
  完成後歸檔，非遺漏。
- 使用者之所以覺得「fix_timestamps 的進度不在日誌裡」，實際原因：它由
  08-27 log 01（根因）＋ log 02（執行與目檢）完整涵蓋，且已歸檔於
  `2026_08_27/scripts/fix-timestamp-execution/`——是**記錄在案**而非遺漏。
- 真正的遺漏只有三隻輔助指令碼（見 How），屬分析工具、不影響產出正確性。

## How

- 盤點方法：`diff` 逐一比對現行檔 vs 歸檔檔；`grep -rl` 各指令碼名於日誌主檔與
  references（排除 `scripts/` 目錄本身）。
- 遺漏清單與判定：
  1. `inspect_words.py`（08-27 10:23）：肯定詞上下文分析（對/沒錯/確實的前後 3
     字統計），用於決定過濾 regex 的複合詞排除（對不起/面對/絕對…）。無日誌、
     無歸檔 → 補歸檔，功能記於本檔 references。
  2. `check_part_starts.py`（08-27 12:14）：量測音訊 part 檔相對 `audio_full.wav`
     的起點偏差（1s 視窗、±100ms、1ms 步距 L2）。**已歸檔**
     （`2026_08_27/scripts/check-part-starts/`）但無任何日誌正文提及 → 補紀錄。
  3. `download_yt.sh`（08-26 20:44）：最早單檔 `yt_dlp` 下載嘗試（後被
     `download_streams.sh` 分流下載取代）。無日誌、無歸檔 → 補歸檔。
- `verify_tokenization.py`（log 03）、`render_fa_preview.py`（log 01/02）、
  `filter_align.py`（08-26 log 06 起）、`edit_video.py`（08-27 log 05）皆有紀錄。

## Execution Results

- 比對：11 檔 SAME；`edit_video.py` DIFF ＝ log 00 改裝內容（119 行差異，全部
  落在 encoder/outdir/workers/retries 相關函式與 CLI），確認無其他未記錄改動。
- 已補歸檔：`inspect_words.py`、`download_yt.sh` →
  `chat_with_my_agent/2026_08_31/scripts/supplement-script-archive-inventory/`。

## Follow-up

- [x] 盤點 12 檔現況 vs 歸檔
- [x] 補歸檔 `inspect_words.py`、`download_yt.sh`
- [ ] （沿用 log 00）序列全量重產 423 片後，改裝版 `edit_video.py` 與
      `clips_mp4_manifest.json` 歸檔至 `2026_08_31/`

## Uncertainty

- 無。三隻指令碼的功能描述取自指令碼 docstring 與時間線推斷；`check_part_starts.py`
  的量測數值結果未見於任何輸出檔，僅能記錄其用途。

## References

- [盤點詳表與三隻指令碼功能細節](references/01_agent_supplement-script-archive-inventory.md)
- [fix_timestamps 的既有紀錄（08-27 log 02）](../2026_08_27/02_agent_fix-timestamp-execution.md)
- [AV1 重產改裝紀錄（本日 log 00）](00_agent_step6-av1-mp4-reclip.md)
