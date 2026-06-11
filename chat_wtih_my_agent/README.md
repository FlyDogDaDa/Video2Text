# chat_wtih_my_agent — Conversation Index

Video2Text 專案的 agent 與 human 對話記錄，涵蓋專案初始化、vLLM 框架選型與除錯、多模態模型驗證、影片切片工具實作，以及 FFmpeg 環境部署。

## 大綱與最終狀態

```
[06-07] 專案初始化 → 框架選型（SGLang ↔ vLLM 來回）→ 確立 vLLM 為最終框架
[06-08] 修復 flashinfer 崩潰 → 推論成功 → 系統環境稽核
[06-09] 建立啟動腳本 → 修正 attention-backend 參數 → API 200 OK
         ├─ 研究 vLLM 多模態模組結構（video/audio/image）
         ├─ 發現 stable v0.22.1 不支援 video_url，圖片有 num_soft_tokens bug
         ├─ 建立離線推論腳本 multimodal_infer.py（僅文字可用）
         └─ 調查 fetch_video() 回傳值與 32 幀來源
[06-09→10] 🔄 升級 nightly vLLM → 修復 num_soft_tokens bug → 四模態全部通過 ✅
         ├─ 更正 Gemma-4-12B encoder-free 架構認知
         ├─ 掃描磁碟空間 → 清理 55GB
         └─ 規劃 NAS 搬移（待 NFS 掛載）
[06-10] 實作 slice-utils 切片工具 → 重構為 PyAV 單一後端 + IOCacheVideo
[06-10] 部署 FFmpeg/ffprobe 7.0.2 靜態執行檔至 runtime/
[06-10] 研究 PyAV ↔ MoviePy 架構關聯性（參考文檔）
```

## 衝突資訊與轉折對照

| 問題 | 初次發現 | 狀態 | 解決方式 |
|------|----------|:----:|----------|
| **影片功能** | stable v0.22.1 不支援 `video_url`（09） | ❌ | → 升級 nightly vLLM dev301（16）→ ✅ 四模態全部通過 |
| **圖片 bug** | `'Gemma4UnifiedVisionConfig' object has no attribute 'num_soft_tokens'`（14） | ❌ | → nightly dev301 原生修復（16）→ ✅ |
| **audio encoder** | 誤以為 Gemma-4-12B 沒有 audio encoder（15） | ❌ 認知錯誤 | → 更正：encoder-free 架構 ≠ 無 audio encoder（16）→ ✅ |
| **flashinfer 崩潰** | `enforce_eager=True` 暫時解法（08） | ✅ 已適用 | → 最終改為 `--attention-backend TRITON_ATTN` 參數（11）|
| **磁碟空間** | 467GB 已用 440GB（94%）（16） | ⚠️ | → `rm -rf .venv && uv cache clean` 釋放 55GB → 可用 61GB |
| **後端選擇** | OpenCV + soundfile + PyAV 多後端（19） | ⚙️ | → 重構為 PyAV 單一後端 + IOCacheVideo（22）|

## 文件列表

| # | 檔案 | 作者 | 日期 | 摘要 |
|---|------|:----:|:----:|------|
| 00 | [`00_2026_06_07_agent_project-initialization-and-vllm-setup.md`](./00_2026_06_07_agent_project-initialization-and-vllm-setup.md) | Agent | 06-07 | 專案初始化（`uv init`）、安裝 vLLM、建立 `.agent` 資料夾 |
| 01 | [`01_2026_06_07_human_video2text-system-design.md`](./01_2026_06_07_human_video2text-system-design.md) | Human | 06-07 | 系統設計規格：schema、視窗處理模式（Sequential / Swarm）、Round 結構 |
| 02 | [`02_2026_06_07_agent_structured-model-and-documentation.md`](./02_2026_06_07_agent_structured-model-and-documentation.md) | Agent | 06-07 | 建立 `src/models.py` Pydantic models（SliceResult 及其子結構） |
| 03 | [`03_2026_06_07_docs_sglang-gemma4.md`](./03_2026_06_07_docs_sglang-gemma4.md) | Human | 06-07 | SGLang 官方文件索引（安裝、部署、呼叫、Benchmark） |
| 04 | [`04_2026_06_07_docs_gemma4-12b-qat-w4a16.md`](./04_2026_06_07_docs_gemma4-12b-qat-w4a16.md) | Human | 06-07 | Gemma 4 12B QAT w4a16-ct 模型評估（規格、量化格式、Benchmark） |
| 05 | [`05_2026_06_07_agent_sglang-installation.md`](./05_2026_06_07_agent_sglang-installation.md) | Agent | 06-07 | 安裝 SGLang 至專案，移除 vLLM（flashinfer 衝突），Python 3.12 定案 |
| 06 | [`06_2026_06_07_agent_vllm-restore-for-gemma4.md`](./06_2026_06_07_agent_vllm-restore-for-gemma4.md) | Agent | 06-07 | 回退至 vLLM（SGLang 不支援 w4a16-ct），清理磁碟，確立最終框架 |
| 07 | [`07_2026_06_07_agent_test-video-spec.md`](./07_2026_06_07_agent_test-video-spec.md) | Agent | 06-07 | 測試影片 `2026_05_11-19_18_26.mkv` 規格分析（57.7 分、60 FPS、207K 幀） |
| 08 | [`08_2026_06_08_agent_gemma4-vllm-inference-fixes.md`](./08_2026_06_08_agent_gemma4-vllm-inference-fixes.md) | Agent | 06-08 | 修復 flashinfer 崩潰（`enforce_eager=True`）、修正影片路徑，推論成功 |
| 09 | [`09_2026_06_08_agent_system-info-gathering.md`](./09_2026_06_08_agent_system-info-gathering.md) | Agent | 06-08 | 系統環境稽核（雙卡 GPU、框架版本、磁碟空間警報） |
| 10 | [`10_2026_06_09_agent_vllm-launch-and-healthcheck.md`](./10_2026_06_09_agent_vllm-launch-and-healthcheck.md) | Agent | 06-09 | 建立啟動腳本 `launch_Gemma4-12b.sh` 與健康檢查 `block_me_with_file.sh`，修復 flashinfer 崩潰 |
| 11 | [`11_2026_06_09_agent_fix-vllm-attention-backend-crash.md`](./11_2026_06_09_agent_fix-vllm-attention-backend-crash.md) | Agent | 06-09 | 修正 `--attention-backend` 參數值（`VLLM_ATTENTION_BACKEND` 不受支援 → `TRITON_ATTN`），API 測試 200 OK |
| 12 | [`12_2026_06_09_agent_vllm-multimodal-video-research.md`](./12_2026_06_09_agent_vllm-multimodal-video-research.md) | Agent | 06-09 | vLLM 影片處理研究：API 格式、動態解析度、stable v0.22.1 不支援 video_url |
| 13 | [`13_2026_06_09_agent_vllm-multimodal-modules-research.md`](./13_2026_06_09_agent_vllm-multimodal-modules-research.md) | Agent | 06-09 | 研究 `vllm.multimodal.video/audio/image` 模組結構，釐清線上 API vs 離線推理差異 |
| 14 | [`14_2026_06_09_agent_vllm-multimodal-online-testing.md`](./14_2026_06_09_agent_vllm-multimodal-online-testing.md) | Agent | 06-09 | 線上 API 測試：文字 ✅、圖片 ❌ 500 bug、影片 ❌ 不支援 |
| 15 | [`15_2026_06_09_agent_vllm-offline-inference-script.md`](./15_2026_06_09_agent_vllm-offline-inference-script.md) | Agent | 06-09 | 建立 `src/inference/multimodal_infer.py` 離線推論腳本（僅文字可用），更正 Gemma-4 賣點 |
| 16 | [`16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md`](./16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md) | Human | 06-09 | 安裝 nightly vLLM dev301 修復 bug → 四模態全部通過 ✅，磁碟清理 55GB，NAS 搬移規劃 |
| 17 | [`17_2026_06_09_agent_vllm-fetch-video-return-type-and-video-frame-count.md`](./17_2026_06_09_agent_vllm-fetch-video-return-type-and-video-frame-count.md) | Agent | 06-09 | 確認 `fetch_video()` 回傳格式，調查 `_VIDEO_MAX_FRAMES = 32` 來源 |
| 18 | [`18_vllm_audio_extraction_logic.md`](./18_vllm_audio_extraction_logic.md) | Human | 06-09 | vLLM 音訊/影片預設行為調查（32 幀上限、音訊 30s 限制、無自動切分） |
| 19 | [`19_2026_06_10_agent_slice-utils-implementation.md`](./19_2026_06_10_agent_slice-utils-implementation.md) | Agent | 06-10 | 實作 `src/utils/slice.py` 切片工具（視窗 30s + 2s 重疊、seek-buffer、range read、快取） |
| 20 | [`20_2026_06_10_agent_ffmpeg-runtime-setup.md`](./20_2026_06_10_agent_ffmpeg-runtime-setup.md) | Agent | 06-10 | 部署 FFmpeg/ffprobe 7.0.2 靜態執行檔至 `runtime/` |
| 21 | [`21_2026_06_10_docs_PyAV_and_MoviePy.md`](./21_2026_06_10_docs_PyAV_and_MoviePy.md) | Agent | 06-10 | PyAV ↔ MoviePy 架構關聯性深度研究（六層技術階梯） |
| 22 | [`22_2026_06_10_agent_restructure-video-slicing-to-pyav.md`](./22_2026_06_10_agent_restructure-video-slicing-to-pyav.md) | Agent | 06-10 | 重構 slice.py：多後端 → PyAV 單一後端 + `IOCacheVideo` + `container.py` + `audio.py` |

## 關鍵決策時間軸

```
06-07  [初始化]  uv init → 安裝 vLLM
06-07  [設計]   人類撰寫系統設計（schema、模式、Round）
06-07  [探索]   評估 SGLang → 安裝成功
06-07  [回退]   SGLang 不支援 w4a16-ct → 回退 vLLM ✅
06-07  [驗證]   測試影片規格、frame extraction
06-08  [修復]   flashinfer 崩潰 → enforce_eager → 推論成功 ✅
06-08  [稽核]   系統環境全盤檢查
06-09  [工具]   建立啟動腳本與健康檢查 shell script
06-09  [修復]   --attention-backend TRITON_ATTN 取代環境變數，API 測試 200 OK
06-09  [研究]   多模態模組結構、離線推論腳本、API 測試（文字✅ 圖片❌ 影片❌）
06-09  [調查]   fetch_video() 回傳值、32 幀來源 (_VIDEO_MAX_FRAMES)
🔀 06-09  [升級] nightly vLLM dev301 → 修復 num_soft_tokens + video_url → 四模態全部通過 ✅
🔀 06-09  [更正] encoder-free ≠ 無 audio encoder，更新模型賣點
🔀 06-09  [清理] rm -rf .venv && uv cache clean → 釋放 55GB
06-10  [實作]   src/utils/slice.py 切片工具（視窗、seek-buffer、range read、快取）
06-10  [部署]   FFmpeg 7.0.2 靜態執行檔 → runtime/
06-10  [重構]   slice.py → PyAV 單一後端 + IOCacheVideo（691行 → 393行）
06-10  [研究]   PyAV ↔ MoviePy 六層技術階梯參考文檔
```

## 當前可用功能總覽

| 功能 | 狀態 | 備註 |
|------|:----:|------|
| vLLM server（OpenAI API） | ✅ | nightly dev301, TRITON_ATTN, port 8746 |
| 純文字推論 | ✅ | stable |
| 圖片推論 | ✅ | dev301 已修復 num_soft_tokens bug |
| 影片推論 | ✅ | dev301 支援 video_url |
| 音訊推論 | ✅ | dev301 支援 |
| 影片切片工具 | ✅ | `IOCacheVideo`（PyAV 單一後端）|
| FFmpeg/ffprobe | ✅ | 7.0.2 靜態執行檔 in `runtime/` |
| SGLang | ❌ | 已移除（不支援 w4a16-ct）|

## 參考路徑

| 項目 | 路徑 |
|------|------|
| 專案根目錄 | `../` |
| pyproject.toml | `../pyproject.toml` |
| 資料模型 | `../src/models.py` |
| 推論腳本 | `08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py` |
| 離線推論 | `../src/inference/multimodal_infer.py` |
| 主程式 | `../main.py` |
| 影片切片工具 | `../src/utils/slice.py`, `../src/utils/container.py`, `../src/utils/audio.py` |
| FFmpeg 執行檔 | `../runtime/ffmpeg`, `../runtime/ffprobe` |
| 啟動腳本 | `../src/vllm_launch/launch_Gemma4-12b.sh` |

---

更新日期：2026-06-10
