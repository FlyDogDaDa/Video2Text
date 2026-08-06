---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [voicetag, long-audio, meeting-meeting, reference-audio, enrollment]
---

# VoiceTag 長音訊測試 — 40 分鐘會議完整推理

## What

1. 將 `~/文件/AudioRecording/保修工程會議.m4a` 轉為 WAV 放入 `test-audio/`
2. 裁剪 4 位 speaker 參考片段（21~37 秒區間）
3. Enroll 4 位說話人 → 跑完整會議 → 產出 JSON

## Why

- 測試 VoiceTag 對長時間音訊（40 分鐘）的實際處理能力
- 驗證 pyannote sliding window 是否穩定
- 不同長度 reference 對 enrollment 品質的影響
- 為後續老闆安排獨立錄音提供資料

## How

### 1. 檔案轉換

**原始檔**：`保修工程會議.m4a`
- 實際長度：**2404.87 秒（~40 分鐘）**，非 2 小時
- 格式：AAC 編碼

**轉換後**：`test-audio/保修工程會議.wav`
- 48kHz / 16-bit / mono / PCM
- 大小：221 MB

```bash
ffmpeg -i 保修工程會議.m4a -ar 48000 -ac 1 -c:a pcm_s16le 保修工程會議.wav
```

### 2. 參考片段裁剪

裁剪時間區間（來自已有註記）：

| Speaker | 起始 | 結束 | 長度 | 大小 | 狀態 |
|---------|------|------|------|------|------|
| 黃 | 28.750s | 36.618s | 7.868s | 246 KB | ✅ 足夠 |
| 文 | 41.898s | 46.723s | 4.825s | 151 KB | ✅ 可用 |
| 陳 | 21.478s | 22.075s | 0.597s | 11 KB | ⚠️ 太短 |
| 婕 | 50.707s | 51.044s | 0.337s | 11 KB | ⚠️ 太短 |

```bash
ffmpeg -i 保修工程會議.wav -ss <start> -to <end> -ar 16000 -ac 1 -c:a pcm_s16le <speaker>.wav
```

### 3. 推理

```python
from voicetag_core import enroll, identify

# Enroll 4 speakers
for name, paths in SPEAKERS.items():
    enroll(name, paths, device="cuda:0")

vt.save(str(PROFILES_JSON))

# Full meeting identification
result = identify(
    audio_path="test-audio/保修工程會議.wav",
    profile_path=str(PROFILES_JSON),
    device="cuda:0",
)
```

### 4. 結果

| 項目 | 數值 |
|------|------|
| 音訊長度 | 2404.9s（40.1 min） |
| 處理時間 | 120.5s（~2 min） |
| 總 segments | 813（100 個 overlap） |

**說話人分佈**：

| 說話人 | Segments | 狀態 |
|--------|----------|------|
| 黃 | 236 | 參考最長，辨識最佳 |
| 文 | 59 | 可用 |
| 陳 | 47 | 參考短但仍有辨識 |
| 婕 | 6 | 參考極短，幾乎未辨識 |
| UNKNOWN | 365 | 未 enrollment |

**Timecode 交叉比對**：

| 說話人 | 已知時間 | 辨識結果 |
|--------|---------|---------|
| 黃 | 28.8~36.6s | 3/3 全中 |
| 文 | 41.9~46.7s | 文、黃混合（可能 overlap） |
| 陳 | 21.5~22.1s | 黃 / 陳混合 |
| 婕 | 50.7~51.0s | 0 segments（<0.4s） |

## Follow-up

- [ ] 通知老闆安排每人 3~5 秒以上的獨立錄音（你好、自我介紹）
- [ ] 補充婕、陳的 longer reference，提升 enrollment 品質
- [ ] 探索 UNKNOWN segments 的說話人 — 也許可以新增更多 speaker profile

## References

- [62_2026_07_31_agent_voicetag-long-audio-and-padding-fix](./62_2026_07_31_agent_voicetag-long-audio-and-padding-fix.md)
- [61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing](./61_2026_07_31_agent_voicetag-pkg_resources-fix-and-testing.md)
- [test_voicetag_meeting.py](../../test_voicetag_meeting.py)
- [output/voicetag/meeting_result.json](../../output/voicetag/meeting_result.json)
- [output/voicetag/meeting_profiles.json](../../output/voicetag/meeting_profiles.json)
- [serve/voicetag/README.md](../../serve/voicetag/README.md)