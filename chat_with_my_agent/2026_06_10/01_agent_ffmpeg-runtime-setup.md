---
created: 2026-06-10
author: Agent
type: agent
status: draft
tags: [ffmpeg, ffprobe, runtime, static-binaries, imageio-ffmpeg]
---

# FFmpeg runtime setup — symlink from imageio-ffmpeg + download ffprobe

## What

將 FFmpeg 系列工具部署到 `runtime/` 資料夾，供專案使用。

## Why

專案使用 `imageio-ffmpeg` 作為影片處理依賴，但其內建套件只包含 ffmpeg 執行檔，沒有 ffprobe。專案需要兩者來提取影片規格、幀數、FPS 等元資料。使用者沒有系統安裝許可權，需要無安裝部署（no-install）方案。

## How

### 1. 確認環境

- 作業系統：Debian Linux (6.1.0-27-amd64), x86_64
- Python 3.12, uv 管理虛擬環境
- `imageio-ffmpeg 0.6.0` 已安裝在 `.venv` 內

### 2. FFmpeg 來源說明

`imageio-ffmpeg 0.6.0` 內建了靜態編譯的 ffmpeg，**未** 包含 ffprobe。但專案的 FFmpeg 和 ffprobe 最終都來自同一個 FFmpeg 7.0.2 release tarball（johnvansickle 靜態包），一次性下載後解壓縮，將 ffmpeg 和 ffprobe 直接移動到 `runtime/`。

這樣做的好處：
- ffmpeg 和 ffprobe 版本一致（都是 7.0.2）
- `runtime/` 獨立存在，不依賴 `.venv` 目錄結構
- 免 symlink，移動即用

### 3. 下載 FFmpeg 7.0.2 release（含 ffprobe）

`imageio-ffmpeg` 不包 ffprobe。從 [johnvansickle.com](https://johnvansickle.com/ffmpeg/) 下載官方靜態包：

```bash
wget -O /tmp/ffmpeg-release-amd64-static.tar.xz \
  https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf /tmp/ffmpeg-release-amd64-static.tar.xz -C /tmp/
```

解壓縮後內容：
```
/tmp/ffmpeg-7.0.2-amd64-static/
├── ffmpeg          # 77 MB
├── ffprobe         # 76 MB
└── qt-faststart    # 679 KB  （不需要，已刪除）
```

將 ffmpeg 和 ffprobe 直接移動到 `runtime/`（非 symlink，因為這是全新檔案）。

### 4. 最終 `runtime/` 內容

| 檔案 | 來源 | 版本 | 大小 |
|------|------|------|------|
| ffmpeg | FFmpeg 7.0.2 release tarball | 7.0.2 | 76 MB |
| ffprobe | FFmpeg 7.0.2 release tarball | 7.0.2 | 76 MB |

兩者都驗證過可執行：
```
ffmpeg version 7.0.2-static
ffprobe version 7.0.2-static
```

### 5. 清理

- 刪除 `qt-faststart`（專案不需要）
- 刪除下載的 `.tar.xz` 和解壓縮資料夾

## Follow-up

- 後續如需引用 FFmpeg/ffprobe，指向 `runtime/ffmpeg` 和 `runtime/ffprobe`
- 若有需要新增 `ffplay` 或其他子工具，可從同一個靜態包獲取

## References

- [runtime/ffmpeg](../runtime/ffmpeg)
- [runtime/ffprobe](../runtime/ffprobe)
- [.venv/lib/.../imageio_ffmpeg/binaries/](../.venv/lib/python3.12/site-packages/imageio_ffmpeg/binaries/)
- [19_2026_06_10_agent_slice-utils-implementation.md](./19_2026_06_10_agent_slice-utils-implementation.md) — 同天的 slice utilities 實作
