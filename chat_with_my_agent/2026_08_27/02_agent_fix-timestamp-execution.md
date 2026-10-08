---
created: 2026-08-27
author: agent
type: agent
tags: [fa-alignment, fix-timestamp, qwen3-forcedaligner, video2text]
---

# fix_timestamp 執行：反轉與重疊歸零，預覽目檢通過

## What

- 依 log 01 核准的計畫執行修復：`exp/N9boWvU-KkA/scripts/fix_timestamps.py`
  移植官方 `fix_timestamp`（LIS 非遞增 + 異常段補整），對 334 段、7681 單位全量修正。
- 健檢對照：反轉單位 73→0、反轉詞 11→0、issues 565→45；修補 606 單位、42 詞。
- 修 `render_fa_preview.py` 兩處 note bug（`{u}`→`u['unit']`、補整單位加「（補整）」標註），
  重渲染 `output/2026-08-27_FA長句預覽_p0_s173.mp4`。
- 使用者目檢確認：時間戳正確、無堆疊。

## Why

- log 01 診斷：堆疊根因是 `filter_align.py` 跳過官方 `fix_timestamp` 後處理，
  重複詞區域產出重疊／反轉區間，libass 因此垂直堆疊。
- 步驟 6 剪輯需要乾淨的 span，反轉詞會讓 clip 邊界錯 1 bin（80ms），必須先修。
- 採用官方後處理而非自訂單調化：與上游行為一致、可解釋、免重跑模型。

## How

- 執行：`cd exp/N9boWvU-KkA && uv run scripts/fix_timestamps.py`（2026-08-27T15:51:33）。
- 寫入策略：修正前值存 `start_s_raw`/`end_s_raw`，修正後值寫回 `start_s`/`end_s`，
  經插值重建的單位標 `fixed: true`，段級 `meta.fix` 記錄 method/source/applied_at。
- 執行前備份 `tmp/filtered_aligned_pre_fix.json`（exp/ 下，不入 git）。
- 重渲染 p0_s173 用重編碼切片（libx264 crf18），不受 keyframe 限制，音畫同步可驗證。

## Follow-up

- [ ] 步驟 6 定案切片策略後，處理殘留 43 個零長「對」詞（詳見 log 04 審計：
      33 個可用 raw 窗口、9 個 raw 反轉、1 個 raw 異常）
- [x] 使用者目檢重渲染預覽片（已確認時間戳正確）

## Uncertainty

- 尾端異常段的補整由落檔 2N 序列重構，與官方吃完整 2N+2 序列可能有微幅差異，暫定可接受。
- 補整值是插值/最近值重建而非模型測量值；目前以健檢與目檢為準。

## References

- [討論細節](references/02_agent_fix-timestamp-execution.md)
- [腳本歸檔](scripts/fix-timestamp-execution/)（fix_timestamps.py、render_fa_preview.py 修後版）
- [健檢前後對照](assets/fix-timestamp-execution/health-check-comparison.json)
- [預覽片](../../exp/N9boWvU-KkA/output/2026-08-27_FA長句預覽_p0_s173.mp4)（exp/ 下，不入 git）
