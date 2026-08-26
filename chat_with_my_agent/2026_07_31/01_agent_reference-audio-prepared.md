---
created: 2026-07-31
author: Vincent
type: agent
status: final
tags: [test-audio, ffmpeg, reference]
---

# 2026-07-31 備妥測試用參考音訊

## What

將 `2026_07_21_test.mp3` 裁剪出 28.750s ~ 36.618s 的純老闆聲音片段，作為測試程式的 voice reference。

## Why

測試程式需要一段短音訊作為 speaker reference，用於 voiceprint / diarization 的驗證。

## How

- 複製原始音檔至 `test-audio/`：`cp ~/檔案/AudioRecording/2026_07_21_test.mp3 test-audio/`
- 使用 ffmpeg 裁剪：`ffmpeg -y -i test-audio/2026_07_21_test.mp3 -ss 28.750 -to 36.618 -c:a libmp3lame -q:a 2 test-audio/boss-reference.mp3`
- 結果：`boss-reference.mp3`（196 KB，約 7.8 秒）

## Follow-up

使用 `boss-reference.mp3` 進行 speaker embedding 提取測試。

## References

- [test-audio/boss-reference.mp3](../../test-audio/boss-reference.mp3)