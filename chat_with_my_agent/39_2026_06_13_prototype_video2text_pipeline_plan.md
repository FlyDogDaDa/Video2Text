---
created: 2026-06-13
author: Human + Agent
type: human
status: draft
tags: [prototype, video2text, pipeline, vllm, asyncio, gemma4]
---

# 實作計畫：Video2Text 自動化處理原型機 (Prototyper)

## 1. 專案目標
建立一個端到端的自動化指令碼 `prototyper.py`，能夠將單一影片檔案轉換為高質量的長片總結。該指令碼將包含多模態內容提取、去重清洗、視覺與語音內容對齊，並最終產出結構化的總結檔案。

## 2. 技術架構與環境
- **模型**: Gemma-4-12B-it-qat-w4a16-ct
- **推理引擎**: vLLM Server (Port 8746)
- **核心庫**: `asyncio` (並行處理), `PyAV` (影片處理), `AsyncOpenAI` (模型通訊)
- **並行策略**: 使用 `asyncio.Semaphore(16)` 控制最大並行請求數。

## 3. 執行流程設計

### 階段一：逐字稿提取與清洗 (Audio/Speech Task)
1.  **影片切片 (Slicing)**:
    *   讀取影片並按 30 秒視窗、15 秒重疊進行切分。
2.  **逐字稿轉錄 (Transcription)**:
    *   呼叫 VLLM API 使用 `enable_thinking=True` 並搭配 `tool_choice="none"`。
    *   目的：獲取包含完整思考過程的高品質逐字稿。
3.  **中間產物儲存**:
    *   在影片同名資料夾下儲存 `transcript_segments.jsonl`。
4.  **去重處理 (De-duplication)**:
    *   提取所有切片的 `dialogue` 內容，拼湊為單一文本塊。
    *   使用 Prompt 要求模型去除重複內容並保留核心細節。
    *   儲存結果至 `clean_transcript.md`。

### 階段二：視覺內容提取 (Visual Task)
1.  **影片切片 (Slicing)**:
    *   按 10 秒視窗、5 秒重疊進行切分。
2.  **視覺提取 (Visual Extraction)**:
    *   **情境注入**: 從 `clean_transcript.md` 提取當前時間範圍內的語音內容，作為 Prompt 前導資訊。
    *   **結構化輸出**: 要求模型描述畫面內容，輸出包含 `start_at`, `end_at`, `description` 的 JSON 格式。
3.  **中間產物儲存**:
    *   將結果存入 `visual_segments.jsonl`。

### 階段三：最終長片總結 (Synthesis Task)
1.  **資料對齊 (Data Alignment)**:
    *   將 `clean_transcript.md` 與 `visual_segments.jsonl` 內容按時間軸排序與對齊。
2.  **最終總結 (Final Summary)**:
    *   將對齊後的資訊串接成 Prompt，要求模型生成整體的長片總結。
    *   Prompt 包含：開始 code-block、時間序要求、細節保留要求，並在末尾再次提示格式要求。
3.  **最終產物**:
    *   儲存為 `final_summary.md`。

## 4. 資料結構定義 (Schema)
*   **SliceResult**: 包含 `start_at`, `end_at`, `visual`, `dialogue`, `sound`。
*   **VisualSegment**: 包含 `start_at`, `end_at`, `content`。

## 5. 待辦事項 (Follow-up)
- [ ] 建立 `prototyper.py` 並實作階段一。
- [ ] 建立中間產物儲存邏輯。
- [ ] 實作視覺提取時的動態內容注入演算法。
- [ ] 進行並行化效能壓力測試。

## 6. 參考檔案
- [37_2026_06_12_human_strategy-summary-vllm-server-api-two-stage.md](../../37_2026_06_12_human_strategy-summary-vllm-server-api-two-stage.md)
- [38_2026_06_13_agent_asr-audio-transcription-tool.md](../../38_2026_06_13_agent_asr-audio-transcription-tool.md)
- [22_2026_06_10_agent_restructure-video-slicing-to-pyav.md](../../22_2026_06_10_agent_restructure-video-slicing-to-pyav.md)
