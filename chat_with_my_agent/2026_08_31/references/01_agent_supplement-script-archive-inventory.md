# References：scripts/ 指令碼歸檔盤點詳表（2026-08-31）

## 比對方法

```bash
# 現行 vs 歸檔逐檔 diff（略去路徑字首）
diff exp/N9boWvU-KkA/scripts/{檔} chat_with_my_agent/{日}/scripts/{topic}/{檔}
# 日誌提及檢索（排除歸檔目錄本身）
grep -rl "{檔名}" chat_with_my_agent/2026_08_2{6,7} chat_with_my_agent/2026_08_31 \
  | grep -v '/scripts/'
```

## 盤點詳表（12 檔）

| 現行檔 | 修改時間 | 歸檔位置 | 日誌提及 | 判定 |
|---|---|---|---|---|
| `test_fa.py` | 08-26 19:29 | `2026_08_26/fa-pooling-test/` | 08-26 log 03/04 | ✅ 同檔 |
| `asr_crosscheck.py` | 08-26 19:57 | `2026_08_26/fa-pooling-test/` | 08-26 log 04 | ✅ 同檔 |
| `transcribe.py` | 08-26 22:27 | `2026_08_26/n9bo-transcribe/` | 08-26 log 06 | ✅ 同檔 |
| `download_streams.sh` | 08-26 21:22 | `2026_08_26/download-streams/` | 08-26 log 05 | ✅ 同檔 |
| `download_yt.sh` | 08-26 20:44 | — | — | ⚠️ 遺漏 → 本次補檔 |
| `filter_align.py` | 08-27 10:52 | `2026_08_26/n9bo-filter-align/` ＋ `2026_08_27/fa-tokenization-verify/` | 08-26 log 04/06、08-27 log 01/03 | ✅ 同檔 |
| `inspect_words.py` | 08-27 10:23 | — | — | ⚠️ 遺漏 → 本次補檔 |
| `check_part_starts.py` | 08-27 12:14 | `2026_08_27/check-part-starts/` | — | ⚠️ 已歸檔、無正文 → 本檔補紀錄 |
| `fix_timestamps.py` | 08-27 15:51 | `2026_08_27/fix-timestamp-execution/` | 08-27 log 01/02 | ✅ 同檔（使用者疑點的正面答案：有紀錄） |
| `render_fa_preview.py` | 08-27 15:59 | `2026_08_27/fix-timestamp-execution/` ＋ `render-fa-preview/` | 08-27 log 01/02 | ✅ 同檔 |
| `verify_tokenization.py` | 08-27 16:58 | `2026_08_27/fa-tokenization-verify/` | 08-27 log 03 | ✅ 同檔 |
| `edit_video.py` | 08-31 10:10 | `2026_08_27/step6-edit-video/`（舊版） | 08-27 log 05、08-31 log 00 | ✅ DIFF ＝ log 00 改裝，待完成後歸檔新版 |

## 三隻遺漏指令碼功能細節

### `inspect_words.py`

肯定詞上下文分析：統計 `對/沒錯/確實` 在 `transcript_combined.json` 中的前後 3
字分佈（`Counter`），用於設計 `filter_align.py` 的過濾 regex——特別是「對」的
複合詞排除清單（對不起、面對、相對、絕對、對吧…）。屬一次性分析工具，輸出僅
stdout。時間點（08-27 10:23）落在 08-26 log 06（盤點）與 log 03 之前的過濾設計期。

### `check_part_starts.py`

量測 `audio_parts.json` 各 part 檔相對 `audio_full.wav` 的實際起點偏差：取 part
前 1s 樣本，於名義 offset ±100ms 內以 1ms 步距滑動算 L2 距離，argmin 為實際起點，
並標記是否 bit-exact。純標準庫、唯讀。用於確認音訊切分無起點漂移。已歸檔於
`2026_08_27/scripts/check-part-starts/` 但當時未寫正文日誌。

### `download_yt.sh`

最早的單檔 `yt_dlp -f "bv*+ba/b"` 下載嘗試（`--js-runtimes node`）。後因 YouTube
AV1/Opus 分離串需求改用 `download_streams.sh`（08-26 log 05 記錄），本指令碼退役。

## `edit_video.py` DIFF 驗證

`diff` 共 119 行差異，新增符號僅：`ENCODERS`、`build_clips`、`_ffmpeg_cmd`、
`run_cuts` 簽名擴充、CLI `--encoder/--outdir/--workers/--retries`——與 log 00
改裝設計一一對應，無其他未記錄改動。
