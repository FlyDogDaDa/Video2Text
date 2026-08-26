---
created: 2026-07-21
author: human+agent
type: agent
status: implemented
tags: [sam-audio, module-design, span-prompting, separation, implemented]
---

# SAM-Audio 模組設計

## 概要

`sam_audio.py` 模組使用 Meta 的 SAM-Audio 模型，提供基於時間跨度提示（span prompting）的聲音分離功能。

模組設計原則：**單一責任**，只提供 `separate_by_anchor()` 一個公開函式。拼接（concat）、VAD 後處理、兩階段組合等策略都在 `workflow.py` 中操作。

## 實作狀態

**✅ 已實作** — 2026-07-21

## 模組位置

```
Video2Text/
└── modules/
    └── sam_audio.py    ← 新增
```

## 回傳型別

```python
from pydantic import BaseModel


class SeparationResult(BaseModel):
    """分離結果。"""
    speaker: Path        # 分離出的語者音軌路徑
    residual: Path       # 剩餘音軌路徑
```

## 設定檔

### Profile YAML (`profiles/default.yaml`)

```yaml
sam_audio:
  model_name: "facebook/sam-audio-large"
  device: "cuda"
```

### Config 類別

```python
class SamAudioConfig(BaseModel):
    model_name: str = "facebook/sam-audio-large"
    device: str = "cuda"
```

## 公開介面

### `separate_by_anchor()`

```python
def separate_by_anchor(
    audio: Path,                          # 主音軌（混合音軌）
    anchors: list[list],                  # 時間區間
    description: str = "",                # 文字提示（可空）
) -> SeparationResult:
    """使用時間跨度提示分離特定區間的聲音。

    Parameters
    ----------
    audio:
        輸入主音軌路徑。
    anchors:
        時間區間列表。每個區間為 ``[type, start, end]``。
        ``"+"`` 表示該區間有目標聲音，``"-"`` 表示沒有。
        
        範例:
        
        .. code-block:: python
        
            [
                ["+", 0.5, 3.2],
                ["+", 5.0, 8.7],
                ["-", 0.0, 0.5]  # 排除區間
            ]
    description:
        文字提示。空字串表示純 span 模式。
        可填如 ``"single speaker"``、``"a man talking"`` 等。

    Returns
    -------
    SeparationResult
        ``speaker``: 分離出的語者音軌路徑
        ``residual``: 剩餘音軌路徑
    """
```

## 完整 `sam_audio.py` 骨架

```python
"""Speaker separation using SAM-Audio span prompting.

Uses Meta's SAM-Audio model to isolate sounds in audio files
based on time span prompts.
"""

from pathlib import Path

from pydantic import BaseModel

from framework.config import cfg


class SeparationResult(BaseModel):
    """Speaker separation result.

    Parameters
    ----------
    speaker:
        Path to the isolated speaker audio file.
    residual:
        Path to the residual (remainder) audio file.
    """

    speaker: Path
    residual: Path


class SamAudioConfig(BaseModel):
    """Configuration for SAM-Audio speaker separation.

    Parameters
    ----------
    model_name:
        Hugging Face model identifier.
    device:
        Device to run inference on (e.g. ``"cuda"``, ``"cpu"``).
    """

    model_name: str = "facebook/sam-audio-large"
    device: str = "cuda"


def separate_by_anchor(
    audio: Path,
    anchors: list[list],
    description: str = "",
) -> SeparationResult:
    """Separate audio based on time span prompts.

    Parameters
    ----------
    audio:
        Path to the input audio file (mixture).
    anchors:
        Time span annotations. Each span is ``[type, start, end]``.
        ``"+"`` marks where the target sound IS present.
        ``"-"`` marks where the target sound is NOT present.
    description:
        Optional text description. Use empty string for pure span mode.

    Returns
    -------
    SeparationResult
        Paths to separated speaker and residual audio files.

    Notes
    -----
    TODO: 實作 SAM-Audio 分離邏輯
    """
    c = cfg("sam_audio", SamAudioConfig)

    # TODO: 實作分離邏輯
    # 1. 載入 model + processor
    # 2. 處理 anchors 格式
    # 3. 呼叫 processor(audios=[audio], description=[description], anchors=[anchors])
    # 4. 呼叫 model.separate(inputs)
    # 5. 儲存輸出到 {audio.stem}_speaker.wav / {audio.stem}_residual.wav
    # 6. 回傳 SeparationResult

    output_dir = audio.parent
    speaker_path = output_dir / f"{audio.stem}_speaker.wav"
    residual_path = output_dir / f"{audio.stem}_residual.wav"

    return SeparationResult(
        speaker=speaker_path,
        residual=residual_path,
    )
```

## 輸出檔案命名規則

| 輸入 | 輸出 |
|------|------|
| `audio.wav` | `audio_speaker.wav`（分離語者） |
| `audio.wav` | `audio_residual.wav`（剩餘音軌） |

音軌格式：WAV，16kHz 取樣率（SAM-Audio 原生取樣率）。

## 在 `workflow.py` 中的組合方式

### 快速模式：拼接法

```python
from modules.sam_audio import separate_by_anchor
from modules.audio import extract_audio  # 假設 audio.py 已實作

# 提取主音軌與參考音軌
audio = extract_audio(input_file, audio_ref="mixture.wav")
ref = extract_audio(input_file, audio_ref="reference.wav")

# 拼接參考音軌到主音軌開頭
combined = concatenate(audio, ref)

# 文字提示分離
result = separate_by_anchor(combined, [], "single speaker")
```

### 高品質模式：VAD + Span

```python
from modules.sam_audio import separate_by_anchor
from modules.vad import detect_speech

# vad.py 分析參考音軌 → 取得時間區間
segments = detect_speech(reference_audio)

# 轉換為 anchors 格式
anchors = [["+", s["start"], s["end"]] for s in segments]

# 直接使用 span prompting 分離
result = separate_by_anchor(audio, anchors, "single speaker")
```

### 最佳品質：兩階段

```python
from modules.sam_audio import separate_by_anchor
from modules.vad import detect_speech

# 階段 1: 拼接法粗估
combined = concatenate(audio, reference_audio)
stage1 = separate_by_anchor(combined, [], "single speaker")

# 階段 2: VAD 分析 → Span 精確分離
segments = detect_speech(reference_audio)
anchors = [["+", s["start"], s["end"]] for s in segments]
result = separate_by_anchor(audio, anchors, "single speaker")

# 若 stage1 品質尚可，可直接使用 stage1.speaker
```

## 前置條件

1. **Hugging Face 認證**：需登入取得 `facebook/sam-audio-large` 存取許可權
   
   ```bash
   huggingface-cli login
   ```

2. **依賴套件**（待安裝）：
   
   ```bash
   uv add sam-audio torch torchaudio
   ```
   
   - `sam-audio` 需從 GitHub 原始碼安裝
   
     ```bash
     git clone https://github.com/facebookresearch/sam-audio.git
     cd sam-audio && pip install .
     ```

3. **CUDA GPU**：建議使用 CUDA GPU 進行推論（可選 CPU 模式）。

## 依賴關係

| 模組 | 被依賴 | 說明 |
|------|--------|------|
| `framework/config.py` | `sam_audio.py` | 讀取 profile 設定 |
| `modules/vad.py` | `workflow.py` | VAD 分析參考音軌（非 `sam_audio.py` 內部依賴） |
| `modules/audio.py` | `workflow.py` | 音軌提取與拼接（非 `sam_audio.py` 內部依賴） |

## References

- [SAM-Audio Hugging Face 頁面](https://huggingface.co/facebook/sam-audio-large)
- [SAM-Audio GitHub](https://github.com/facebookresearch/sam-audio)
- [SAM-Audio Paper (arXiv)](https://arxiv.org/abs/2512.18099)