---
created: 2026-08-27
author: agent
type: agent
tags: [keyframe, gop, video-editing, deviation, video2text]
---

# 步驟 6 偏離：keyframe GOP 實測 6.0s，`-c copy` 起點不精確

## What

- 量測 composite.mkv 的 keyframe：全片 940 個 keyframe，間隔**固定 6.0 秒**。
- `-c copy` 試切零長「對」@675.87（raw 窗口 675.63→675.87，0.24s）：
  實際產出 3.9s 片段，起點被拉回前一個 keyframe 672.0（lead-in 3.63s），
  音畫互相同步、目標內容在片尾 0.24s。
- 43 個零長「對」詞 raw 審計：33 個有可用 raw 窗口（0.08–0.32s）、
  9 個 raw 也是反轉、1 個 raw 異常（1.44s）。
- **偏離判定**：TODO 假設 `-c copy` 偏差 0.1–0.5s，本片最壞 6s，不成立。
  依偏離規則停下，向使用者說明並等定案。

## Why

- 步驟 6 目標是「精準剪出」肯定詞片段；起點偏 3.6–6s 會把前一句内容剪進來，
  與「只取肯定單字片段」的目標直接衝突，必須在寫 `edit_video.py` 前定案策略。

## How

- ffprobe 掃 packets 的 K flag 統計 GOP（940 keyframes / 固定 6.0s）。
- 試切：`ffmpeg -ss 675.63 -i N9boWvU-KkA_composite.mkv -t 0.24 -c copy tmp/test_clip_copy.mkv`，
  再以 ffprobe 回讀容器時長、首末 pts、音畫幀數，證據存 assets。
- 零長審計：讀 `filtered_aligned.json` 中 43 個 start_s==end_s 的詞樣本，
  比對 `start_s_raw`/`end_s_raw` 分三組（可用 raw / raw 反轉 / raw 異常）。

## Follow-up

- [ ] 使用者定案：A（維持 `-c copy`，容忍 lead-in）vs B（逐片重編碼，幀精確，agent 推薦）vs C（混合）
- [ ] 定案後寫 `scripts/edit_video.py`；零長政策暫定：33 個用 raw 窗口、10 個用 T±0.2s
- [ ] 切完抽 1–2 段目檢音畫同步後再全量

## Uncertainty

- 選項 B 重編 334 片（AV1 解碼→H.264 crf18）預估 5–15 分鐘，未實測。
- 零長政策（33 raw + 10 T±0.2s）是暫定，未與使用者確認。

## References

- [討論細節（含 ffprobe/ffmpeg 指令與試切數據）](references/04_agent_step6-keyframe-gop-deviation.md)
- [試切報告](assets/step6-keyframe-gop/test-clip-copy-report.json)
- [TODO 步驟 6](../../exp/N9boWvU-KkA/TODO.md)（exp/ 下，不入 git）
