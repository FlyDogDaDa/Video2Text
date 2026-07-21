# Video2Text — 專案總覽

## 專案目標

將影片內容轉為結構化文字描述，使用 **Gemma-4-12B-it-qat-w4a16-ct** 進行視覺與音訊理解。

### 核心 Schema

每個影片切片（slice）輸出 JSON：

```json
{
  "start_at": 28.0,
  "end_at": 58.0,
  "visual": "畫面發生的事件描述",
  "dialogue": [{"speaker": "...", "text": "..."}],
  "sound": "背景音描述"
}
```

> **Window ＝ Slice**：設計文件稱「視窗」，程式碼用「slice」。30 秒視窗，滑動步長 = 視窗大小 - 重疊量。

---

## 最終架構（2026-06-12 定案）

```
┌─────────────────────────────────────────┐
│              main.py                     │
│  - slice_video() → list[SliceInput]     │
│  - asyncio.gather(*tasks) 並行          │
│  - 收集結果                             │
└──────────────┬──────────────────────────┘
               │ HTTP POST
               ▼
┌─────────────────────────────────────────┐
│   vllm serve (:8746)                    │
│   google/gemma-4-12B-it-qat-w4a16-ct    │
│  ─────────────────────────────────────  │
│  • 載入模型一次，永久可用               │
│  • template + 多模態編碼                │
│  • --reasoning-parser gemma4            │
│  • --tool-call-parser gemma4            │
└─────────────────────────────────────────┘
```

### 為什麼是 Server API 模式？

| 維度 | 離線推理（淘汰） | Server API（採用） |
|------|-----------------|-------------------|
| 載入開銷 | 每次 20 秒 | 一次載入，永久可用 |
| 多模態 bug | numpy array 格式不匹配 | `data:audio/wav;base64,...` 原生支援 |
| video_url | ❌ stable 不支援 | ✅ nightly dev301 |
| 並行 | 全部串列 | `asyncio.gather` 並行 |
| guided decoding | 需手動 StructuredOutputsParams | vLLM 自動處理 |
| reasoning 分離 | 需手動 parse_thinking_output | `--reasoning-parser` 自動 |
| 部署 | 需 SSH 到 GPU 機器 | API 調用即可 |

---

## 請求策略：兩階段穩定輸出

### 問題背景

- `enable_thinking=True` + `response_format` 並用 → `reasoning=None`，JSON 截斷（#32）
- `enable_thinking=True` + `tool_choice="required"` → `tool_calls=[]`（SDK 回傳 bug）（#35）
- 兩階段注入推理 ≠ 原生思考（#34）

### 最終方案

```
Phase 1: Free-form thinking
  enable_thinking=True, tool_choice="none"
  → 拿到完整 chain-of-thought + 自然語言描述

Phase 2: Structured anchoring
  enable_thinking=False, tool_choice="required"
  → 帶第一輪輸出，強制工具呼叫，保證 JSON 格式
```

### 驗證結果（2026-06-12）

用 `test_two_stage_output.py` 驗證通過：

| Phase | 設定 | 結果 |
|-------|------|------|
| Phase 1 | thinking ✅, tool_choice=`none` | ✅ reasoning (2611 chars) + 自然語言 (993 chars) |
| Phase 2 | thinking ❌, tool_choice=`required` | ✅ tool_call (8 relationships, clean JSON) |

---

## 已驗證能力

| 能力 | 狀態 | 備註 |
|------|:----:|------|
| vLLM server（OpenAI API） | ✅ | nightly dev301, TRITON_ATTN, port 8746 |
| 純文字推論 | ✅ | stable |
| 圖片推論（base64） | ✅ | dev301 已修復 num_soft_tokens bug |
| 音訊推論（base64 WAV） | ✅ | 原生支援 |
| 影片推論（video_url） | ✅ | dev301 原生支援 |
| thinking mode（單獨） | ✅ | `--reasoning-parser gemma4` 自動分離 |
| Function Calling（無 thinking） | ✅ | `tool_choice="required"` 穩定 |
| **兩階段 free-form → anchored** | ✅ | **生產環境策略** |
| thinking + response_format 並用 | ❌ | `reasoning=None`，JSON 截斷 |
| thinking + function calling 並用 | ❌ | `tool_calls=[]` SDK bug |
| SGLang | ❌ | 不支援 w4a16-ct quantization |

---

## 專案結構

```
Video2Text/
├── main.py                      # 入口（離線模式測試，待重構）
├── pyproject.toml
├── short_test.mp4               # 測試影片
├── runtime/
│   ├── ffmpeg                   # FFmpeg 7.0.2 靜態執行檔
│   └── ffprobe
├── src/
│   ├── types.py                 # 資料模型（原 models.py）
│   ├── pipeline/
│   │   ├── loader.py            # 離線模型載入（待重構）
│   │   ├── slicer.py            # 切片邏輯（待重構）
│   │   └── extractor.py         # 結構化提取（待重構）
│   ├── utils/
│   │   ├── video.py             # IOCacheVideo（PyAV 單一後端）
│   │   ├── factory.py           # create_bytes_io
│   │   └── audio.py
│   └── vllm_launch/
│       └── launch_Gemma4-12b.sh # vLLM server 啟動腳本
└── chat_with_my_agent/          # 開發日誌與策略文件
```

---

## 開發日誌索引

### 核心策略文件

| 檔案 | 日期 | 摘要 |
|------|------|------|
| [`01_...-video2text-system-design.md`](./01_2026_06_07_human_video2text-system-design.md) | 06-07 | 系統設計：schema、Sequential / Swarm 模式 |
| [`31_...-strategy-vllm-server-api-pattern.md`](./31_2026_06_11_human_strategy-vllm-server-api-pattern.md) | 06-11 | **策略定案：Server API 模式** |
| [`37_...-strategy-summary-vllm-server-api-two-stage.md`](./37_2026_06_12_human_strategy-summary-vllm-server-api-two-stage.md) | 06-12 | **總結：兩階段穩定輸出策略** |
| [`39_...-prototype-video2text-pipeline-plan.md`](./39_2026_06_13_prototype_video2text_pipeline_plan.md) | 06-13 | 實作計畫：端到端自動化原型機 |

### 實作與測試

| 檔案 | 日期 | 摘要 |
|------|------|------|
| [`00_...-project-initialization-and-vllm-setup.md`](./00_2026_06_07_agent_project-initialization-and-vllm-setup.md) | 06-07 | 專案初始化 |
| [`06_...-vllm-restore-for-gemma4.md`](./06_2026_06_07_agent_vllm-restore-for-gemma4.md) | 06-07 | 確立 vLLM 框架 |
| [`08_...-gemma4-vllm-inference-fixes.md`](./08_2026_06_08_agent_gemma4-vllm-inference-fixes.md) | 06-08 | Gemma-4 vLLM 推理修復 |
| [`11_...-fix-vllm-attention-backend-crash.md`](./11_2026_06_09_agent_fix-vllm-attention-backend-crash.md) | 06-09 | `--attention-backend TRITON_ATTN`，API 200 OK |
| [`16_...-vllm-nightly-installation-and-storage-optimization.md`](./16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md) | 06-09 | nightly dev301 修復四模態 |
| [`19_...-slice-utils-implementation.md`](./19_2026_06_10_agent_slice-utils-implementation.md) | 10-06 | 切片工具實作 |
| [`22_...-restructure-video-slicing-to-pyav.md`](./22_2026_06_10_agent_restructure-video-slicing-to-pyav.md) | 10-06 | PyAV 單一後端 + IOCacheVideo |
| [`23_...-swarm-structured-extraction.md`](./23_2026_06_11_agent_swarm-structured-extraction.md) | 11-06 | Swarm 模式結構化提取 |
| [`25_...-vllm-delayed-guided-decoding-offline.md`](./25_2026_06_11_agent_vllm-delayed-guided-decoding-offline.md) | 11-06 | 延遲引導解碼離線測試 |
| [`27_...-main-py-modularization-and-pipeline-extraction.md`](./27_2026_06_11_agent_main-py-modularization-and-pipeline-extraction.md) | 11-06 | main.py 模組化 430→79 行 |
| [`32_...-vllm-multimodal-openai-api-testing.md`](./32_2026_06_11_agent_vllm-multimodal-openai-api-testing.md) | 11-06 | thinking + structured output bug |
| [`33_...-gemma4-reasoning-three-variants.md`](./33_2026_06_11_agent_vllm-gemma4-reasoning-three-variants.md) | 11-06 | 三變體並行跑通 |
| [`34_...-vllm-reasoning-injection-equivalence.md`](./34_2026_06_11_agent_vllm-reasoning-injection-equivalence.md) | 11-06 | 兩階段注入推理 ≠ 原生思考 |
| [`35_...-function-calling-test-refactoring.md`](./35_2026_06_12_agent_function-calling-test-refactoring.md) | 12-06 | Function Calling 測試與工具衝突發現 |
| [`38_...-asr-audio-transcription-tool.md`](./38_2026_06_13_agent_asr-audio-transcription-tool.md) | 06-13 | ASR 音訊轉錄工具整合 |

### 參考實作（References）

| 目錄 | 日期 | 用途 |
|------|------|------|
| [`08_.../references_gemma4-vllm-inference-fixes/`](./08_2026_06_08_references_gemma4-vllm-inference-fixes/) | 06-08 | 影片推理測試 (`try_video.py`) |
| [`16_.../references_vllm-nightly-installation-and-storage-optimization/`](./16_2026_06_09_references_vllm-nightly-installation-and-storage-optimization/) | 06-09 | 多模態推理範例 (`multimodal_infer.py`) |
| [`23_.../references_swarm-structured-extraction/`](./23_2026_06_11_references_swarm-structured-extraction/) | 11-06 | Swarm 模式實作 (`main.py`, `test_swarm.py`) |
| [`25_.../references_vllm-delayed-guided-decoding-offline/`](./25_2026_06_11_references_vllm-delayed-guided-decoding-offline/) | 11-06 | 延遲引導解碼測試 (`test_vllm_delayed_guided_decoding.py`) |
| [`31_.../`](./31_2026_06_11_human_strategy-vllm-server-api-pattern/) | 11-06 | Server API 測試腳本集合 |
| [`38_.../asr_audio_transcription/`](./38_2026_06_13_asr_audio_transcription/) | 06-13 | ASR 轉錄 + 對齊實作 (`asr_and_align.py`, `asr_transcribe.py`) |

### 測試腳本

| 檔案 | 用途 |
|------|------|
| `31_.../how_to_use_vllm_multimodal_via_openai_api.py` | 多模態 demo（文字/圖片/音訊/推理） |
| `31_.../test_function_calling.py` | Function Calling + Thinking 測試 |
| `31_.../test_two_stage_output.py` | **兩階段策略驗證**（已驗證通過） |

---

## 決策時間軸

```
06-07  專案初始化 → vLLM 框架確定
06-08  Gemma-4 vLLM 推理修復 → 影片推理測試
06-09  API 200 OK → nightly dev301 → 四模態全部通過
06-09  vLLM nightly 安裝與儲存最佳化
06-10  PyAV 單一後端 + IOCacheVideo → FFmpeg 部署
06-10  切片工具實作 + main.py 模組化 430→79 行
06-11  Swarm 模式結構化提取
06-11  延遲引導解碼離線測試
06-11  Server API 模式定案（#31）
06-11  thinking + structured output 發現 bug（#32）
06-11  三變體驗證通過（#33）
06-11  reasoning 注入不等價（#34）
06-12  Function Calling 測試 → tool_choice 衝突發現（#35）
06-12  兩階段策略驗證通過 ✅（#37）
06-13  ASR 音訊轉錄工具整合（Breeze-ASR-26 + Qwen3-ForcedAligner）
06-13  端到端原型機實作計畫定稿（#39）
```

---

## 已知限制與待辦

| 項目 | 狀態 | 說明 |
|------|------|------|
| `main.py` Server API 重構 | ⏳ | 待實作，目前仍用離線模式 |
| `extract_structured()` 兩階段實作 | ⏳ | 待寫入 `src/pipeline/extractor.py` |
| 並行請求效能驗證 | ⏳ | 需測試 `asyncio.gather` 對多 slice 的加速比 |
| 端到端原型機 (`prototyper.py`) | 📋 | 計畫定稿 (#39)，待分階段實作 |
| ASR + 音訊對齊整合 | ✅ | Breeze-ASR-26 + Qwen3-ForcedAligner 已驗證 |
| Swarm Mode 整合 | 📋 | Round 1 兩階段 + Round 2+ context sandwich |
| `max_num_seqs` 並行數限制 | ⚠️ | 當前 16，需 `asyncio.Semaphore` 控制 |
| vLLM thinking + function calling bug | ❌ | `tool_calls=[]` SDK 回傳問題 |

---

## 快速開始

### 啟動 vLLM Server

```bash
vllm serve google/gemma-4-12B-it-qat-w4a16-ct \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-auto-tool-choice \
  --attention-backend TRITON_ATTN \
  --structured-outputs-config.enable_in_reasoning=True \
  --enforce-eager
```

### 運行測試

```bash
# 測試多模態能力
cd Video2Text
uv run python chat_with_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/how_to_use_vllm_multimodal_via_openai_api.py

# 測試 Function Calling
uv run python chat_with_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/test_function_calling.py

# 測試兩階段策略（已驗證通過）
uv run python chat_with_my_agent/31_2026_06_11_human_strategy-vllm-server-api-pattern/test_two_stage_output.py
```

### 使用技巧

- 所有 `cd` 參數都是 `Video2Text`（工作區根目錄）
- vLLM server 需先啟動，測試腳本才會連上 `http://localhost:8746/v1`
- 使用 `uv run` 進入虛擬環境

---

最後更新：2026-06-13
