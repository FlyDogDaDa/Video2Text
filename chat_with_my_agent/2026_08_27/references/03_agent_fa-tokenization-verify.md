# FA 分詞驗證——token↔字元對應到底是怎麼做的

## 使用者疑慮

使用者提出：「你有使用 tokenizer 和 de-tokenizer 取得真實 Token 對應字元嗎？還是你自己靠手算？」
並建議研究 vLLM 官方 FA 流程：`tokenizer → IDs → FA → 時間 pool → classify_num + de-tokenizer(IDs) → 時間戳`，
理由是「tokenizer 分詞後的 Token 可能跟我們預期的不一樣，遵循 FA 模型的分詞算法就好」。
並給出 vLLM token_classify（Forced Alignment）文件頁。

## 調查：現有 `filter_align.py` 怎麼做

讀 `exp/N9boWvU-KkA/scripts/filter_align.py`（歸檔副本 `scripts/fa-tokenization-verify/filter_align.py`）：

1. **`split_text_units`（單位切分）**：
   - CJK 單字 = 1 單位；連續字母數字（如 VTuber）= 1 單位；標點丟掉。
   - 與官方 `Qwen3ForceAlignProcessor` 的 `split_segment_with_chinese` 規則一致（log 01 已比對官方原始碼）。
2. **`build_prompt`（L124）**：
   `prefix + "<timestamp><timestamp>".join(words) + "<ts><ts>"`
   每個單位前後各插一個 `<timestamp>`（token id 151705），N 單位 → 2N 個 timestamp token。
3. **`tokenize_messages`（L183–208）**：
   **POST `/tokenize`** 到 vLLM 伺服器（`http://10.46.219.5:8755`），傳與 `align_once` 完全相同的
   `messages` + `chat_template`，取**伺服器端真實** `token_ids`。
   → 不是手算 token id，也不是本地另裝一份 tokenizer 對齊。
4. **`align_once`（L235–316）**：
   - 從真實 token_ids 找所有 151705 的位置（應為 2N 個）
   - `audio_pad=151676` 後加 `audio_token_shift`
   - `POST /pooling`（`task=token_classify`、`classify_num=5000`、
     `chat_template="{{ messages[0]['content'] }}"`）
   - argmax × 80ms（`timestamp_segment_time`）得每個 `<ts>` 的 bin
   - `pair=[2i, 2i+1]` 配對成單位的 start/end

## 驗證腳本 `verify_tokenization.py`

實測樣本句（30 單位）：`對我的意思是說就是就是VTuber就是印象裡面它會是一個比較以遊戲直播`

| 項目 | 結果 |
|------|------|
| 逐字單位數（`split_text_units`） | 30 |
| A) 整句送 `/tokenize` 自然 BPE | 18 tokens（CJK 多字併成 1 token，如「VTuber」也非 1 token） |
| B) 逐字 prompt（含 `<ts>` 標記）送 `/tokenize` | 94 tokens |
| B) 其中 `<timestamp>`（151705）數量 | 60 = 2 × 30，**全部對位正確** |

結論：

1. **token 序列走伺服器 `/tokenize` API，非手算**——`filter_align.py` 的 `tokenize_messages`
   已用與 FA 請求同參數（同 messages、同 chat_template）取真實 token_ids。
2. **自然 BPE 與逐字切分不同**（18 vs 94 tokens），但 FA 讀點由 prompt 裡插入的
   `<timestamp>` 標記決定：逐字 prompt 下每個 CJK 字仍是單 token、每個單位前後恰有 1 對 `<ts>`，
   60 = 2×30 全對位。→ **遵循 FA 模型的分詞算法就是官方 `Qwen3ForceAlignProcessor` 的逐字切法，
   我們做的與它一致**。
3. **de-tokenizer 不需要**：逐字方案下，文字→單位的切分在 `split_text_units` 時就已完成
   （單位是手切、非模型分詞產物），FA 回傳的 2N 個 bin 直接對回已知單位序列，
   不存在「模型分詞產物要還原字元」的問題。vLLM 文件裡的 `de-tokenizer(IDs)` 步驟
   是給「模型自由分詞」場景用的；FA 場景下官方處理器就是用固定 `<ts>` 標記定位，不需 detokenize。
4. `/tokenize` 的 `token_strs` 需顯式 `"return_token_strs": true` 才回傳；
   CJK 字串回傳是 latin1 解 UTF-8 的亂碼，但 token id 與數量正確可用。

## 對使用者建議的回應

- 建議的 `tokenizer→IDs→FA→時間pool→classify_num+de-tokenizer(IDs)→時間戳` 流程中，
  前四段（tokenizer、IDs、FA、時間 pool）我們已走伺服器 API；
  最後 de-tokenizer 段在逐字標記方案下是恒等映射（單位序列本來就已知），無實質作用。
- 「分詞後 Token 可能跟預期不一樣」確實是自然 BPE 的行為（實測 18 tokens），
  但 FA 不依賴自然 BPE 邊界——依賴的是插入的 `<timestamp>` 標記，已實測 60/60 對位。

## 產出

- `exp/N9boWvU-KkA/scripts/verify_tokenization.py`（已執行）
- 歸檔：`scripts/fa-tokenization-verify/verify_tokenization.py`、`filter_align.py`
