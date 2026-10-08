# 預覽片字幕堆疊根因診斷與官方 FA 流程研究

日期：2026-08-27
發起：human（回報預覽片問題）→ agent（診斷與研究）
狀態：根因已定位，修復計畫已核准，待執行

## 1. 問題回報

使用者用 VLC 檢查 `output/2026-08-27_FA長句預覽_p0_s173.mp4`（p0_s173，8.68s，30 units，
chunk 990.56+8.68s，ASR 990.76→999.04s），回報：「開頭是好的，後面幾個逐字稿字幕就開始互相堆疊了」，
預期行為應為「有 highlight、有替換」（同一時刻只顯示一個高亮行）。

## 2. Agent 第一輪診斷

### 2.1 渲染腳本行為（`scripts/render_fa_preview.py`）

- 一個「baseline」ASS 事件：全句白字 + 資訊小字，`[0, clip_dur]` 全程顯示。
- 每個 unit 一個 ASS 事件：全句 + 該 unit 黃色高亮 + 小字 `FA: {start}→{end}s`，
  顯示區間為該 unit 的 `[start_s, end_s]`。
- 全部事件同位置（同 Style、同 MarginV）。libass 對「同時活躍」的多個事件會垂直堆疊顯示。

結論：若 FA 時間區間乾淨互不重疊，任一時刻只有一個 unit 事件活躍 → 視覺上就是
「baseline + 一個高亮行」的替換效果。堆疊 = 有多個 unit 事件同時活躍。

### 2.2 p0_s173 的 FA 數據（`filtered_aligned.json`）

unit 4–10 的 FA 絕對時間（秒）：

| unit | start | end | 狀態 |
|---|---|---|---|
| 4 | 991.84 | 992.08 | 正常 |
| 5 | 992.48 | 992.08 | 反轉 |
| 6 | 992.08 | 993.44 | 重疊 |
| 7 | 994.24 | 992.48 | 反轉 |
| 8 | 992.48 | 993.44 | 重疊 |
| 9 | 994.24 | 993.12 | 反轉 |
| 10 | 993.04 | 993.44 | 重疊 |

截圖時刻（VLC ≈00:02，clip 起點 990.16 → 絕對 ≈992.3s）：u6、u8、u10 三個重疊區間
同時涵蓋該時刻 → 3 個 unit 事件 + 1 個 baseline = 畫面 4 行，與截圖完全吻合。

### 2.3 次要 bug（渲染腳本）

`note = f"FA: {u} ..."` 中 `u` 是 dict，note 行印的是 dict 而非單字（應為 `u['unit']`）。

### 2.4 對最終產物的影響

全量 494 個肯定詞樣本（`word_matches`）中 **11 個 span 反轉**（start > end，差 80ms 一個 bin），
p0_s173 的「對」（991.04→990.96）就是其中之一 → 步驟 6 的 clip 邊界會偏 1 bin。

### 2.5 當時給使用者的選項

- A：修渲染器（顯示層單調化）+ 重渲染
- B：短窗口重對齊（每詞 ±2s 音訊 + ±10 字，batch=4，約 3–5 分，健檢不合格回退）
- Agent 建議：A → B

## 3. 使用者反饋與方向

使用者觀察：「撇除掉時間戳能出現反轉、重疊等問題，獨立單看 Token 其實時機都還算準確。」
並提出假設：token↔字元的對應若不是用真正的 tokenizer/detokenizer 取得而是手算，可能就是失準原因；
建議研究流程：`tokenizer->IDs->FA->時間pool->classify_num+de-tokenizer(IDs)->時間戳`，
「遵循 FA 模型的分詞算法就好」。
指定：直接走 API（伺服器已有 /tokenize、/detokenize、/pooling），不在本地裝模型環境。
參考：vLLM docs `token_classify` 頁的 Forced Alignment Online 範例。

## 4. Agent 研究結果

### 4.1 現有 `filter_align.py` 與官方 online 範例逐項比對

| 環節 | 官方 online 範例 | filter_align.py | 一致？ |
|---|---|---|---|
| prompt 組裝 | `prefix + "<timestamp><timestamp>".join(words) + "<timestamp><timestamp>"` | 相同 | ✅ |
| tokenize | 本地 `AutoTokenizer`（`add_special_tokens=False`） | 伺服器端 `POST /tokenize`（同 messages + 同 chat_template） | ✅ 等價 |
| timestamp 定位 | 找 `timestamp_token_id` 位置，audio pad 後加 shift | 找 151705 位置，`i + audio_token_shift`（audio_pad=151676） | ✅ |
| 時間解碼 | `argmax × timestamp_segment_time`（80ms/bin） | `argmax × 80ms` | ✅ |
| 配對 | 第 i 個單位的 pair = 序列 `[2i, 2i+1]` | 相同 | ✅ |
| **後處理** | **`fix_timestamp`（LIS + 異常補整）再配對** | **無，raw 直接存檔** | ❌ 差異 |

### 4.2 單位切分：官方規則 = 我的規則

官方 `Qwen3ForceAlignProcessor.encode_timestamp`（非日韓語言）走 `tokenize_space_lang`：
- `text.split()` 按空白切段
- `clean_token`：只留 Unicode L*/N* 類別字元（字母、數字）與 `'` → 標點被丟掉
- `split_segment_with_chinese`：CJK 字各自成單位，其餘字元（字母/數字）累積成一串為一個單位

與 `split_text_units`（CJK 單字一個單位、連續 ASCII 字母數字一個單位、其他丟掉）在
本語料（中文 + 少量英文如 VTuber/AI）下產出完全相同的單位序列。
**官方不使用 LLM BPE tokenizer 決定對齊單位，也不需要 /detokenize**——
使用者的假設（分詞錯位）被排除；`<timestamp>` 是 prompt 內的顯式 marker token（151705），
單位邊界不依賴字元分詞。

### 4.3 根因：缺 `fix_timestamp`

官方 `parse_timestamp` 在配對 start/end 前，對整條 2N(+2) 原始 timestamp 序列執行
`fix_timestamp`：

1. 對序列跑 LIS（最長「非遞減」子序列，`data[j] <= data[i]`），LIS 成員標為 normal。
2. 逐段處理 non-normal 連續段：
   - 長度 ≤2：取左/右最近 normal 值，逐點指派「較近側」（無左取右、無右取左）
   - 長度 >2：用左/右最近 normal 值做線性插值
3. 再配對 `start = fixed[2i]`、`end = fixed[2i+1]`。

本專案跳過此步 → raw argmax 的離群 bin（快語速、重複詞「就是就是」「對對」區域最集中）
直接落檔 → 17 個 span 反轉、區間重疊、預覽片堆疊。
這與既有 QA 結論（亂序集中在快語速＋重複詞，與 chunk 長度無關）一致：
模型單 token 預測大致正確，少數離群值需要 LIS 補整。

### 4.4 伺服器端點確認（`curl /openapi.json`）

`POST /tokenize`、`POST /detokenize`、`POST /pooling`、`POST /ping`、`POST /invocations`；
`GET /load`、`/version`、`/health`、`/metrics`、`/v1/models`。

## 5. 修復計畫（使用者指令「先寫日誌後執行你的計畫」核准）

1. 新增 `exp/N9boWvU-KkA/scripts/fix_timestamps.py`：
   - 逐字移植官方 `fix_timestamp`（純 Python，無 numpy）
   - 讀 `filtered_aligned.json`，每段由 units 重構 2N 序列（毫秒整數）→ 跑 fix → 寫回
     `start_s`/`end_s`，原值保留為 `start_s_raw`/`end_s_raw`，被修單位加 `"fixed": true`
   - `word_matches` 依 `text_span` → 單位索引（`char_unit_map`）重算 start/end（同樣留 raw）
   - `issues` 依 `filter_align.py` 同規則重算；`meta.fix` 記錄方法與統計
   - 執行前備份到 `tmp/filtered_aligned_pre_fix.json`
2. 修 `render_fa_preview.py`：note 行 `f"FA: {u['unit']} ..."`，補整單位標「（補整）」
3. 重渲染 `p0_s173` 預覽片（覆蓋舊檔），驗證堆疊消失
4. 健檢：反轉數、重疊數、補整點數，與修復前對照回報
5. 待使用者目檢預覽片確認後，寫執行日誌；再進步驟 6（edit_video.py）

### 已知近似（與官方差異，需知會）

- 官方 fix 吃的是 2N+2 完整序列（含尾端多出的最後一對 marker）；我們由落檔的 2N 重構，
  尾端異常段的補整可能與官方微幅不同。
- 落檔值為 3 位小數秒（80ms bin 可精確表示），轉 ms 整數無失真。
- 補整值是「重建值」（最近正常值或插值），非模型直接測量；預覽與健檢以補整後為準，
  需要對照原始時看 `*_raw` 欄位。

## 6. 其他發現

- `chat_with_my_agent/2026_08_27/` 缺 `00_agent_full-alignment-run-and-qa.md` 主日誌檔
  （其歸檔 `assets/alignment-run-output/` 與 `scripts/` 兩資料夾存在），本條記为 01，
  00 缺失原因待查（可能是早先寫入失敗或檔案被移走）。
