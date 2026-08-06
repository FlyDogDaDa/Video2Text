---
created: 2026-06-07
author: User
type: human
status: draft
tags: [design, video2text, architecture, vllm]
---

# Video2Text System Design

## Overview

Video2Text 是一個將影片內容轉為結構化文字描述的系統，使用 LLM 進行視覺與音訊理解。支援兩種處理模式，並可串聯使用。

## Core Schema

每個視窗輸出的 JSON 格式：

```json
{
  "description": {
    "visual": "畫面發生的事件描述",
    "audio": "畫面中的音訊內容描述"
  },
  "transcription": {
    "audio": [
      {"text": "對話內容", "speaker": "語者名稱"},
      {"text": "對話內容", "speaker": "語者名稱"}
    ]
  },
  "time_range": {
    "start": 28.0,
    "end": 58.0
  }
}
```

## Terminology

> **Window**（設計文件中的用詞）＝ **Slice**（程式碼中的用詞）

兩者指的是同一個概念：從影片中提取的一段連續時間區間。程式碼偏好使用 **Slice**，因為更能傳達「從影片中取出小區段」的語感。全文的 `window`、`slice` 可互換，實作時統一以 Slice 命名。

## Common Design

| 要素 | 說明 |
|------|------|
| 音訊處理 | 轉為 Mono 混音 |
| 視覺抽幀 | 1 FPS（可引數化） |
| 視窗大小 | 30 秒（可引數化） |
| 視窗重疊 | 滑動步長 = 視窗大小 - 重疊量 |
| 輸出格式 | JSON |
| 語者清單 | 系統提示中預設，嵌入 schema |

## Processing Modes

### Sequential Mode（序列式）

線性處理，一次一個視窗：

```
視窗1: |── 0s ───30s ────────────|
視窗2:          |── 28s ───58s ───|  ← 起始 = 上一輪開始 + 重疊
視窗3:                  |── 56s ───86s ───|
```

Context 結構：
```
[系統提示] + [上文累積] + [當前視窗]
```

特性：
- 因果理解好，每個視窗依賴前一個的輸出
- VRAM 需求低，一次只處理一個視窗
- 速度較慢

### Swarm Mode（蜂群式）

平行處理，一次所有視窗：

```
Round 1: 視窗1,視窗2,...,視窗N → Summarize
Round 2: 視窗1,視窗2,...,視窗N → Summarize (更深)
...
```

#### Context 結構

**Round 1（初始化）：**
```
[系統提示]
[當前視窗：影片與提問]
```
無任何上下文，完全離散視角。

**Round 2+（三明治版本）：**
```
[系統提示]
[Summarize from previous round]    ← 全域性濃縮，掌握大意
[Preceding windows]                ← 上文：R1 完整輸出中比當前視窗更早的視窗
[當前視窗：影片與提問]             ← 當前處理的視窗
[Following windows]                ← 下文：R1 完整輸出中比當前視窗更晚的視窗
```

說明：
- 下文**不是預警**，而是 R1 完整輸出按視窗位置的拆分
- 所有視窗在 Round 2+ 都能看到整個 R1 的完整輸出
- 只是按位置拆成上文/下文兩段，格式上像三明治包夾

特性：
- 真正並行，由 vLLM 管理
- 全域性理解強，有 Summarize + 完整 Context 包夾
- VRAM 需求高

## Round 結構

```python
def run_round(round_num: int, previous_results: list | None) -> list:
    """核心單位，無狀態，可重複呼叫"""
    
    # 1. Context Pack 階段
    if round_num == 1:
        context = {"system_prompt": prompt}
    else:
        context = {
            "system_prompt": prompt,
            "summarize": summarize(previous_results),  # 上一輪全域性濃縮
            "preceding_windows": previous_results[:i], # 上文：比當前更早的視窗
            "following_windows": previous_results[i+1:], # 下文：比當前更晚的視窗
        }
    
    # 2. 執行視窗（平行）
    windows = create_windows(context, video, params)
    results = parallel_send(windows, vllm)
    
    # 3. 儲存輸出
    save_results(results)
    return results
```

Round 1 是初始化（無上下文），Round 2+ 才有意義（有全域性脈絡）。

## Advanced Usage

```
序列式掃描 → 取得關鍵時間段 → 蜂群式深度理解
```

第一層用序列式快速掃描建立時間索引，第二層用蜂群式針對索引點進行全域性交叉分析。

## Implementation Strategy

所有模式共用同一個執行函式，差異只在 Context 打包：

```python
def execute_window(context: Context, video_segment: Segment) -> JSON:
    prompt = build_prompt(context, video_segment)
    return llm.generate(prompt, response_format=JSON)
```

主程式的角色：
- 設定引數（模式、輪數、視窗大小等）
- 打包 Context
- 反覆呼叫 `run_round()`
- 儲存結果

## Error Handling

| 狀況 | 處理方式 |
|------|---------|
| LLM 格式錯誤 | 不會發生（vLLM 保證 response_format） |
| 時間戳異常 | 重試一次，插入反饋提示 |

最終無額外輸出，使用者自由組合。
