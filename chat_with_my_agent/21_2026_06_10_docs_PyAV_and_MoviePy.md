# PyAV 與 MoviePy 關聯性與進階 FX 深度研究

> 日期：2026-06-10
> 作者：Zed Coding Agent

---

## 目錄

1. [MoviePy 與 PyAV 的核心關係](#1moviepy-與-pyav-的核心關係)
2. [MoviePy 兩種後端架構對比](#2moviepy-兩種後端架構對比)
3. [PyAV 與 FFmpeg 架構定位](#3pyav-與-ffmpeg-架構定位)
4. [libavfilter 過濾器完整分類目錄](#4libavfilter-過濾器完整分類目錄)
5. [PyAV Filter Graph 進階應用](#5pyav-filter-graph-進階應用)
6. [PyAV + NumPy 每幀像素操控](#6pyav--numpy-每幀像素操控)
7. [PyAV + CuPy GPU 加速特效](#7pyav--cupy-gpu-加速特效)
8. [三層混合架構：PyAV + FFmpeg CLI + MoviePy](#8三層混合架構pyav--ffmpeg-cli--moviepy)
9. [效能優化建議](#9效能優化建議)
10. [總結：複雜度階梯](#10總結複雜度階梯)

---

## 1. MoviePy 與 PyAV 的核心關係

### 1.1 兩者定位差異

| 特性 | MoviePy | PyAV |
|---|---|---|
| **技術本質** | 高階影片剪輯框架，預設透過子進程呼叫 FFmpeg | 低階 FFmpeg C API 的 Cython 綁定庫 |
| **數據模型** | 全域處理 NumPy 陣列 (H×W×3) | 直接操作 Container、Packet、Frame、Stream |
| **擅長領域** | 剪切、多軌混音、字幕、圖層疊加、特效 | 精確解碼、即時串流、自訂編碼參數 |
| **執行方式** | 傳統方式啟動 FFmpeg 命令行子進程 | 直接載入 FFmpeg 共享庫進記憶體 |
| **效能表現** | 較高 I/O 開銷（進程間管道） | 極快（記憶體內直接操作） |

### 1.2 核心關係：MoviePy 的替代後端

在 **MoviePy 2.x** 中，PyAV 被引入為**另一個影片讀取的後端選項**：

```
┌─────────────────────────────────────────────────┐
│                  MoviePy Clip                     │
└──────────┬──────────────────────┬────────────────┘
           ▼                      ▼
┌────────────────────┐  ┌────────────────────┐
│ FFmpeg 子進程模式  │  │   PyAV 後端模式    │
│ (預設 / Legacy)    │  │   (Optional)       │
├────────────────────┤  ├────────────────────┤
│ 啟動 ffmpeg.exe    │  │  載入 libavcodec   │
│ OS 管道傳輸原始    │  │  libavformat       │
│ 位元資料           │  │  libavfilter       │
│ 解析 stderr 文字   │  │  直接記憶體映射     │
│ 序列化/反序列化    │  │  零拷貝 NumPy 轉換 │
└────────────────────┘  └────────────────────┘
```

### 1.3 選擇 PyAV 後端的優勢

| 優勢 | 說明 |
|---|---|
| **速度** | 大型影片的精確搜尋更快，沒有管道瓶頸 |
| **VFR 支援** | 變更動幀率（Variable Frame Rate）影片不會有音視訊漂移 |
| **精確度** | 直接存取低階中繼資料、封包串流、多軌音訊路由 |
| **錯誤處理** | 損壞幀以 Python 例外處理，可優雅跳過而非子進程崩潰 |
| **零拷貝** | 解碼記憶體直接映射到 NumPy，不需管道傳輸 |

### 1.4 潛在缺點

| 考量 | 說明 |
|---|---|
| **安裝複雜度** | 需要與 FFmpeg 匹配的 C 編譯輪（wheel），不像預設模式自動下載 |
| **平台相容性** | 某些平台上 PyAV 輪可能較難安裝或版本不匹配 |

### 1.5 為什麼選擇 PyAV 後端？（詳細對比）

| Feature | Legacy FFmpeg Subprocess | PyAV Backend |
|---|---|---|
| **Execution** | External CLI Subprocess | Direct C Shared Libraries |
| **Memory Sync** | Heavy OS Pipe I/O | Direct Pointer Mapping to NumPy |
| **VFR Stability** | Prone to audio/video drift | High precision via PTS tracking |
| **Installation** | Seamless (auto-downloads) | Complex (matched C-binary wheels) |

---

## 2. MoviePy 兩種後端架構對比

### 2.1 傳統方式：FFmpeg 子進程模式

```
[ MoviePy Clip ] --> [ 啟動 ffmpeg.exe ] --> [ OS Pipe ] --> [ FFmpeg 解碼 ]
                          │                        │
                          ▼                        ▼
                   寫入 CLI 命令            解析 stderr 文字
                   等待 stdout 位元流      序列化/反序列化開銷
```

**工作流程：**
1. MoviePy 組建 FFmpeg CLI 命令
2. 啟動獨立的 `ffmpeg.exe`（或 `ffmpeg`）子進程
3. 透過 OS 管道傳輸原始位元資料
4. 解析 stderr 文字輸出以提取中繼資料
5. 等待管道傳輸完整幀位元流

**缺點：**
- 子進程啟動與管理開銷
- OS 管道 I/O 瓶頸
- 序列化/反序列化延遲
- stderr 文字解析脆弱

### 2.2 PyAV 方式：直接 C-Bindings

```
[ MoviePy Clip ] --> [ PyAV Wrapper ] --> [ FFmpeg C-Libraries ]
                              │                      │
                              ▼                      ▼
                       精確 PTS 尋址          libavcodec/libavformat
                       零拷貝 NumPy 映射      記憶體內直接操作
```

**工作流程：**
1. MoviePy 請求特定時間 t 的幀
2. PyAV 使用原生 PTS（Presentation Timestamp）精確尋址到關鍵幀
3. 在記憶體中直接解碼封包
4. 將解碼資料零拷貝映射到 NumPy 陣列
5. MoviePy 直接操作 NumPy 陣列進行像素變換

**優勢：**
- 無子進程啟動開銷
- 記憶體內直接操作
- 精確時間戳追蹤
- Python 異常處理

---

## 3. PyAV 與 FFmpeg 架構定位

### 3.1 FFmpeg 架構層級

```
┌──────────────────────────────────────────────────────────┐
│                   Application Layer                       │
│              (MoviePy / PyAV / CLI ffmpeg)                │
├──────────────────────────────────────────────────────────┤
│                   libavfilter                             │
│              (Video/Audio Filters & Graph)                │
├──────────────────────────────────────────────────────────┤
│                   libavformat                             │
│          (Containers, Streams, Packets)                   │
├──────────────────────────────────────────────────────────┤
│                   libavcodec                              │
│        (Codecs: libavcodec, libswscale)                   │
├──────────────────────────────────────────────────────────┤
│                   libavutil                               │
│         (Utilities: Pixel formats, Time)                  │
├──────────────────────────────────────────────────────────┤
│                   Hardware Acceleration                   │
│          (NVDEC, NVENC, Vulkan, CUDA, VA-API)             │
└──────────────────────────────────────────────────────────┘
```

### 3.2 PyAV 綁定範圍

PyAV 提供 Pythonic 綁定到以下 FFmpeg 庫：

| FFmpeg Library | PyAV 對應 | 功能 |
|---|---|---|
| `libavformat` | `av.Container`, `av.Stream`, `av.Packet` | 容器、音訊/影片/字幕串流、封包 |
| `libavcodec` | `av.Codec`, `av.Context`, `av.Frame` | 解碼器、編碼器、幀資料平面 |
| `libavfilter` | `av.filter.Graph`, `av.filter.Filter` | 過濾器、過濾器圖譜 |
| `libswscale` | `av.VideoReformatter` | 影片重格式化（縮放、色彩空間轉換） |
| `libswresample` | `av.AudioResampler` | 音訊重取樣 |
| `libavdevice` | 需指定格式 | 裝置輸入/輸出（螢幕截圖、攝像頭） |

### 3.3 PyAV 核心 API

```python
import av

# 容器操作
container = av.open('input.mp4')
for stream in container.streams:
    print(stream.type, stream.codec_context)

# 串流解碼
for frame in container.decode(video=0):
    img = frame.to_ndarray(format='rgb24')  # NumPy 陣列

# 過濾器圖譜
graph = av.filter.Graph()
buffer_in = graph.add_buffer(template=video_stream)
graph.configure()
graph.push(frame)
processed = graph.pull()

# 編碼輸出
output = av.open('output.mp4', mode='w')
out_stream = output.add_stream('libx264', rate=fps)
for packet in out_stream.encode(frame):
    output.mux(packet)
output.close()
```

---

## 4. libavfilter 過濾器完整分類目錄

### 4.1 過濾器完整分類總表

#### 4.1.1 縮放、裁切與幾何變換

| 過濾器 | 功能 |
|---|---|
| `scale` | 使用軟體縮放調整影片尺寸 |
| `crop` | 裁切成指定的矩形區域 |
| `cropdetect` | 自動偵測黑色裁切邊界 |
| `pad` | 新增邊框（padding） |
| `transpose` | 旋轉 90/180/270 度或翻轉 |
| `vflip` / `hflip` | 垂直或水平翻轉 |
| `aspect` / `setdar` / `setsar` | 修改顯示或取樣長寬比 |
| `v360` | 360 度影片不同投影格式轉換（等距柱狀 → 立方體） |

#### 4.1.2 色彩、對比度與 LUT 調整

| 過濾器 | 功能 |
|---|---|
| `eq` | 調整亮度、對比度、飽和度、Gamma |
| `colorbalance` | 修改陰影、中間調、高Light 的 RGB 強度 |
| `colorchannelmixer` | 透過通道混合調整色彩配置文件 |
| `lut2` / `lut3d` | 套用 3D 查找表（LUT）進行電影級調色 |
| `colorspace` | 色彩標準轉換（BT.601, BT.709, BT.2020） |
| `hsvkey` / `hsvhold` | 基於 Hue/Saturation/Value 的範圍選色 |
| `grayworld` | 自動白平衡調整 |
| `curves` | 使用樣條曲線調整色彩分量 |

#### 4.1.3 模糊、銳化與降噪

| 過濾器 | 功能 |
|---|---|
| `boxblur` | 盒狀模糊演算法 |
| `avgblur` | 平均模糊 |
| `unsharp` | 非銳化遮罩（Unsharp Mask） |
| `atadenoise` | 自適應時間平均降噪 |
| `bm3d` | 3D 塊匹配匹配進階降噪 |
| `hqdn3d` | 高品質 3D 降噪 |
| `cas` | 對比度自適應銳化 |
| `varblur` | 變量模糊（使用二進制映射） |
| `deband` | 消除色彩帶狀偽影 |

#### 4.1.4 幀率、去隔行與時間操控

| 過濾器 | 功能 |
|---|---|
| `fps` | 強制特定常數幀率（丟幀或複製） |
| `framerate` | 使用場景偵測進行線性插值 |
| `minterpolate` | 運動補償幀插值（高品質慢動作） |
| `setpts` | 修改 Presentation Timestamp |
| `yadif` | 高品質自適應去隔行 |
| `bwdif` | 運動自適應去隔行 |
| `decimate` / `mpdecimate` | 丟棄相似幀 |
| `reverse` | 影片倒放 |

#### 4.1.5 混合、合成與字幕

| 過濾器 | 功能 |
|---|---|
| `overlay` | 將一個影片疊加在另一個之上 |
| `blend` | 使用自訂數學模式混合（Multiply, Screen, Overlay） |
| `alphaextract` / `alphamerge` | 提取或套用透明 Alpha 通道 |
| `drawtext` | 渲染文字字串或元數據疊加 |
| `drawbox` / `drawgrid` | 繪製矩形或網格 |
| `ass` / `subtitles` | 燒錄 ASS/SSA 或 SRT 字幕 |
| `xfade` | 過場轉場（Dissolve, Slide, Fade 等） |
| `chromakey` | 綠幕/藍幕抠像 |

#### 4.1.6 診斷、測試與元數據

| 過濾器 | 功能 |
|---|---|
| `showinfo` | 記錄每個影片幀的詳細中繼資料 |
| `blackdetect` / `blackframe` | 偵測純黑序列或轉場段落 |
| `freezedetect` | 偵測凍結影片段落 |
| `vectorscope` / `histogram` | 可視化色彩範圍與訊號剖面 |
| `psnr` / `ssim` | 計算客觀影片品質指標 |
| `addroi` | 定義感興趣區域（ROI） |

#### 4.1.7 現代深度學習與硬體加速

| 過濾器 | 功能 |
|---|---|
| `dnn_processing` | 深度神經網絡模型（超解析度、風格轉換） |
| `libplacebo` | GPU 加速 HDR tone mapping、去帶、縮放 |
| `scale_vulkan` / `scale_cuda` / `scale_vaapi` | GPU 加速縮放 |
| `yadif_videotoolbox` | Apple 硬體加速去隔行 |
| `flip_vulkan` | Vulkan API 硬體加速翻轉 |

### 4.2 查詢過濾器方法

```bash
# 查看所有編譯進去的過濾器
ffmpeg -filters

# 查看特定過濾器的詳細功能與參數
ffmpeg -h filter=scale
```

---

## 5. PyAV Filter Graph 進階應用

### 5.1 基本線性過濾器鏈

```python
import av

graph = av.filter.Graph()

# 建立輸入來源、節點、輸出
buffer_in = graph.add_buffer(template=video_stream)
vflip = graph.add("vflip")
hue = graph.add("hue", "h=45:s=1.5")
buffer_out = graph.add("buffersink")

# 線性連接：輸入 → vflip → hue → 輸出
buffer_in.link_to(vflip)
vflip.link_to(hue)
hue.link_to(buffer_out)
graph.configure()

# 標準框架迴圈
graph.push(frame)
processed = graph.pull()
```

### 5.2 進階 Picture-in-Picture（PiP）過濾器圖譜

```python
import av

graph = av.filter.Graph()
src = graph.add_buffer(template=v_stream)

# 建立分支節點
split = graph.add("split")           # 分流：一份模糊背景，一份縮小前景
scale = graph.add("scale", f"{int(v_stream.width/4)}:-1")
overlay = graph.add("overlay", "x=20:y=20")
sink = graph.add("buffersink")

# 線路連接：
#  1 input → split → [1: scaled, 2: original] → overlay → sink
src.link_to(split)
split.link_to(overlay, 0, 0)  # Path 1 到 overlay 背景
split.link_to(scale, 1, 0)    # Path 2 到 scale
scale.link_to(overlay, 0, 1)  # 縮小後到 overlay 前景
overlay.link_to(sink)
graph.configure()
```

### 5.3 動態過濾器圖譜：背景模糊 + 前景 PiP

```python
import av

container = av.open('input.mp4')
output = av.open('output.mp4', mode='w')

in_stream = container.streams.video[0]
out_stream = output.add_stream('libx264', rate=in_stream.average_rate)
out_stream.width = in_stream.width
out_stream.height = in_stream.height
out_stream.pix_fmt = 'yuv420p'

# 複雜過濾器圖譜
# [in] split into [main] and [bg]. [bg] blurs, [main] scales. Overlay.
graph = av.filter.Graph()
link_in = graph.add_buffer(template=in_stream)
link_out = graph.add_buffersink()

split = graph.add("split", "2")
blur = graph.add("boxblur", "luma_radius=20:luma_power=2")
scale = graph.add("scale", f"{in_stream.width//2}:{in_stream.height//2}")
overlay = graph.add("overlay", "x=(W-w)/2:y=(H-h)/2")

# 連接圖譜
link_in.link_to(split)
split.outputs[0].link_to(blur)       # 背景軌道
split.outputs[1].link_to(scale)      # 前景軌道

blur.outputs[0].link_to(overlay, 0)  # Overlay 輸入 0 (背景)
scale.outputs[0].link_to(overlay, 1)  # Overlay 輸入 1 (前景)
overlay.outputs[0].link_to(link_out)

graph.configure()

# 處理迴圈
for frame in container.decode(video=0):
    graph.push(frame)
    try:
        while True:
            out_frame = graph.pull()
            for packet in out_stream.encode(out_frame):
                output.mux(packet)
    except av.EOFError:
        pass  # 圖譜刷新

# 刷新編碼器
for packet in out_stream.encode():
    output.mux(packet)
output.close()
```

### 5.4 動態參數調控（Runtime Filter Modification）

```python
# 在處理迴圈中動態修改過濾器參數
# 例如：每幀修改 hue 的色相值
hue_node.process_command(cmd="h", arg=str(new_hue_value))
```

### 5.5 進階圖譜場景規劃

| Effect | Libavfilter Strategy | Multi-Node Graph Wiring |
|---|---|---|
| **Chroma Key** | `chromakey` + `overlay` | Background→overlay[0], Green Screen→chromakey→overlay[1] |
| **Side-by-Side** | `hstack` or `xstack` | buffer_left→hstack[0], buffer_right→hstack[1] |
| **Watermark** | `movie` + `overlay` | `graph.add("movie", "logo.png")`→overlay[1] |
| **Blur Background** | `split` + `boxblur` + `overlay` | Split→blur→overlay[0], Split→sharp→overlay[1] |
| **Crossfade** | `xfade` or `fade` + `overlay` | [0:v][1:v]xfade=transition=dissolve |
| **Multi-Track Audio** | `amix`, `aresample`, `aformat` | 多軌音訊混音與路由 |

---

## 6. PyAV + NumPy 每幀像素操控

### 6.1 RGB 色差特效（Chromatic Aberration）

```python
import av
import numpy as np

container = av.open('input.mp4')
output = av.open('glitch_output.mp4', mode='w')

in_stream = container.streams.video[0]
out_stream = output.add_stream('libx264', rate=in_stream.average_rate)
out_stream.width = in_stream.width
out_stream.height = in_stream.height
out_stream.pix_fmt = 'yuv420p'

for frame in container.decode(video=0):
    # 1. 將 PyAV 幀轉換為 RGB NumPy 陣列
    img_rgb = frame.to_ndarray(format='rgb24')

    # 2. 進階操控：RGB 色差偏移
    shift_pixels = 15
    glitch_img = img_rgb.copy()

    # R 通道向左移，B 通道向右移
    glitch_img[:, shift_pixels:, 0] = img_rgb[:, :-shift_pixels, 0]  # Red
    glitch_img[:, :-shift_pixels, 2] = img_rgb[:, shift_pixels:, 2]  # Blue

    # 3. 將 NumPy 陣列封裝回 PyAV VideoFrame
    new_frame = av.VideoFrame.from_ndarray(glitch_img, format='rgb24')
    new_frame.pts = frame.pts
    new_frame.time_base = frame.time_base

    # 4. 重新編碼到 YUV420p
    for packet in out_stream.encode(new_frame):
        output.mux(packet)

# 沖刷編碼器
for packet in out_stream.encode():
    output.mux(packet)
output.close()
```

### 6.2 影片殘影 / 幀累積效果（Temporal Echo / Ghosting）

```python
import av
import collections
import numpy as np

container = av.open('input.mp4')
output = av.open('echo_output.mp4', mode='w')
in_stream = container.streams.video[0]
out_stream = output.add_stream('libx264', rate=in_stream.average_rate)
out_stream.width = in_stream.width
out_stream.height = in_stream.height
out_stream.pix_fmt = 'yuv420p'

# 滾動緩衝區：保留歷史幀
history_depth = 5
frame_history = collections.deque(maxlen=history_depth)

for frame in container.decode(video=0):
    img = frame.to_ndarray(format='rgb24').astype(np.float32)
    frame_history.append(img)

    # 混合歷史幀（線性衰減權重）
    blended_img = np.zeros_like(img)
    weights = np.linspace(0.2, 1.0, len(frame_history))
    weights /= weights.sum()  # 正規化權重

    for idx, hist_frame in enumerate(frame_history):
        blended_img += hist_frame * weights[idx]

    # 轉回 uint8 編碼
    final_img = np.clip(blended_img, 0, 255).astype(np.uint8)

    new_frame = av.VideoFrame.from_ndarray(final_img, format='rgb24')
    new_frame.pts = frame.pts
    new_frame.time_base = frame.time_base

    for packet in out_stream.encode(new_frame):
        output.mux(packet)

for packet in out_stream.encode():
    output.mux(packet)
output.close()
```

### 6.3 綠幕抠像合成（Green Screen Compositing）

```python
import av
import numpy as np

# 假設 foreground_frame 和 background_frame 來自兩個串流
fg_nodes = foreground_frame.to_ndarray(format='rgb24')
bg_nodes = background_frame.to_ndarray(format='rgb24')

# RGB 空間中的綠幕閾值判斷
green_mask = (
    (fg_nodes[:,:,1] > 150) &   # Green 通道高
    (fg_nodes[:,:,0] < 100) &   # Red 通道低
    (fg_nodes[:,:,2] < 100)     # Blue 通道低
)

# 將遮罩擴展到 3 個色彩通道
mask_3d = np.repeat(green_mask[:, :, np.newaxis], 3, axis=2)

# 將綠色像素替換為背景像素
composited_nodes = np.where(mask_3d, bg_nodes, fg_nodes)

composited_frame = av.VideoFrame.from_ndarray(composited_nodes, format='rgb24')
```

### 6.4 進階每幀操控場景總表

| 場景 | NumPy 技術 | 效果說明 |
|---|---|---|
| **色差偏移** | RGB 通道切片與位移 | 模擬鏡頭色散效果 |
| **殘影追蹤** | 歷史幀緩衝 + 權重疊加 | 光軌拖尾、動態模糊 |
| **綠幕抠像** | 閾值判斷 + np.where | 前景與背景無縫合成 |
| **邊緣檢測** | Sobel/Canny NumPy 實現 | 輪廓線描效果 |
| **頻率域濾波** | FFT → 頻域遮罩 → IFFT | 進階頻域處理 |
| **自訂遮罩** | 布林運算 + np.select | 任意形狀的透明區域 |
| **像素替換** | 座標映射 + 陣列索引 | 鏡像、扭曲、平移 |

---

## 7. PyAV + CuPy GPU 加速特效

### 7.1 核心架構：PyAV → CuPy 零拷貝轉換

```python
import av
import cupy as cp
import numpy as np

def process_video(input_path, output_path):
    container = av.open(input_path)
    stream = container.streams.video[0]

    # 設定輸出容器與編碼器
    out_container = av.open(output_path, mode='w')
    out_stream = out_container.add_stream('libx264', rate=stream.average_rate)
    out_stream.width = stream.width
    out_stream.height = stream.height
    out_stream.pix_fmt = 'yuv420p'

    for frame in container.decode(stream):
        # 1. 轉為 NumPy 陣列
        img_np = frame.to_ndarray(format='rgb24')

        # 2. 傳送到 GPU (CuPy)
        img_gpu = cp.asarray(img_np)

        # 3. 執行 GPU 特效處理
        processed_gpu = apply_effects(img_gpu)

        # 4. 傳回 CPU
        out_np = cp.asnumpy(processed_gpu).astype(np.uint8)

        # 5. 封裝回 PyAV 並寫入
        out_frame = av.VideoFrame.from_ndarray(out_np, format='rgb24')
        for packet in out_stream.encode(out_frame):
            out_container.mux(packet)

    # 沖刷編碼器
    for packet in out_stream.encode():
        out_container.mux(packet)
    out_container.close()
    container.close()
```

### 7.2 GPU 色差特效（Chromatic Aberration）

```python
def apply_chromatic_aberration(img_gpu, shift_x=5, shift_y=2):
    """
    img_gpu: CuPy array of shape (H, W, 3)
    """
    h, w, c = img_gpu.shape
    output = cp.zeros_like(img_gpu)

    # R 通道向左上平移
    output[:h-shift_y, :w-shift_x, 0] = img_gpu[shift_y:, shift_x:, 0]
    # G 通道保持不動
    output[:, :, 1] = img_gpu[:, :, 1]
    # B 通道向右下平移
    output[shift_y:, shift_x:, 2] = img_gpu[:h-shift_y, :w-shift_x, 2]

    return output
```

### 7.3 GPU 運動追蹤與視覺暫留（Motion Tracking & Trails）

```python
class MotionTrackerEffect:
    def __init__(self, alpha=0.7, threshold=30):
        self.prev_gray = None
        self.alpha = alpha  # 殘影衰減率
        self.motion_buffer = None
        self.threshold = threshold

    def apply(self, img_gpu):
        # 轉為灰階計算動態
        gray = 0.299 * img_gpu[:,:,0] + 0.587 * img_gpu[:,:,1] + 0.114 * img_gpu[:,:,2]

        if self.prev_gray is None:
            self.prev_gray = gray.copy()
            self.motion_buffer = cp.zeros_like(img_gpu, dtype=cp.float32)
            return img_gpu

        # 計算前後幀差異（Motion Mask）
        diff = cp.abs(gray - self.prev_gray)
        motion_mask = diff > self.threshold

        # 將動態區域著色（科幻風格）
        current_motion = cp.zeros_like(img_gpu, dtype=cp.float32)
        current_motion[motion_mask, 1] = 255  # Green
        current_motion[motion_mask, 2] = 255  # Blue

        # 疊加歷史動態殘影（指數移動平均 EMA）
        self.motion_buffer = self.alpha * self.motion_buffer + (1 - self.alpha) * current_motion

        # 混合原圖與追蹤殘影
        output = cp.clip(img_gpu + self.motion_buffer, 0, 255).astype(cp.uint8)

        self.prev_gray = gray
        return output
```

### 7.4 GPU Datamoshing（數據融合破壞）

```python
class GPUDatamosher:
    def __init__(self, mosh_frequency=30):
        self.frame_count = 0
        self.mosh_frequency = mosh_frequency
        self.anchor_frame = None

    def apply(self, img_gpu):
        self.frame_count += 1

        # 模擬 I-Frame 觸發點：每隔一段時間重新擷取基準畫面
        if self.frame_count % self.mosh_frequency == 0 or self.anchor_frame is None:
            self.anchor_frame = img_gpu.copy().astype(cp.float32)
            return img_gpu

        # 模擬 P-Frame 運動向量錯誤渲染：
        # 計算當前幀的偽運動引導（利用 X 方向梯度）
        gray = (0.299 * img_gpu[:,:,0] + 0.587 * img_gpu[:,:,1] + 0.114 * img_gpu[:,:,2])
        grad_x = cp.gradient(gray, axis=1)

        # 根據梯度大小，將 anchor_frame 的像素進行無序揉捏（Glitch）
        shift = (grad_x * 0.1).astype(cp.int32)

        # 透過 GPU 網格重採樣（Grid Mapping）產生破壞性撕裂
        rows, cols, ch = img_gpu.shape
        c_idx, r_idx = cp.meshgrid(cp.arange(cols), cp.arange(rows))

        # 扭曲 X 座標
        mushed_c_idx = cp.clip(c_idx + shift, 0, cols - 1)

        # 從基準幀抽取像素，覆蓋到當前幀
        for i in range(ch):
            self.anchor_frame[:, :, i] = self.anchor_frame[r_idx, mushed_c_idx, i]

        return self.anchor_frame.astype(cp.uint8)
```

### 7.5 整合主程式執行

```python
def main():
    input_video = "input.mp4"
    output_video = "output_glitch.mp4"

    container = av.open(input_video)
    stream = container.streams.video[0]

    out_container = av.open(output_video, mode='w')
    out_stream = out_container.add_stream('libx264', rate=stream.average_rate)
    out_stream.width = stream.width
    out_stream.height = stream.height
    out_stream.pix_fmt = 'yuv420p'

    # 初始化特效器
    tracker = MotionTrackerEffect(alpha=0.85, threshold=25)
    mosher = GPUDatamosher(mosh_frequency=45)

    for frame in container.decode(stream):
        # CPU → GPU
        img_np = frame.to_ndarray(format='rgb24')
        img_gpu = cp.asarray(img_np)

        # 執行 GPU 加速特效鏈
        img_gpu = apply_chromatic_aberration(img_gpu, shift_x=8, shift_y=3)
        img_gpu = tracker.apply(img_gpu)
        img_gpu = mosher.apply(img_gpu)

        # GPU → CPU
        out_np = cp.asnumpy(img_gpu).astype(np.uint8)

        # 寫入幀
        out_frame = av.VideoFrame.from_ndarray(out_np, format='rgb24')
        for packet in out_stream.encode(out_frame):
            out_container.mux(packet)

    for packet in out_stream.encode():
        out_container.mux(packet)
    out_container.close()
    container.close()
    print("影片 GPU 特效處理完成！")

if __name__ == "__main__":
    main()
```

---

## 8. 三層混合架構：PyAV + FFmpeg CLI + MoviePy

### 8.1 架構總覽

```
┌──────────────────────────────────────────────────────────┐
│              High-Level: MoviePy                           │
│  ├── 非線性剪輯時間軸管理                                  │
│  ├── 多軌音訊混音 + 同步                                   │
│  ├── 字幕 + 圖層 + 轉場                                   │
│  └── write_videofile 快速導出                              │
├──────────────────────────────────────────────────────────┤
│              Mid-Level: FFmpeg CLI                         │
│  ├── filter_complex 多軌精細控制                          │
│  ├── xfade 過場轉場                                       │
│  ├── dnn_processing AI 超解析度                            │
│  └── libplacebo HDR 調色映射                              │
├──────────────────────────────────────────────────────────┤
│              Low-Level: PyAV                               │
│  ├── 高效解碼、精確時間戳追蹤                              │
│  ├── Filter Graph 處理合成/過場/調色                       │
│  └── NumPy/CuPy 像素數學運算                               │
└──────────────────────────────────────────────────────────┘
```

### 8.2 典型工作流範例

```python
"""
完整工作流：
1. PyAV 高效解碼大型影片 → 提取特定範圍幀
2. CuPy GPU 做像素級特效（色差、運動追蹤、Datamoshing）
3. 轉為 NumPy 陣列後交給 MoviePy 加字幕、混音、加轉場
4. MoviePy write_videofile 輸出最終成品
"""

import av
import cupy as cp
import numpy as np
from moviepy import ImageSequenceClip, VideoFileClip

# ===========================
# Stage 1: PyAV 高效解碼
# ===========================
container = av.open('input_large_video.mp4')
video_stream = next(s for s in container.streams if s.type == 'video')

extracted_frames = []
for frame_count, frame in enumerate(container.decode(video=0)):
    if frame_count >= 60:
        break
    img_array = frame.to_ndarray(format='rgb24')
    extracted_frames.append(img_array)

container.close()

# ===========================
# Stage 2: CuPy GPU 特效
# ===========================
processed_frames = []
for img_np in extracted_frames:
    img_gpu = cp.asarray(img_np)
    img_gpu = apply_chromatic_aberration(img_gpu, shift_x=8, shift_y=3)
    img_gpu = tracker.apply(img_gpu)
    out_np = cp.asnumpy(img_gpu).astype(np.uint8)
    processed_frames.append(out_np)

# ===========================
# Stage 3: MoviePy 高階剪輯
# ===========================
fps = float(video_stream.average_rate)
short_clip = ImageSequenceClip(processed_frames, fps=fps)

# 加入縮放、旋轉、淡入效果
processed_clip = (
    short_clip
    .resized(size=(1280, 720))   # 調整解析度
    .rotated(angle=90)           # 旋轉 90 度
    .fadein(duration=1.0)        # 加入 1 秒淡入效果
)

# 加入字幕與音訊
final_clip = processed_clip.with_subtitles('subtitle.srt')

# ===========================
# Stage 4: 導出
# ===========================
final_clip.write_videofile('output_final.mp4', fps=fps)
```

### 8.3 FFmpeg CLI 進階應用範例

```bash
# 1. Crossfade 過場轉場（帶音訊）
ffmpeg -i video1.mp4 -i video2.mp4 -filter_complex \
  "[0:v][1:v]xfade=transition=dissolve:duration=1:offset=9[v]; \
   [0:a][1:a]acrossfade=d=1[a]" \
  -map "[v]" -map "[a]" output.mp4

# 2. 複雜過濾器鏈：調色 + 模糊背景 + PiP + HDR tone mapping
ffmpeg -i input.mp4 -filter_complex \
  "[0:v]split=[main][bg]; \
   [bg]boxblur=20:10=[blur]; \
   [main]scale=320:240=[pip]; \
   [blur][pip]overlay=W-w-20:H-h-20=[composited]; \
   [composited]lut3d=grade.cube=[graded]; \
   [graded]libplacebo=tonemap=bt2020:peak=auto" \
  -map "[graded]" output.mp4

# 3. AI 超解析度
ffmpeg -i input.mp4 -vf dnn_processing=model=upscaler.onnx output.mp4
```

---

## 9. 效能優化建議

### 9.1 記憶體管理

| 優化策略 | 說明 |
|---|---|
| **預分配陣列** | 重複使用 `np.empty()` 或 `np.zeros()`，避免每幀重新配置 |
| **避免 GC 開銷** | 在 CuPy 中盡量重用固定形狀的 `cp.zeros` 或 `motion_buffer` |
| **零拷貝優先** | 基本裁剪、縮放等操作留在 `yuv420p` 空間，避免 RGB↔YUV 轉換 |

### 9.2 多執行緒配置

```python
# 解碼執行緒
in_stream.thread_type = 'AUTO'

# 編碼執行緒
out_stream.codec_context.thread_count = 4

# 過濾器圖譜執行緒
graph = av.filter.Graph()
graph.thread_count = 4
```

### 9.3 色彩空間注意事項

| 情境 | 建議 |
|---|---|
| 基本裁剪/縮放 | 留在 `yuv420p` 空間，使用 FFmpeg 過濾器圖譜 |
| 像素級數學運算 | 轉換到 `rgb24` 後用 NumPy/CuPy 處理 |
| HDR 調色 | 使用 `libplacebo` 或 `lut3d`，避免手動色彩空間轉換 |
| 硬體解碼 | PyAV 設定 `hwaccel='cuda'`，解碼→GPU→編碼全流程留在 GPU |

### 9.4 硬體加速解碼

```python
# PyAV 設定 CUDA 硬體解碼
container = av.open(
    'input.mp4',
    options={'hwaccel': 'cuda'}
)
# 解碼階段留在 GPU 內
# 結合 CuPy 進行 GPU 處理
# 全程避免 CPU-GPU 記憶體拷貝
```

### 9.5 自訂 CUDA Kernel

若切片或网格映射操作仍未達到滿幀率，可使用 CuPy 的 `cp.ElementwiseKernel` 撰寫原生 C++ CUDA 核心：

```python
import cupy as cp

# 自訂 CUDA Kernel：色差偏移
chromatic_aberration_kernel = cp.ElementwiseKernel(
    'raw int32 src, int32 shift_x, int32 shift_y, int32 height, int32 width',
    'raw uint8 dst',
    '''
    int y = i / (width * 3);
    int x = (i % width) * 3;
    int ch = i % 3;
    int src_x = x;
    if (ch == 0) src_x -= shift_x;  // R 通道左移
    if (ch == 2) src_x += shift_x;  // B 通道右移
    if (y < shift_y || src_x < 0 || src_x >= (width-1)*3) {
        dst[i] = 0;  // 邊界填充黑
    } else {
        dst[i] = src[y * width * 3 + src_x + ch];
    }
    ''',
    'chromatic_aberration'
)
```

---

## 10. 總結：複雜度階梯

### 10.1 六大技術階梯

| 階梯 | 技術層次 | 可達到的效果 | 適用場景 |
|---|---|---|---|
| **Lv1** | FFmpeg CLI 命令 | 調色、裁切、疊加、過場、綠幕 | 快速批次處理 |
| **Lv2** | PyAV Filter Graph | 程式化多分支過濾器圖譜、動態參數 | 自訂過場與合成 |
| **Lv3** | PyAV + NumPy 每幀運算 | 色差、殘影、Datamoshing、邊緣檢測 | 像素級自訂特效 |
| **Lv4** | PyAV + CuPy GPU 加速 | 實時 GPU 像素級特效、硬體解碼 | 高吞吐量管線 |
| **Lv5** | PyAV + CuPy + CUDA Kernel | 自訂 GPU 核心、極致幀率 | 商業級實時處理 |
| **Lv6** | PyAV + MoviePy + FFmpeg 混合 | 完整商業級影片後製管線 | 專業影片製作 |

### 10.2 選擇建議

| 需求 | 推薦方案 |
|---|---|
| **快速剪輯與原型** | MoviePy（預設 FFmpeg 後端） |
| **高頻率影片解碼** | PyAV（替代 FFmpeg 子進程） |
| **複雜過濾器圖譜** | PyAV Filter Graph API |
| **像素級自訂特效** | PyAV + NumPy |
| **GPU 加速實時處理** | PyAV + CuPy |
| **完整影片後製管線** | PyAV（I/O）+ CuPy（特效）+ MoviePy（高階邏輯） |

### 10.3 核心結論

1. **PyAV 並非 MoviePy 的必要依賴，而是其效能最佳化的選擇性後端。**
2. **MoviePy 預設使用 FFmpeg 子進程模式，但可切換到 PyAV 後端獲得更好的效能與準確性。**
3. **FFmpeg 提供了強大的過濾器底層，PyAV 讓你能以程式化方式完全控制每一個解碼幀。**
4. **結合 NumPy/CuPy 的數學運算能力，理論上你能實現任何基於像素的影像特效。**
5. **最高級的實務應用是三者分工協作：PyAV 負責 I/O 與低階處理，MoviePy 負責高階剪輯邏輯，FFmpeg CLI 負責批次進階過濾器。**

---

## 參考資源

| 資源 | 連結 |
|---|---|
| PyAV 官方文件 | https://pyav.org/ |
| MoviePy 官方文件 | https://zulko.github.io/moviepy/ |
| FFmpeg 過濾器文件 | https://ffmpeg.org/ffmpeg-filters.html |
| CuPy 文件 | https://docs.cupy.dev/ |
| MoviePy PyAV 後端整合 | https://zulko.github.io/moviepy/getting_started/install.html |

---

*End of Document*
