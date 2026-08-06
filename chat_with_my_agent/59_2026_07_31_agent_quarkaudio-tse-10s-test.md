---
created: 2026-07-31
author: Vincent
type: agent
status: final
tags: [quark-audio, tse, ffmpeg, testing]
---

# 使用 10 秒裁切音訊測試 QuarkAudio-UniSE TSE

## What

- 使用 ffmpeg 從原始 120 秒音訊裁切 30s~40s 共 10 秒作為新的測試混合音訊
- 使用裁切後的音訊重新執行 TSE 推理
- 將 `output/` 目錄加入 `.gitignore`

## Why

根據官方 demo 建議，10 秒音訊是最適合的測試長度。原始 120 秒音訊也能運行，但 10 秒更貼近實際使用場景。

## How

1. **裁切音訊：**
   ```bash
   ffmpeg -i 2026_07_21_test.mp3 -ss 00:00:30 -t 10 -acodec libmp3lame -ab 192k -vn 2026_07_21_test_30s.mp3
   ```

2. **更新 `workflows/quark-audio.py` 測試路徑：**
   - 將 `mix_path` 改為 `test-audio/2026_07_21_test_30s.mp3`

3. **執行推理：** 成功輸出 10 秒 WAV（313KB, 16kHz mono）

4. **`.gitignore`：** 新增 `output/` 到 `# Output directories` 區段

## Follow-up

- 測試不同長度的音訊（>5s 分段推理、<5s 短音訊）
- 評估輸出音訊品質（需要實際聆聽）
- 封裝為 HTTP API endpoint

## References

- [serve/quark-audio/quark_audio/api.py](../../serve/quark-audio/quark_audio/api.py)
- [workflows/quark-audio.py](../../workflows/quark-audio.py)
- [QuarkAudio-UniSE GitHub](https://github.com/alibaba/unified-audio)