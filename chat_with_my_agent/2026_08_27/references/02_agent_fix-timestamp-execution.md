# fix_timestamp 執行與驗證——完整過程

## 背景

log 01 診斷出 `filtered_aligned.json` 中 334 段 FA 時間戳存在 73 個反轉單位、11 個反轉詞、565 個 issues。根因是 `filter_align.py` 跳過官方 `fix_timestamp` 後處理，直接存 raw argmax 結果。log 01 核准修復計畫後，本回合執行。

## 執行步驟

### 1. 撰寫 `fix_timestamps.py`

- 位置：`exp/N9boWvU-KkA/scripts/fix_timestamps.py`
- 功能：移植 Qwen3-ASR 官方 `fix_timestamp` 函數（LIS 非遞增多項式 + 異常段補整），對 `filtered_aligned.json` 中每段的 2N timestamp 序列執行修正。
- 寫入策略：
  - 修正前值存入 `start_s_raw` / `end_s_raw`
  - 修正後值寫入 `start_s` / `end_s`
  - 經插值/最近值重建的單位標 `fixed: true`
  - 段級 `meta.fix` 記錄 `method`、`source`、`applied_at`
- 執行前備份：`cp filtered_aligned.json tmp/filtered_aligned_pre_fix.json`

### 2. 執行修正

```bash
cd exp/N9boWvU-KkA && uv run scripts/fix_timestamps.py
```

- 執行時間：2026-08-27T15:51:33
- 處理 334 段、7681 單位

### 3. 修正前後健檢對照

| 指標 | 修正前 | 修正後 | 變化 |
|------|--------|--------|------|
| segments | 334 | 334 | — |
| units | 7681 | 7681 | — |
| reversed_units | 73 | **0** | −73 |
| zero_units | 295 | 654 | +359 |
| issues_total | 565 | **45** | −520 |
| reversed_words | 11 | **0** | −11 |
| zero_words | 17 | 43 | +26 |
| fixed_units | 0 | 606 | +606 |
| fixed_words | 0 | 42 | +42 |

完整數據：`assets/fix-timestamp-execution/health-check-comparison.json`

### 4. 殘留 45 issues 審計

45 個殘留 issues 的構成：
- **43 個零長詞**（start_s == end_s）：fix 對共享邊界的兩個相鄰單位同時壓到同一 bin，產生零長 span。這是 fix 的已知行為——當兩個 token 共享邊界 timestamp 時，非遞增約束會把其中一個壓到 0 長。
- **1 個零長單位「呃」**：單詞 span 被壓到 0。
- **1 個零長單位「裡」**：同上。

### 5. 零長 raw 審計（43 個）

對 43 個零長詞逐個查 raw 值：
- **33 個有可用 raw 窗口**：raw 值範圍 0.08–0.32s，非零長。零長是 fix 壓縮共享邊界時的人工產物，raw 值可用。
- **9 個 raw 也是反轉的**：fix 修正了反轉但產生零長，raw 值不可用。
- **1 個 raw 異常（1.44s）**：fix 修掉是對的，raw 值不可用。

### 6. 重渲染 p0_s173

- 修正 `render_fa_preview.py` 的 note bug：
  - `{u}` 應為 `u['unit']`（dict 而非字串）
  - 補整單位加「（補整）」標註
- 重編碼切 p0_s173（libx264 crf18，不受 keyframe 影響）
- 輸出：`output/2026-08-27_FA長句預覽_p0_s173.mp4`（4.8MB）
- **使用者目檢確認：時間戳正確，無堆疊**

## 關鍵決策

1. **不重跑模型**：fix_timestamp 是純後處理，由 2N 序列重構即可，不需再次呼叫 vLLM API。
2. **原值保留 `*_raw`**：方便後續審計與零長政策決策（步驟 6 時可選擇用 raw 或 fix 值）。
3. **`fixed: true` 標記**：標明哪些值不是模型直接測量，而是插值/最近值重建。
4. **備份至 `tmp/`**：gitignored 區域，不污染版本控制，但可供回滾。

## 邊距擴展問題

使用者問「邊距擴展是將開始結束點向外微微擴展後直接當作擷取依據嗎？」——是的。fix_timestamp 的異常段補整（interpolation/nearest-neighbor）本質上就是把反轉或零長 span 的 start/end 向外或向內微調到合理的相鄰 bin，使整條序列非遞增。這與「邊距擴展」的直覺一致：取一個略寬的窗口來覆蓋該詞的實際發音範圍。

## 待解決

- 43 個零長詞的 span 在步驟 6 切 clip 時如何處理（用 raw 窗口？fix 值 T±0.2s？）。這是步驟 6 的政策決策，未在本回合定案。
