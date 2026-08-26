---
created: 2026-07-20
author: agent
type: agent
status: final
tags: [architecture, design, v0.1.1, prototype-closure]
---

# 架構設計檔案 — Video2Text v0.1.1

## 概要

此檔案定義 Video2Text 專案重新建構後的架構。整個專案是一個實驗性 prototype 的重寫，目標是清除所有 legacy code，以全新的模組化架構重新建構。

## 核心設計原則

### 1. 直接函式呼叫（拒絕超級函式）

不使用通用 `run(module_name, ...)` 這種查表式呼叫。每個功能都是明確命名的函式，簽名即檔案。

### 2. Config 提走（數學提公因式）

Config 不作為 public API 的必須引數。模組內部自行從全域性 profile 載入 config，外部只看見「輸入路徑 → 輸出路徑」。

### 3. 對外開放，對內封閉

- 框架提供通用方法（路徑取得、config 初始化），模組可自由使用
- 框架不決定模組的 key name、config schema、執行邏輯
- 模組定義自己的 Pydantic config，框架負責 YAML → Pydantic 轉換

### 4. 檔案導向

所有 intermediate state 存在檔案系統。Cache key 就是 path hash。

## 目錄結構

```
video2text/
├── profiles/                  # YAML 設定檔
│   ├── default.yaml           # 預設 profile
│   ├── research.yaml          # 研究用（保守設定）
│   └── final.yaml             # 最終版（生產設定）
│
├── modules/                   # 功能模組（每個模組獨立）
│   ├── __init__.py
│   ├── vad.py                 # VAD 說話區間偵測
│   ├── asr.py                 # 語音辨識
│   ├── video_desc.py          # 畫面描述
│   ├── clean.py               # 文本清理
│   └── summarize.py           # 多模態總結
│
├── framework/                 # 共享框架（模組使用，使用者不直接碰）
│   ├── __init__.py
│   └── config.py              # profile 路徑管理、config 載入
│
└── workflow.py                # 唯一的入口，組合各模組
```

## 框架層（framework）

### config.py

提供兩個全域函式：

```python
# ── 設定 profile 路徑（workflow.py 呼叫一次） ──
def set_profile(path: str):
    """設定 profile 路徑。全域共享。"""

# ── 取得 config（模組內呼叫） ──
def cfg(key: str, model: type[BaseModel]) -> BaseModel:
    """從當前 profile 讀取 key section 並初始化成 model。"""
```

**行為**：
- `set_profile()` 設定全域性變數 `_PROFILE_PATH`
- `cfg(key, Model)` 讀取 `_PROFILE_PATH` 的指定 key，用 Pydantic 初始化
- 無快取（YAML 很小，讀取成本可忽略）

**模組範例**：

```python
# modules/vad.py
from pydantic import BaseModel
from framework.config import cfg

class VadConfig(BaseModel):
    threshold: float = 0.5

def detect_speech(video: Path) -> list[dict]:
    c = cfg("vad", VadConfig)  # 一行取得 config
    ...
```

## 模組層（modules）

### 每個模組的結構

```python
from pydantic import BaseModel
from framework.config import cfg

# 1. 定義 config schema
class ModuleConfig(BaseModel):
    field1: str = "default"
    field2: int = 42

# 2. 定義主功能函式
def main_function(input_path: Path) -> Path:
    c = cfg("module_name", ModuleConfig)
    # 執行邏輯...
    return output_path
```

### 簽名原則

| 規則 | 說明 |
|------|------|
| 輸入路徑 | `Path` 型別，明確指定輸入檔案 |
| 輸出路徑 | 回傳 `Path` 型別，明確指定輸出位置 |
| Config 不作為引數 | 透過 `cfg()` 內部取得 |
| 名稱明確 | 不用 `run()`、`process()` 等模糊名稱 |

### 模組清單

| 模組 | 主功能 | 輸入 | 輸出 |
|------|--------|------|------|
| `vad` | `detect_speech(video) → segments` | 影片路徑 | 說話區間列表 |
| `asr` | `transcribe(video, segments) → transcript` | 影片路徑 + 區間 | 音訊逐字稿路徑 |
| `video_desc` | `describe_frames(video) → video_transcript` | 影片路徑 | 畫面描述路徑 |
| `clean` | `reduce_redundancy(transcript) → cleaned` | 逐字稿路徑 | 清理後逐字稿路徑 |
| `summarize` | `generate_summary(audio, video) → summary` | 音訊 + 視訊逐字稿 | 總結路徑 |

**注意**：`vad` 是唯一不回傳 Path 的模組（回傳 segments list），因為 segments 是後續模組的共同輸入，不存在檔就不需要 cache。

### Config 預設值

每個模組的 `BaseModel` 應該定義合理的預設值。即使 YAML 沒有指定該欄位，模組仍可使用預設值執行。

## Profile 層（profiles）

### 結構

```yaml
# profiles/default.yaml
vad:
  threshold: 0.5
  min_silence_duration_ms: 300
  chunk_seconds: 300.0

asr:
  model: "MediaTek-Research/Breeze-ASR-26"
  batch_size: 64
  language: "zh"

video_desc:
  fps: 1.0
  max_tokens: 24576
  temperature: 1.0

clean:
  chunk_size: 20
  temperature: 1.0

summarize:
  max_tokens: 24576
  temperature: 1.0
  top_p: 0.95
```

### 使用方式

```yaml
# profiles/research.yaml
vad:
  threshold: 0.4            # 更敏感
  chunk_seconds: 180        # 較小 chunk

asr:
  batch_size: 32            # 較小批次
```

### Profile 選擇

- 專案預設使用 `profiles/default.yaml`
- 使用者可透過 `set_profile()` 切換
- 不同 profile 之間是**完全獨立**的，不共享設定

## Workflow 層

### workflow.py

唯一的入口指令碼，組合各模組：

```python
import argparse
from pathlib import Path
from framework.config import set_profile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--profile", default="profiles/default.yaml")
    args = parser.parse_args()

    # 設定 profile（一次設定，全域共享）
    set_profile(args.profile)

    # 明確的模組呼叫，沒有超級函式
    segments = detect_speech(args.input)
    transcript = transcribe(args.input, segments)
    video_desc_result = describe_frames(args.input)
    cleaned = reduce_redundancy(transcript)
    summary = generate_summary(cleaned, video_desc_result)

    print(f"Done → {summary}")
```

### 執行方式

```bash
# 使用預設 profile
uv run python workflow.py --input video.mp4

# 使用研究 profile
uv run python workflow.py --input video.mp4 --profile profiles/research.yaml
```

## 設計決策記錄

| 決策 | 選擇 | 理由 |
|------|------|------|
| Config 傳遞 | 全域 `cfg()` 函式 | 模組 API 乾淨，不用每次傳 cfg |
| Profile 管理 | `set_profile()` 全域變數 | 簡單，workflow 級別設定一次 |
| 模組介面 | 明確名稱 + Path 引數/回傳 | 簽名即檔案，無查表成本 |
| 目錄結構 | 按「做的事情」分類 | 每個模組只做一件事 |
| YAML key | 模組自己定義 | 框架不決定模組的 key |
| Cache | 模組自己實現 | 框架不干涉執行邏輯 |

## 未定義專案（待討論）

- Cache 策略細節（cache key 格式、過期策略）
- Error handling 模式
- Logging 策略
- 測試架構
- 多個 workflow.py 是否需要？目前只有一個 `workflow.py`