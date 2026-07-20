---
created: 2026-06-07
author: Agent
type: agent
status: final
tags: [test-video, frame-extraction, opencv]
---

# 測試影片 `2026_05_11-19_18_26.mkv` 規格

## What

測試用影片 `2026_05_11-19_18_26.mkv` 的基本規格分析，以及 frame extraction 測試。

## Why

Video2Text 系統需要處理實際影片輸入。透過測試影片確認：
1. OpenCV 能否正常讀取影片格式（MKV）
2. 每分鐘約產生多少幀（決定 slice 密度）
3. Frame extraction 效能與輸出大小

## How

### 影片規格

```
Duration:  57.7 minutes (3463.1 seconds)
FPS:       60.0
Resolution: 1920 × 1082
Total frames: 207,785
```

### 按 1 FPS 抽幀的輸出

| 項目 | 數值 |
|------|------|
| 抽幀數 | ~5,770 幀 |
| 估算每幀大小 | ~100KB（壓縮 JPEG） |
| 總輸出大小 | ~570MB |

### 主程式測試模組

`main.py` 已更新為完整測試流程：
- GPU 硬體檢測（PyTorch + CUDA 資訊）
- vLLM 模型載入（`google/gemma-4-12B-it-qat-w4a16-ct`）
- 文字生成測試
- Frame extraction 測試（OpenCV → Pillow → JPEG）

## References

- [main.py](../main.py) — Console test
- [pyproject.toml](../pyproject.toml) — opencv-python-headless, imageio, imageio-ffmpeg
