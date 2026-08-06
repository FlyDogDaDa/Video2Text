---
created: 2026-07-20
author: agent
type: agent
status: final
tags: [implementation-plan, next-steps, core-modules, data-flow]
---

# 核心模組實作計畫

## 核心模組回傳值修正

### detect_speech（vad.py）

**現在**：回傳 `list[dict]`
```python
def detect_speech(video: Path) -> list[dict]:
    ...
    return []  # stub
```

**目標**：回傳 jsonl 檔案路徑
```python
def detect_speech(video: Path) -> Path:
    """偵測影片中的說話區間，輸出 JSONL 檔案。
    
    Parameters
    ----------
    video:
        影片路徑。
    
    Returns
    -------
    Path
        說話區間 JSONL 檔案路徑（例如：`{video.stem}_vad.jsonl`）。
    """
    cfg = cfg("vad", VadConfig)
    
    # 實作邏輯：
    # 1. 讀取影片音軌
    # 2. 執行 VAD 偵測
    # 3. 寫入 JSONL 檔案
    # 4. 回傳檔案路徑
    
    return Path(f"{video.stem}_vad.jsonl")  # 暫時 stub
```

### generate_summary（summarize.py）

**現在**：回傳 `Path("output.md")`
```python
def generate_summary(audio: Path, video: Path) -> Path:
    ...
    return Path("output.md")  # stub
```

**目標**：回傳 markdown 檔案路徑
```python
def generate_summary(audio: Path, video: Path) -> Path:
    """生成多模態總結，輸出 Markdown 檔案。
    
    Parameters
    ----------
    audio:
        音訊逐字稿 JSONL 檔案路徑。
    video:
        視訊逐字稿 JSONL 檔案路徑。
    
    Returns
    -------
    Path
        總結 Markdown 檔案路徑（例如：`{audio.stem}_summary.md`）。
    """
    cfg = cfg("summarize", SummaryConfig)
    
    # 實作邏輯：
    # 1. 讀取 audio JSONL
    # 2. 讀取 video JSONL
    # 3. 呼叫 LLM 生成總結
    # 4. 寫入 Markdown 檔案
    # 5. 回傳檔案路徑
    
    return Path(f"{audio.stem}_summary.md")  # 暫時 stub
```

## 模組完整回傳值清單

| 模組 | 主函式 | 輸入 | 輸出 | 檔案格式 |
|------|--------|------|------|---------|
| vad | `detect_speech(video)` | 影片路徑 | jsonl 路徑 | 說話區間 |
| asr | `transcribe(video, vad_jsonl)` | 影片 + vad jsonl | jsonl 路徑 | 語音辨識 |
| video_desc | `describe_frames(video)` | 影片路徑 | jsonl 路徑 | 畫面描述 |
| clean | `reduce_redundancy(transcript_jsonl)` | 逐字稿 jsonl | jsonl 路徑 | 清理後逐字稿 |
| summarize | `generate_summary(audio_jsonl, video_jsonl)` | 音訊 + 視訊 jsonl | markdown 路徑 | 總結 |

## 資料流示意

```
video.mp4 ──→ detect_speech() ──→ video_vad.jsonl
                    │
                    ├──────────────→ transcribe() ──→ video_asr.jsonl
                    │
                    └──────────────→ describe_frames() ──→ video_video_desc.jsonl
                                                      │
                                                      ├──────────────→ reduce_redundancy() ──→ video_asr_clean.jsonl
                                                      │
                                                      └──────────────→ generate_summary() ──→ video_summary.md
```

## 實作順序建議

1. **jsonl.py**（30 行）— 檔案讀寫工具
2. **vad.py**（VAD 實作）— 第一個完整流程
3. **audio.py**（音軌提取）— asr.py 依賴
4. **video.py**（幀提取）— video_desc.py 依賴
5. **asr.py**（ASR API 呼叫）— 接 vLLM server
6. **video_desc.py**（畫面描述）— 接 vLLM server
7. **clean.py**（文本清理）— 本地處理
8. **summarize.py**（總結生成）— 最後一步，接 vLLM server
9. **錯誤處理 + 日誌** — 全域加入
10. **進度條** — 用戶體驗

## 必要依賴

```bash
uv add pydantic pyyaml openai tqdm
uv add pyav pydub              # 音影片處理
uv add silero-vad              # VAD 偵測
```

## 模組實作注意事項

- 每個模組的 `TODO` 註解處需實作核心邏輯
- 使用 `jsonl.py` 的 `read_jsonl()` 和 `write_jsonl()` 函數
- 輸出路徑命名規則：`{input.stem}_{module}.jsonl` 或 `{input.stem}_summary.md`
- 需實作快取機制：若輸出檔案已存在且時間戳記新於輸入，跳過執行