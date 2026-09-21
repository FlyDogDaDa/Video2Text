# FA 官方對齊器原始碼歸檔

## 檔案

- `qwen3_forced_aligner.py`
  - 來源：`QwenLM/Qwen3-ASR` @ main，路徑 `qwen_asr/inference/qwen3_forced_aligner.py`
  - 擷取方式：`curl https://raw.githubusercontent.com/QwenLM/Qwen3-ASR/main/qwen_asr/inference/qwen3_forced_aligner.py`（2026-08-27，內容未改動）
  - 關鍵類別：`Qwen3ForceAlignProcessor`

## 關鍵發現（2026-08-27 診斷 `exp/N9boWvU-KkA` 預覽片字幕堆疊時查到）

1. **單位切分規則**（`tokenize_space_lang` → `split_segment_with_chinese`，非日韓語言）：
   - 每個 CJK 字 = 1 個對齊單位
   - 連續非 CJK 字母/數字 = 1 個單位
   - 標點、空白被丟掉
   - 與 `exp/N9boWvU-KkA/scripts/filter_align.py` 的 `split_text_units` 規則一致；
     且官方流程**不使用 LLM 的 BPE tokenizer 做單位對應**，因此 API 的 `/detokenize` 在此用途上不需要。
2. **缺失的後處理**：`parse_timestamp` 在配對 start/end 前，對整條 2N(+2) 原始 timestamp
   序列先跑 `fix_timestamp`：
   - LIS（最長非遞增多項式）標出「正常」值
   - 異常段 ≤2 個：取左/右最近正常值的較近者
   - 異常段較長：兩側最近正常值線性插值
   - `filter_align.py` 直接存了 raw argmax、沒跑這步 → 17 個 span 反轉、區間重疊、預覽片堆疊的根因。

## 相關外部頁面（未快照，直接連結）

- vLLM `token_classify` 文件（含 Forced Alignment Offline / Online 範例）：
  <https://docs.vllm.ai/en/latest/examples/pooling/token_classify/>
- 模型卡：`https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B`
  （說明 FA 支援「arbitrary units」、≤5 分鐘音訊）
- 官方 repo：`https://github.com/QwenLM/Qwen3-ASR`
