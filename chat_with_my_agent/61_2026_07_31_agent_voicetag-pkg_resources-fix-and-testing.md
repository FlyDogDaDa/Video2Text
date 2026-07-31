---
created: 2026-07-31
author: Vincent
type: agent
status: completed
tags: [voicetag, speaker-diarization, pkg_resources, MP3-conversion, Pydantic-frozen]
---

# 修復 VoiceTag 測試管线：pkg_resources 相容性、MP3 編碼支援、Frozen Pydantic 問題

## What

修復 `serve/voicetag/` 模組的三個關鍵問題，使完整測試管线（Enroll → Save → Identify → JSON）成功運行。

## Why

先前實作的 VoiceTag 模組因以下三個問題導致測試腳本失敗：
1. `setuptools >= 70` 移除了 `pkg_resources` 模組，導致 `webrtcvad`（resemblyzer 的間接相依性）無法匯入
2. `soundfile` 不支援 MP3 格式，enroll 階段無法讀取 `.mp3` 檔案
3. voicetag 庫的回傳物件（`DiarizationResult`、`SpeakerSegment`）是 frozen Pydantic model，無法直接修改

## How

### 1. 修復 `pkg_resources` 相容性

**問題**：`setuptools 83.0.0` 移除了 `pkg_resources`，但 `webrtcvad` 仍使用它。

**解法**：降級 setuptools 至 `<70`：
```bash
serve/voicetag/.venv/bin/python -m pip install "setuptools<70"
```
安裝成功後 `pkg_resources` 可正常匯入（含 DeprecationWarning）。

**注意**：torch 2.13.0 要求 `setuptools>=77.0.3`，降級會產生 version conflict warning，但不影響執行期行為。

### 2. 新增 MP3→WAV 轉換輔助函式

**問題**：`soundfile`（voicetag 內部使用的音訊讀取庫）不支援 MP3。`identify()` 已有透過 librosa 轉 WAV 的 workaround，但 `enroll()` 沒有。

**解法**：在 `voicetag_core.py` 新增兩個公開函式：

- `_convert_to_wav(audio_path, target_sr=16000) → Path`
  使用 librosa 讀取任意支援格式（MP3/FLAC/OGG/M4A），透過 ffmpeg 解碼，寫入暫存 WAV 檔。

- `enroll(name, audio_paths, hf_token, device) → tuple[str, list[str]]`
  自動將所有輸入音訊轉為 WAV 後傳給 voicetag，並清理暫存檔案。

```python
def enroll(name: str, audio_paths: list[str | Path], ...) -> tuple[str, list[str]]:
    wav_paths = []
    temp_files = []
    try:
        for ap in audio_paths:
            wav_path = _convert_to_wav(ap, target_sr=16000)
            if wav_path != ap:
                temp_files.append(wav_path)
            wav_paths.append(str(wav_path))
        vt = _ensure_voicetag(hf_token=hf_token, device=device)
        vt.enroll(name, wav_paths)
        return (name, wav_paths)
    finally:
        for tf in temp_files:
            tf.unlink(missing_ok=True)
```

### 3. 處理 Frozen Pydantic Model 限制

**問題**：voicetag 庫回傳的 `DiarizationResult`、`SpeakerSegment`、`VoiceTagConfig` 都是 frozen Pydantic model，無法直接修改屬性。

**解法**：使用 `object.__setattr__()` 繞過 frozen 檢查：

```python
# 修正 audio_duration（pyannote 報告的是 padded 後的長度）
object.__setattr__(result, "audio_duration", original_duration)
```

同時移除不支援的 `threshold` 參數（`VoiceTagConfig` 是 frozen，無法執行期修改）。

### 4. 修正原始長度記錄時機

`original_duration` 在 `np.pad()` 之後計算會包含 padding 樣本。改為先記錄 `original_samples`：

```python
original_samples = len(y)  # padding 前
# ... padding ...
original_duration = original_samples / sr
```

### 5. 測試結果

完整 pipeline 在 GPU（cuda:0）上成功運行：

```
音訊：test-audio/2026_07_21_test.mp3（120s，2.9 MB）
處理時間：8.8s
輸出：32 個分段，10 個識別為 'boss'，3 個 overlap 分段
```

Boss 說話人識別 confidence 範圍：0.76 ~ 0.98。

## Follow-up

- [ ] 測試 API endpoint（`python serve/voicetag/server.py` + `curl`）
- [ ] 使用 boss-reference（28.75s-36.618s 片段）測試更精確的說話人匹配
- [ ] 評估不同音訊長度的效能
- [ ] `serve/voicetag/api/service.py` 需同步更新（移除 `threshold` 參數傳遞）

## References

- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py)
- [test_voicetag.py](../../test_voicetag.py)
- [workflows/voicetag.py](../../workflows/voicetag.py)
- [output/voicetag/result.json](../../output/voicetag/result.json)
- [output/voicetag/profiles.json](../../output/voicetag/profiles.json)
- [voicetag GitHub](https://github.com/Gr122lyBr/voicetag)
- [setuptools pkg_resources deprecation](https://setuptools.pypa.io/en/latest/pkg_resources.html)