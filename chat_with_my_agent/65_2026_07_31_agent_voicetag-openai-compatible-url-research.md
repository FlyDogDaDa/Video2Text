---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [voicetag, openai-api, breeze-asr-26, speaker-diarization, transcription]
---

# voicetag OpenAI 相容 URL 設定研究

## What

1. 研究 voicetag 官方 GitHub 倉庫（Gr122lyBr/voicetag）的 `openai_stt.py` 是否支援 `base_url` 引數
2. 評估能否用 voicetag 的 `transcribe()` 搭配 Breeze-ASR-26 達成「誰在何時說了什麼」
3. 確認是否需要 patch 官方程式碼

## Why

- 目標：產出 **誰、在何時、講了什麼** 的 JSON
- voicetag 已經有完整的 diarization + identification + transcription pipeline
- 不應該自己重複造輪子，直接用官方庫
- Breeze-ASR-26 提供 OpenAI 相容 API，理論上可以取代官方 OpenAI Whisper API

## How

### 官方程式碼分析

**GitHub**: `https://github.com/Gr122lyBr/voicetag`
**版本**: 0.2.0（2026-03-16 釋出）
**Python**: >=3.10

官方 `openai_stt.py` 目前的實作：

```python
def __init__(
    self,
    api_key: Optional[str] = None,
    model: str = "whisper-1",
) -> None:
    self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
    self._model = model

def transcribe(self, audio, sr=16000, language=None) -> str:
    client = OpenAI(api_key=self._api_key)  # ← 固定連 OpenAI 官方
    ...
```

**結論：不原生支援 `base_url`。**

### Patch 方案

只需在 `__init__` 加一個 `base_url` 引數：

```python
def __init__(
    self,
    api_key: Optional[str] = None,
    model: str = "whisper-1",
    base_url: Optional[str] = None,  # ← 新增
) -> None:
    self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
    self._model = model
    self._base_url = base_url  # ← 儲存

def transcribe(self, audio, sr=16000, language=None) -> str:
    client_kwargs = {"api_key": self._api_key}
    if self._base_url:
        client_kwargs["base_url"] = self._base_url  # ← 傳遞
    client = OpenAI(**client_kwargs)
    ...
```

OpenAI SDK 原生支援 `base_url` 引數，這樣就能連任何 OpenAI 相容 API（包含 Breeze-ASR-26 的 `http://localhost:8750/v1`）。

### 使用流程（Patch 後）

```python
from voicetag import VoiceTag, VoiceTagConfig

vt = VoiceTag(config=VoiceTagConfig(device='cuda'))

# Enroll 講者
vt.enroll("黃", ["test-audio/黃.wav"])
vt.enroll("文", ["test-audio/文.wav"])

# Transcribe → 誰說了什麼
result = vt.transcribe(
    'test-audio/meeting.wav',
    provider='openai',
    api_key='token-abc123',
    model='MediaTek-Research/Breeze-ASR-26',
    base_url='http://localhost:8750/v1',
    language='zh',
)

# 結果
for seg in result.segments:
    print(f"[{seg.speaker}] {seg.start:.1f}s - {seg.end:.1f}s: {seg.text}")
```

### 支援的 Providers

| Provider | 安裝方式 | 說明 |
|----------|---------|------|
| `openai` | `voicetag[openai]` | OpenAI Whisper API |
| `groq` | `voicetag[groq]` | Groq 快速 Whisper |
| `fireworks` | `voicetag[fireworks]` | Fireworks AI |
| `whisper` | `voicetag[whisper]` | 本機 Whisper（不需 API key） |
| `deepgram` | `voicetag[deepgram]` | Deepgram |

## Follow-up

- [ ] Patch `serve/voicetag/.venv/lib/python3.12/site-packages/voicetag/providers/openai_stt.py` 加入 `base_url`
- [ ] 用 `meeting.wav` 完整跑一次 transcribe 測試
- [ ] 將結果輸出為 JSON，確認格式符合需求

## References

- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)
- [voicetag PyPI](https://pypi.org/project/voicetag/)
- [64_2026_07_31_agent_vllm-breeze-asr26-installation-and-stt-testing](./64_2026_07_31_agent_vllm-breeze-asr26-installation-and-stt-testing.md)
- [63_2026_07_31_agent_voicetag-meeting-test-and-enrollment](./63_2026_07_31_agent_voicetag-meeting-test-and-enrollment.md)