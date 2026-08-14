---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [voicetag, long-audio, padding-fix, bug-fix, env-loader]
---

# VoiceTag 移除多餘 padding、修復 .env 載入、長音訊處理檔案

## What

1. 移除 `voicetag_core.py:identify()` 中不必要的 10s audio padding
2. 修復 `.env` 路徑解析 bug（`Path.resolve() / "../.env"` 無法正確 `exists()`）
3. 修復 `workflows/voicetag.py` 中 `OverlapSegment` 無 `confidence` 屬性的 bug
4. 更新 `.env.example` 加入 gated model 授權連結
5. 更新 `README.md` 加入長音訊支援說明

## Why

**Padding 移除**：VoiceTag 的 `Diarizer.diarize()` 直接傳檔案路徑給 pyannote Pipeline，pyannote 3.x 原生使用 30s sliding window with 15s stride 處理任意長度音訊。我們自己 padding 是多餘的，而且導致 `audio_duration` 不準確、segment 包含 padding 部分。

**.env 路徑 bug**：`Path(__file__).resolve() / "../.env"` 在 Linux 上 `exists()` 回傳 False，因為 `..` 在中間時不會被自動 canonicalize。改為 `Path(__file__).resolve().parent / ".env"`。

**OverlapSegment bug**：`OverlapSegment` Pydantic model 沒有 `confidence` 欄位，只有 `SpeakerSegment` 有。直接存取會拋 `AttributeError`。

**Gated model 連結**：使用者需要知道要接受哪些模型的授權才能使用 pyannote。

## How

### 1. 移除 padding（`serve/voicetag/voicetag_core.py`）

**之前**（多餘邏輯）：
```python
y, sr = librosa.load(str(audio), sr=48000, mono=True)
original_samples = len(y)

required_samples = sr * 10  # one chunk
n_chunks = max(1, int(len(y) / required_samples) + ...)
pad_size = n_chunks * required_samples - len(y)
if pad_size > 0:
    y = np.pad(y, (0, pad_size), mode="constant")

original_duration = original_samples / sr
```

**之後**（簡化）：
```python
y, sr = librosa.load(str(audio), sr=48000, mono=True)
original_duration = len(y) / sr
# 直接存 WAV，不 padding
sf.write(tmp.name, y, sr, format="WAV")
```

同時移除不需要的 `import numpy as np`。

### 2. 修復 .env 路徑（`serve/voicetag/voicetag_core.py:14`）

```diff
- _ENV_LOADER = Path(__file__).resolve() / "../.env"
+ _ENV_LOADER = Path(__file__).resolve().parent / ".env"
```

驗證：
```
$ ls -la serve/voicetag/.env
-rw-rw-r-- 1 freespace freespace  149  7月 31 17:08 .env
$ HF_TOKEN env: hf_pDCyCpx...  ✅
```

### 3. 修復 OverlapSegment（`workflows/voicetag.py:76-90`）

```python
for seg in result.segments:
    segment = {"start": ..., "end": ..., "duration": ..., "speaker": ...}
    if hasattr(seg, "speakers") and seg.speakers:
        segment["speakers"] = seg.speakers
        segment["type"] = "OVERLAP"
    elif hasattr(seg, "confidence"):
        segment["confidence"] = round(seg.confidence, 4)
        segment["type"] = "SPEAKER"
    else:
        segment["type"] = "SPEAKER"
```

### 4. 更新 `.env.example`

```
# Required models (accept license at links below):
# 1. pyannote/speaker-diarization-3.1  →  https://huggingface.co/pyannote/speaker-diarization-3.1
# 2. pyannote/segmentation-3.0         →  https://huggingface.co/pyannote/segmentation-3.0
```

### 5. 更新 `README.md`

- 修正 CLI 指令（`-m workflows.voicetag` → `workflows/voicetag.py`）
- 移除不存在的 `--threshold` 引數
- 新增「長音訊支援」章節，說明 pyannote 30s sliding window 機制

## Follow-up

- [ ] 用更長的音訊檔案測試（5 分鐘+），確認 sliding window 處理正常
- [ ] 確認 `output/voicetag/result_new.json` 的 segment 結果與舊版 `result.json` 的差異是否在預期範圍內

## References

- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)
- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py)
- [workflows/voicetag.py](../../workflows/voicetag.py)
- [serve/voicetag/README.md](../../serve/voicetag/README.md)
- [61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing](./61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing.md)