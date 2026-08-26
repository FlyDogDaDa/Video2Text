---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [voicetag, breeze-asr-26, diarization, transcription, json-output]
---

# voicetag transcribe() 成功測試 — 完整 JSON 輸出

## What

- 驗證 voicetag 的 `transcribe()` 能正常連線 Breeze-ASR-26 並輸出完整 JSON
- 測試 pyannote diarization 與 transcription 的整合 pipeline
- 確認輸出格式符合「誰、在何時、講了什麼」的需求

## Why

- 使用者需要「誰在何時講話」的 JSON 輸出
- 不註冊 speaker 時 diarization 依然有效（segments 正確切分）
- 這是完整的 end-to-end pipeline 測試，確認 voicetag + Breeze-ASR 的整合可行

## How

### 測試環境

| 專案 | 設定 |
|------|------|
| Breeze-ASR-26 | port 8750, TP_SIZE=1, GPU_MEM_UTIL=0.08, async-scheduling, PID 273073 |
| voicetag venv | `serve/voicetag/.venv` (Python 3.10.19) |
| 測試音訊 | `test-audio/meeting_30_60s.wav` (30 秒) |
| 測試裝置 | CPU（GPU 在 resemblyzer embedding 階段被卡住） |

### 測試結果

**Diarization（pyannote）獨立測試**：
- 載入時間：3.4 秒
- 偵測到 11 個 segments，4 個 speaker（SPEAKER_00~03）
- 處理時間：5.0 秒

**完整 identify() pipeline**：
- 載入 voice encoder model：0.04 秒（CUDA）
- CPU 模式下完整完成：10.1 秒
- 偵測到 9 個 segments（min_segment_duration=0.5s）
- 因為沒有註冊 speaker，全部標記為 `UNKNOWN`

**完整 transcribe() pipeline（連 Breeze-ASR-26）**：
- 處理時間：12.8 秒
- 9 個 segments，每個都有 text + 時間軸
- JSON 格式：

```json
{
  "segments": [
    {
      "speaker": "UNKNOWN",
      "start": 0.031,
      "end": 6.629,
      "text": "前情提要讓傑信知道 我們在討論什麼問題...",
      "confidence": 0.0
    }
  ],
  "audio_duration": 30.0,
  "num_speakers": 0,
  "processing_time": 12.88
}
```

### 使用方式

```python
from voicetag import VoiceTag, VoiceTagConfig
import json

vt = VoiceTag(config=VoiceTagConfig(
    hf_token="hf_...",
    device="cuda"
))

# 選擇一：只跑轉錄 + 語音分離
result = vt.transcribe(
    "audio.wav",
    provider="openai",
    api_key="token-abc123",
    model="MediaTek-Research/Breeze-ASR-26",
    base_url="http://localhost:8750/v1",
    language="zh"
)
print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))

# 選擇二：註冊 speaker 後再識別
vt.enroll("黃", ["test-audio/黃.wav"])
vt.enroll("文", ["test-audio/文.wav"])
result = vt.transcribe(...)  # speaker 會被識別為 "黃"、"文"
```

## Follow-up

- [ ] 用完整的 2 小時會議檔案（`~/檔案/AudioRecording/保修工程會議.m4a`）測試
- [ ] 註冊 speaker 樣本後測試 identification（目前都是 UNKNOWN）
- [ ] 修復 GPU 模式下的 resemblyzer 卡住問題（可能是 CUDA OOM 或 hanging）
- [ ] 考慮用 `cuda` 替代 `cpu` 以加速 embedding 計算

## References

- [65_2026_07_31_agent_voicetag-openai-compatible-url-research](./65_2026_07_31_agent_voicetag-openai-compatible-url-research.md)
- [64_2026_07_31_agent_vllm-breeze-asr26-installation-and-stt-testing](./64_2026_07_31_agent_vllm-breeze-asr26-installation-and-stt-testing.md)
- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)