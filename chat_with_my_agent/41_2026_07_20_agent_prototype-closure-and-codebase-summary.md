---
created: 2026-07-20
author: agent
type: agent
status: final
tags: [prototype-closure, codebase-summary, refactor-preparation]
---

# Prototype 結案報告 — 程式庫現況總結

## 背景

本程式庫是一個**一週期限的實驗性 prototype**，目標是在極端交付壓力下，從零建構完整的影音處理 pipeline，處理上百個錄影檔，並整合成成果報告。

開發風格偏實驗人員：快速建構 → 觀察行為 → 學習細節 → 徹底理解 → **大砍重練**。當前程式庫代表的是「理解所有環節後、清理前的最終狀態」。

## 系統架構（當前狀態）

### 資料流程

```
影片檔案 → VAD 說話區間偵測 → ASR 語音辨識 → LLM 文本清理 → LLM 畫面描述 → 多模態整合 → 成果文件
```

### 四個獨立入口

| 檔案 | 功能 | 狀態 |
|------|------|------|
| `main.py` | 完整 pipeline（VAD + ASR + LLM 三階段 CLI） | ⚠️ 1277 行，核心但臃腫 |
| `prototyper.py` | 僅 ASR 流程的簡化版 | ⚠️ 重複主程式的 ASR 邏輯 |
| `vad_preprocess.py` | VAD 預處理 CLI（多行程平行） | ⚠️ 與 main.py VAD 邏輯分離 |
| `test_vllm_delayed_guided_decoding.py` | OpenAI API 測試腳本 | ✅ 可刪除（測試用） |
| `debug_thinking_structured.py` | tqdm 多層進度條實驗 | ❌ 死碼 |

### 模組結構

```
src/
├── types.py              # SliceResult Pydantic model
├── utils/
│   ├── video.py          # IOCacheVideo（PyAV wrapper）— 最完整的模組
│   ├── audio.py          # normalize_audio
│   ├── vad_cache.py      # VAD cache 讀寫（644 行雜貨店）
│   ├── factory.py        # BytesIO factory + create_slices_indices
│   └── jsonl.py          # JSONL 讀寫
├── pipeline/             # ⚠️ 死碼，引用不存在之 import
│   ├── extractor.py      # 預期 local vLLM，與實際 OpenAI API 模式不符
│   ├── slicer.py         # 同上
│   └── loader.py         # load_model() 僅供參考
└── vllm_launch/          # Shell 腳本（部署用）
```

### 核心程式邏輯

#### `main.py` 三個階段

**Phase 0 — VAD 階段** (`run_phase_vad`)
- 批次掃描目錄，收集所有 .mp4/.mkv
- 對每部影片每條音軌執行 VAD 說話區間偵測
- 結果快取到 `runs/vad_cache/` JSON 檔
- 使用 `ProcessPoolExecutor` 多行程平行

**Phase 1 — ASR 階段** (`scan_and_run_phase1`)
- 批次掃描目錄
- 對每部影片每條音軌：
  1. 讀取 VAD cache（或即時計算）
  2. 只讀說話區間的音軌資料
  3. 送 vLLM ASR 模型（透過 OpenAI API）
  4. 結果存為 `track_N.jsonl`

**Phase 2 — LLM 階段** (`scan_and_run_phase2`)
- 批次掃描目錄
- 對每部影片：
  1. 音軌文本清理（chunked + 兩輪 LLM）
  2. ~~畫面提取~~（**L909 return 截斷，已死碼**）
  3. ~~影音清理~~（**已死碼**）
  4. ~~總結~~（**已死碼**）

#### 核心抽象

| 抽象層 | 用途 | 評價 |
|--------|------|------|
| `IOCacheVideo` | PyAV wrapper，支援快取模式 | ✅ 實作良好，可重用 |
| `SliceParams` | 切片參數 | ✅ 合理 |
| `SliceResult` | Pydantic structured output | ✅ 設計良好 |
| `vad_cache` 模組 | 快取管理 | ⚠️ 與 processing 邏輯混在一起 |
| `src/pipeline/*` | 預期 vLLM local mode | ❌ 不能用，應刪除 |

### 已知結構性問題

1. **main.py 1277 行，27 個函式** — 三個階段全部擠在同一支
2. **L909 return 截斷** — Phase 2 的畫面提取、影音清理、總結全部是死碼
3. **重複程式碼** — 音軌清理與影音清理的流程結構 90% 相同
4. **三個入口點** — `main.py`、`prototyper.py`、`vad_preprocess.py` 各有不同 CLI 解析
5. **硬編碼路徑** — `/mnt/hdd/...` 散落在多個檔案
6. **死碼積累** — `src/pipeline/` 不能執行、`main copy.py` 仍在 git 中
7. **零自動化測試** — 任何修改都是賭博

### 關鍵技術決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| LLM 呼叫方式 | OpenAI API（遠端 vLLM） | 比 local mode 穩定 |
| 影片讀取 | PyAV (`av.open`) | 比 OpenCV 靈活 |
| VAD | silero-vad（ONNX） | 速度快，可 chunked |
| 快取策略 | JSON 檔案 + `runs/` 目錄 | 避免重複運算 |
| 平行策略 | `ProcessPoolExecutor`（VAD）| CPU bound 任務需要多行程 |
| 結果格式 | JSONL（逐筆）+ Markdown（摘要） | 易於後處理 |

## 實驗者的學習收穫

經過這一周的暴力開發，已掌握以下細節：

1. **VAD 行為** — silero-vad 在長音軌上的表現、chunk boundary 處理、靜音軌偵測
2. **ASR 行為** — vLLM OpenAI API 的 latency、prompt 效果、多軌音訊處理
3. **影片 IO** — PyAV seek 效能、cached vs non-cached 差異、多軌音軌處理
4. **LLM 行為** — thinking mode、chunked 提示工程、兩輪清理策略
5. **pipeline 流程** — 從影片到成果文件的完整資料鏈

這些知識是重新建構的基礎。

## 已確認的可行方向

根據實驗結果，新的架構應遵循以下原則：

1. **重運算分離** — VAD 預處理、ASR、LLM 處理各自獨立，可平行執行
2. **本地腳本驅動** — 每個階段獨立可執行，不依賴單一龐大 main.py
3. **檔案導向** — 所有 intermediate state 存在檔案系統，不依賴記憶體
4. **OpenAI API 唯一通路** — 不需要 local vLLM mode
5. **最小抽象** — 只抽象已重複三次以上的模式，不做預防性抽象

## 下一步

這個 prototype 的使命已經達成：
- ✅ 理解所有環節的行為
- ✅ 驗證了可行的技術路徑
- ✅ 建立了關鍵細節的知識

現在是時候**大砍程式、清空空間、帶著思維重新建立**。

新的架構將按照「實際做的事情」劃分模組，每個模組都是最小可重複使用單位。不做過度抽象，不保留實驗用的 dead code，每個檔案都有明確的單一職責。

---

## References

- [main.py](../../main.py)
- [prototyper.py](../../prototyper.py)
- [vad_preprocess.py](../../vad_preprocess.py)
- [src/utils/video.py](../../src/utils/video.py)
- [src/utils/vad_cache.py](../../src/utils/vad_cache.py)
- [src/pipeline/](../../src/pipeline/)
- [tests/](../../tests/)