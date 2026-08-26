---
created: 2026-07-20
author: agent
type: agent
status: final
tags: [code-audit, architecture-review, refactoring]
---

# Code Audit — main.py 全面架構審查

## What

對整個 Video2Text 專案進行全面的程式碼審查，針對 `main.py` 的臃腫程度、重複模式、模組化缺陷、以及整體架構問題產出具體的審查報告。

## Why

`main.py` 已成長為 1277 行、27 個函式的單一大檔案，包含 VAD / ASR / LLM 三個階段全部擠在同一支。專案中同時存在多個重複的入口點（`main.py`、`prototyper.py`、`vad_preprocess.py`、`debug_thinking_structured.py`），且 `src/pipeline/` 模組引用不存在的 import。需要一次性的完整評估來作為後續重構的基礎。

## How

- 全面閱讀 `main.py`（1277 行，27 個 symbol）的每個函式實現
- 瀏覽 `src/utils/` 下所有模組（`video.py`、`audio.py`、`vad_cache.py`、`factory.py`、`jsonl.py`）
- 檢查 `src/pipeline/`（`extractor.py`、`loader.py`、`slicer.py`）
- 檢查 `src/types.py`、`pyproject.toml`、`tests/`
- 比對根目錄多個 entrypoint 的差異
- 整理重複模式、硬編碼路徑、死碼區塊、結構性問題

## 主要發現

### 1. main.py 1277 行怪物

| 指標 | 數值 |
|------|------|
| 行數 | 1277 |
| 函式數量 | 27 |
| 包含的 Phase | VAD + ASR + LLM 全部擠在同一支 |
| 硬編碼路徑 | `/mnt/hdd/b11223209/螢幕錄影/2026_06/` 散落在 main.py、vad_preprocess.py |

- 第 909 行 `run_single_file_llm()` 有 `return` 把畫面提取、影音清理、總結截斷為死碼
- CLI 解析巢狀四層 `if args.phase` 分支，快速測試 / 單檔案 / 批次模式交錯
- 兩個幾乎相同的 chunking cleanup 流程（音軌 vs 影音）各 160+ 行

### 2. 重複模式

- `run_workflow_audio_transcription_cleanup_chunked` (L408) 與 `run_workflow_video_transcription_cleanup_chunked` (L676) 結構幾乎一模一樣
- `async with sem:` + LLM call 模式重複 5 次以上
- `enable_thinking: True` 寫入 8 次以上
- `if result is None: raise ValueError("model stuck in loop")` 寫入 3 次
- 檔案收集邏輯在 `vad_preprocess.py`、`main.py`、`vad_cache.py` 各有版本

### 3. src/pipeline/ 死碼

- `extractor.py` import `src.utils.slice` 但該 module 不存在（已改名為 `src.utils.video`）
- `slicer.py` 同樣引用不存在的 import
- 這些模組預期直接操作 vLLM `LLM` instance，與 main.py 的 OpenAI API 遠端模式完全無關

### 4. 沒有自動化測試

- `tests/test_models.py` 與 `tests/test_slice_utils.py` 極少
- 根目錄 `test.py` 不是 pytest 測試，只是 `asyncio.run()` 呼叫 OpenAI API 的 script
- main pipeline 零自動化測試覆蓋

### 5. 多個重複入口點

- `main.py` — 完整 pipeline（VAD + ASR + LLM）
- `prototyper.py` — 僅 ASR 流程
- `vad_preprocess.py` — VAD 預處理 CLI
- `debug_thinking_structured.py` — tqdm 多層進度條測試
- `main copy.py` — 舊備份仍在 git 中

### 6. vad_cache.py 644 行雜貨店

單一檔案做了 cache path 計算、save/load/clear、檔案收集、批次 VAD 處理、跨 process 工作 — 應該拆成至少 4 個模組。

## Follow-up

- 需要設計新的模組化架構：VAD 處理、ASR 批次、LLM 批次 各自獨立模組
- 需要消除多個入口點，只保留一個 CLI 入口
- 需要修復 src/pipeline/ 的 import 或決定打掉重練
- 需要加入自動化測試覆蓋核心 pipeline
- 需要移除死碼（main.py L909 return 截斷的 Phase 2 剩餘工作）
- 需要提取常數與配置到集中管理

## References

- [main.py](../../main.py)
- [prototyper.py](../../prototyper.py)
- [vad_preprocess.py](../../vad_preprocess.py)
- [src/utils/vad_cache.py](../../src/utils/vad_cache.py)
- [src/pipeline/extractor.py](../../src/pipeline/extractor.py)
- [src/pipeline/slicer.py](../../src/pipeline/slicer.py)
- [tests/](../../tests/)
- [pyproject.toml](../../pyproject.toml)