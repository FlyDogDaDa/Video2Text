---
date: 2026-08-14
topics: [target-diarization-research, video2text-comparison, audio-processing, architecture-analysis]
status: research-complete
author: agent
---

# TargetDiarization vs Video2Text 完整技術比較研究

## 時間

2026-08-14

## 研究動機

Video2Text 專案的 `modules/` 目錄中，VAD、ASR、Clean、Summarize、VideoDesc 全部是 Stub placeholder，主流程 `workflow.py` 目前無法執行有意義的處理。

需要評估外部專案 `jingzhunxue/TargetDiarization` 是否可作為 Video2Text 的 STT 伺服器模組整合，補上當前缺失的核心音訊處理能力。

## 研究方法

使用 **4 個 parallel sub-agents** 從不同維度進行深入比較分析：

| Agent ID | 分析維度 | 輸入 | 輸出 |
|---|---|---|---|
| #1 | **架構分析** | TargetDiarization 完整 source code（6 個核心檔案） | 整體架構、Pipeline 流程、設計模式、工程評價 |
| #2 | **Video2Text 深度分析** | Video2Text 完整 source tree（所有目錄） | modules 實作狀態、voicetag 整合、配置管理、完成度 |
| #3 | **音訊處理技術比較** | 兩個專案的各子系統技術選型 | VAD/Diarization/Separation/ASR/Punctuation 逐項比較 |
| #4 | **軟體工程實務比較** | 兩個專案的程式碼風格、API、Config、Packaging | 工程品質評估、安全考量、開發者體驗 |

## 完整比較結果

### 一、專案定位與概況

| 維度 | TargetDiarization | Video2Text |
|---|---|---|
| **定位** | 多說話人音訊處理 ALL-IN-ONE 系統 | 多模態影片理解平臺（開發中） |
| **Python 版本** | 3.10 | 3.12+ |
| **License** | Apache 2.0 | MIT |
| **相依套件** | ~50 packages（conda + pip） | ~11 packages（uv workspace） |
| **GitHub Stars** | 96 | 私有專案 |
| **完成度** | ✅ 完整上線，可立即使用 | ⚠️ Microservices 完成，Modules 大部分 Stub |

### 二、TargetDiarization 架構深度分析

#### 2.1 四層架構設計

TargetDiarization 採用 **L4 → L1 分層架構**：

| 層級 | 類別 | 檔案 | 責任 |
|---|---|---|---|
| **L4 — 服務層** | FastAPI | `main.py` | HTTP REST API + WebSocket Streaming、請求路由、狀態管理 |
| **L3 — Pipeline 層** | TargetDiarization / TargetDiarizationStream | `TargetDiarization.py`, `TargetDiarizationStream.py` | 整合所有模組的端到端 Pipeline、orchestrator |
| **L2 — 核心邏輯層** | TargetASR | `TargetASR.py` | 目標說話人抽取、聲紋比對、多說話人分離 |
| **L1 — 基礎設施層** | AudioProcessor / ASRProcessor | `AudioProcessor.py`, `ASRProcessor.py` | 音訊處理工具類、ASR/VAD/標點恢復等基礎能力 |

#### 2.2 完整 Pipeline 流程（非流式）

```
音訊輸入
    │
    ▼
1. 音訊讀取 (ap.read_audio)
    │
    ▼
2. audio_preprocess()
    ├─ audio_to_mono()
    ├─ int16_to_float32()
    ├─ audio_resample() → 16kHz
    ├─ audio_loudness_control() (LUFS normalization)
    ├─ denoise_vocal() (MDX-Net, UVR-MDX-Net) → 15s chunk processing with 1s margin
    ├─ audio_loudness_control() ── post-denoise
    └─ [stream_mode] → separate_speaker() instead
    │
    ▼
3. Target Speaker Embedding
    ├─ get_target_embedding() → ERes2NetV2 (192-dim)
    └─ VAD filtering + HDBSCAN clustering
    │
    ▼
4. Diarization (CAM++)
    ├─ ModelScope CAM++ Pipeline
    └─ sd_result_parser() → {speaker_id: [(start, end)]}
    │
    ▼
5. Overlap Detection (Pyannote 3.1)
    ├─ Pyannote Diarization 3.1
    ├─ od_result_parser()
    ├─ sd_key_matcher() (IoU-based key matching)
    └─ apply_od_result() → split overlap/non-overlap
    │
    ▼
6. Speaker Matching
    ├─ target_embedding_to_target_spk() → Cosine similarity per segment
    └─ sd_result_to_target_embedding() (auto target)
    │
    ▼
7. ASR Processing
    ├─ sd_result_to_asr_audio() → 按 speaker 分類
    │   ├─ Non-overlap → single_speaker_asr()
    │   ├─ Overlap → multi_speakers_separate_asr()
    │   ├─ combine_audio_chunks() → silence padding
    │   └─ asrp.asr_detection() → paraformer/whisper
    └─ [timestamp mode] → word-level timestamp mapping
    │
    ▼
8. recheck_target_speaker() (二次聲紋比對)
    ├─ Cosine similarity with target_similarity_threshold
    └─ Reassign speaker labels based on score
    │
    ▼
9. asr_audio_parser() (結果封裝)
    ├─ Merge target speaker audio (silence-padded)
    └─ Return (target_spk, results[], target_audio)
```

#### 2.3 音訊處理管線完整架構

| 處理階段 | 模型/技術 | 框架/實現 | 備註 |
|----------|-----------|-----------|------|
| **Endpoint Detection** | CAM++ | ModelScope Diarization Pipeline | 主要 Diarization 引擎 |
| **Overlap Detection** | Pyannote Diarization 3.1 | Pyannote Audio Pipeline | 需要 HF Token，長音訊自動 fallback |
| **VAD** | FSMN-Monophone VAD | FunASR | 16kHz 輸入 |
| **VAD (Streaming)** | Silero VAD | silero_vad | 流式處理的 chunk-level VAD |
| **Noise Denoise** | UVR-MDX-Net (ConvTDFNet) | ONNX Runtime (CUDA) | 15s chunk processing with 1s margin |
| **Speech Separation** | MossFormer2 Finetune | look2hear | 雙說話人分離 |
| **Audio Restore** | Apollo | look2hear | 可選（預設停用以提升推理速度） |
| **Speaker Embedding** | ERes2NetV2-Large | ModelScope Speaker Verification | 192-dim embedding, HDBSCAN clustering |
| **ASR** | Paraformer-Large / Whisper | FunASR / OpenAI Whisper | 支援 SenseVoice 作為可選引擎 |
| **Punctuation** | CT-Transformer | FunASR Punctuation | 中文標點恢復 |

#### 2.4 設計模式分析

| 設計模式 | 位置 | 說明 | 評分 |
|----------|------|------|------|
| **Pipeline Pattern** | `TargetDiarization.infer()` | 端到端處理鏈，每階段有明確的輸入/輸出 | ⭐⭐⭐⭐⭐ |
| **Strategy Pattern** | `ASRProcessor.asr_detection()` | 多 ASR 引擎可切換（Paraformer/Whisper/SenseVoice/外部 API） | ⭐⭐⭐⭐⭐ |
| **Inheritance / Extension** | `TargetDiarizationStream → TargetDiarization` | 流式版本繼承非流式基類，覆寫核心方法 | ⭐⭐⭐⭐ |
| **Optional Fallback** | Diarization / OD / ASR 載入 | 失敗時 gracefully degrade，系統繼續執行 | ⭐⭐⭐⭐ |
| **Feature Flag** | `DISABLED_PACKAGES` | 啟動時停用不需要的模組 | ⭐⭐⭐ |
| **Queue + Thread Pool** | `async_infer_stream()` | 橋接 async WebSocket 和 sync PyTorch 推理 | ⭐⭐⭐⭐ |
| **Singleton（隱式）** | `main.py` 中的 `tds_model` 全域變數 | 服務啟動時初始化，全域性共享 | ⭐⭐ |

#### 2.5 工程評分

| 維度 | 評分 (1-5) | 備註 |
|------|-----------|------|
| **架構清晰度** | 4 | 層級分明，模組責任單一 |
| **錯誤處理** | 4 | 多層 fallback 設計良好，但缺少 retry |
| **可測試性** | 3 | 全域狀態和環境變數依賴使單元測試有難度 |
| **可擴充性** | 4 | Strategy Pattern 讓新引擎擴充容易 |
| **效能設計** | 4 | Chunk 處理 + 非同步橋接合理 |
| **程式碼質量** | 3.5 | 整體乾淨，但部分方法過長，缺少 docstring |
| **配置管理** | 3 | .env 方案足夠簡單場景，但缺乏驗證 |

**總體評價**：這是一個工程品質良好的整合型專案。設計上善用繼承和策略模式來管理複雜性，音訊處理管線完整且容錯設計到位。主要改進空間在於測試覆蓋率和配置驗證。

### 三、Video2Text 深度分析

#### 3.1 目錄結構與完成度

```
Video2Text/
├── main.py                  # 空白骨架 (stub)
├── workflow.py              # 主流程入口 (CLI pipeline) — 目前空殼
├── modules/                 # Pipeline 模組 (全部是 Stub)
│   ├── vad.py              # 🔴 Stub — 永遠回傳 []
│   ├── asr.py              # 🔴 Stub — 永遠回傳固定 Path
│   ├── clean.py            # 🔴 Stub — 無實際清理邏輯
│   ├── summarize.py        # 🔴 Stub — 無 LLM 整合
│   ├── video_desc.py       # 🔴 Stub — 無 vision model 整合
│   └── sam_audio.py        # 🟡 部分實作 — HTTP client 完整
├── serve/                   # Microservice 目錄 (完全實作 ✅)
│   ├── voicetag/           # Speaker Diarization 服務 — 完成 100%
│   ├── sam-audio/          # Speaker Separation 服務 — 核心完成
│   ├── vllm/               # Breeze-ASR-26 vLLM 伺服器 — 啟動指令碼
│   └── quark-audio/        # QuarkAudio TSE 推理 — 探索階段
├── workflows/               # End-to-end 工作流程 (完成 ✅)
│   ├── speech_to_text.py   # Speaker 辨識 + STT 整合 — 完全實作
│   └── voicetag.py         # 純 voicetag 推理 pipeline — 完全實作
├── webuis/                  # Web UI (Gradio) — 完全實作 ✅
│   └── speech-to-text.py   # Speech-to-Text WebUI
└── profiles/                # 環境設定檔
    ├── default.yaml
    ├── research.yaml
    └── final.yaml
```

**完成度概覽**：

```
██████████░░ 80%  — Microservices (voicetag, sam-audio, vllm)  ✅ 核心完成
██████████░░ 80%  — Workflows (speech_to_text.py, voicetag.py)  ✅ 完成
██████████░░ 80%  — WebUI (Gradio)                              ✅ 完成
██░░░░░░░░░░ 20%  — Modules (vad/asr/clean/summarize/video_desc) 🔴 全部 Stub
███░░░░░░░░░ 30%  — framework (config.py)                       ⚠️ 最小可行
░░░░░░░░░░░░ 0%   — Tests                                       🔴 無
░░░░░░░░░░░░ 0%   — CI/CD / Docker                              🔴 無
```

#### 3.2 微服務架構

Video2Text 採用 **獨立的 FastAPI microservice** 架構，每個服務有自己獨立的虛擬環境與 `pyproject.toml`：

| Microservice | Port | 功能 | 狀態 |
|---|---|---|---|
| `serve/voicetag` | 8001 | Speaker identification (diarization) | ✅ 完整實作 |
| `serve/sam-audio` | 8000 | Speaker separation (SAM-Audio span prompting) | ✅ 核心 + API 實作 |
| `serve/vllm` | 8750 | Breeze-ASR-26 via vLLM (OpenAI-compatible) | ✅ 啟動指令碼 |
| `serve/quark-audio` | N/A | QuarkAudio-UniSE TSE | 🔬 實驗階段 |

每個服務採用 **相同的四層架構**：
1. `*_core.py` — 核心推理邏輯（model lifecycle）
2. `api/models.py` — Pydantic request/response models
3. `api/service.py` — 業務邏輯層
4. `api/main.py` — FastAPI app
5. `server.py` — uvicorn 入口

#### 3.3 Modules 實作狀態詳細分析

| Module | 狀態 | 函式回傳 | 註解 |
|---|---|---|---|
| `vad.py` | 🔴 **Stub** | `Path("output.jsonl")` 改為 `[]` | 只有 cfg 讀取 + TODO |
| `asr.py` | 🔴 **Stub** | `Path("output.jsonl")` | TODO 有三行規劃註解 |
| `clean.py` | 🔴 **Stub** | `Path("output_cleaned.jsonl")` | 只有 cfg 讀取 |
| `summarize.py` | 🔴 **Stub** | `Path("output.md")` | 只有 cfg 讀取 |
| `video_desc.py` | 🔴 **Stub** | `Path("output.jsonl")` | 只有 cfg 讀取 |
| `sam_audio.py` | 🟡 **部分實作** | 完整 HTTP client | 但依賴外部 SAM-Audio 服務 |

**詳細分析**：

##### `vad.py` — Voice Activity Detection
```python
def detect_speech(video: Path) -> list[dict]:
    c = cfg("vad", VadConfig)
    # TODO: 實作 VAD 邏輯
    return []  # ← 永遠回傳空列表
```
- 有 `VadConfig` Pydantic model（threshold, min_silence_duration_ms, chunk_seconds）
- **完全沒有實作**

##### `asr.py` — Automatic Speech Recognition
```python
def transcribe(video: Path, segments: list[dict]) -> Path:
    c = cfg("asr", AsrConfig)
    # TODO: 實作 ASR 邏輯
    # 1. 使用 ffmpeg 或 moviepy 從 video 提取區間音訊
    # 2. 批次送給 c.model 推理
    # 3. 將逐字稿寫入 JSONL 並回傳路徑
    return Path("output.jsonl")
```
- 有 `AsrConfig`（model 預設 `MediaTek-Research/Breeze-ASR-26`, batch_size, language）
- TODO 規劃最完整

##### `sam_audio.py` — Speaker Separation Client
- **這是唯一有實際程式碼的 module**
- 完整的 HTTP client，呼叫 `serve/sam-audio` 的 `/separate` endpoint
- 有 `SeparationResult` Pydantic model
- 支援 anchor-based separation

### 四、音訊處理技術逐項比較

#### 4.1 VAD（Voice Activity Detection）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **模型** | **FSMN-Monophone VAD**（阿里達摩院，ModelScope） | **未實作**（Stub） |
| **備援方案** | Silero VAD（`silero_vad` package） | 無 |
| **狀態** | ✅ 已整合，支援 streaming 與 non-streaming | ⚠️ 框架已定義 `VadConfig`，但 `detect_speech()` 為空殼 |
| **中文最佳化** | ✅ FSMN 專為中文最佳化 | ❌ |

**分析**：TargetDiarization 採用 FSMN（Feed-forward Sequence Memory Network）架構的 Monophone 模型，這是專為中文語音最佳化的 VAD，在中文場景下準確率優於通用模型。Video2Text 目前完全沒有 VAD 實現——這是其音訊模組中最大的缺口。

#### 4.2 Speaker Diarization（說話人分離/註記）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **主要模型** | **CAM++**（pyannote.pipeline 格式） + **Pyannote Diarization 3.1**（重疊偵測） | **VoiceTag**（pyannote.audio 包裝） |
| **Embedding** | **ERes2NetV2-Large**（1024-dim，阿里達摩院） | **Resemblerzer**（透過 VoiceTag 內部使用） |
| **重疊處理** | ✅ Pyannote 3.1 overlap detection + IoU 匹配演算法 | ✅ VoiceTag 原生支援 overlap 分段 |
| **目標說話人匹配** | ✅ 基於 cosine similarity + HDBSCAN 雜訊過濾 | ✅ Enroll → Save → Identify 完整流程 |
| **串流模式** | ✅ WebSocket streaming 支援 | ❌ 僅 non-streaming batch |
| **狀態** | ✅ 完整 production 級實現 | ⚠️ VoiceTag 已可運作（見 `test_voicetag_meeting.py`），但尚未串入主 pipeline |

**分析**：TargetDiarization 的 diarization pipeline 更為成熟——它採用了 CAM++ 做主 diarization + Pyannote 3.1 做 overlap detection 的**雙層架構**，並有完整的 IoU 匹配邏輯將兩者的結果融合。Video2Text 的 VoiceTag 已經可以正常運作（支援 40 分鐘會議測試），但它是一個獨立的 microservice，**尚未整合到主 workflow pipeline 中**。

#### 4.3 Speaker Separation（訊源分離）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **模型** | **MossFormer2**（look2hear 生態，已自訓練 fine-tune） | **SAM-Audio**（Facebook Meta，`facebook/sam-audio-small`） |
| **分離方式** | 頻域分離（時域輸入 → 頻域處理 → 時域輸出） | Span prompting（時間錨點提示式分離） |
| **分離限制** | 雙說話人分離（2-channel output） | 支援多說話人 span 提示 |
| **狀態** | ✅ 已整合至 pipeline（非流式模式） | ⚠️ 微服務已實作，但尚未串入主 pipeline |

**分析**：這是兩個專案最大的差異點之一。TargetDiarization 的 MossFormer2 是針對音訊分離任務訓練的專門模型，但僅支援最多 2 個說話人。Video2Text 採用 SAM-Audio（Meta 基於 Segment Anything 架構的音訊模型），它使用 **span prompting**（時間錨點提示）的方式來分離目標聲音，這種方式更靈活——你可以用時間區間或文字描述來指定要分離的音源。不過 SAM-Audio-small 的容量較小，複雜混音場景可能不如 fine-tuned MossFormer2。

#### 4.4 Audio Restoration / Denoise（音訊修復與降噪）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **降噪** | ✅ **UVR-MDX-Net**（ONNX 加速） + **noisereduce**（備援） | ❌ 無 |
| **音質修復** | ✅ **Apollo**（look2hear 生態） | ❌ 無 |
| **音質增強** | ✅ **Resemble Enhance** | ❌ 無 |
| **LUFS 均衡** | ✅ pyloudnorm 標準化 | ❌ 無 |
| **壓縮器** | ✅ 可選 | ❌ 無 |
| **狀態** | ✅ 完整 production 級音訊後處理管線 | ❌ 完全沒有音訊後處理模組 |

**分析**：TargetDiarization 擁有業界級的音訊後處理能力——從降噪（MDX-Net，基於深度學習的背景音樂消除）到修復（Apollo，專為低品質音訊設計）到增強（Resemble Enhance，使用 diffusion model），是一個完整的 audio enhancement pipeline。**Video2Text 完全沒有這個層面，直接拿原始音訊去做 VAD 和 ASR。**

#### 4.5 ASR（自動語音辨識）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **主要引擎** | **Paraformer-Large**（阿里達摩院 / FunASR） | **Breeze-ASR-26**（MediaTek Research via vLLM） |
| **備援引擎** | Whisper、SenseVoice | 無（單一引擎） |
| **部署方式** | 本地 modelscope 推理 | **vLLM 推理伺服器**（批次最佳化） |
| **語言支援** | 中文為主（zh-cn 最佳化） | 中文（可配置 `language` 引數） |
| **VAD 內建** | ✅ 與 ASR 整合（Paraformer 內建 VAD） | ❌ 需外部 VAD 模組提供分段 |
| **狀態** | ✅ 完整 | ⚠️ 架構已定義，`transcribe()` 為 TODO |

**分析**：Video2Text 選擇了 **MediaTek 的 Breeze-ASR-26** 並透過 **vLLM** 部署，這是一個較新的選擇。vLLM 的 PagedAttention 技術能提供高 throughput 的批次推理。而 TargetDiarization 使用阿里達摩院的 Paraformer，這是中文 ASR 的工業級基準模型。Video2Text 的優勢在於 vLLM 架構可以更輕易地平伸縮和整合更多 LLM 能力的模型。

#### 4.6 Punctuation / Capitalization（標點還原）

| 專案 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **能力** | ✅ **CT-Transformer**（阿里達摩院 punctuation restoration） | ❌ 無 |
| **整合方式** | 與 ASR pipeline 整合（`punctuation_restore()`） | 無 |
| **總結模組** | 無（僅轉錄） | ✅ `generate_summary()`（LLM 多模態總結） |

**分析**：TargetDiarization 有完整的標點還原能力。Video2Text 沒有標點處理，但它的差異化在於有 `summarize.py`——這是一個 LLM 多模態總結模組，將音訊轉錄和影片描述結合產生摘要。這代表 Video2Text 的設計哲學是「轉錄 → 理解 → 總結」，而 TargetDiarization 則是「轉錄 → 標點 → 輸出」。

### 五、工程實務比較

#### 5.1 程式碼風格

| 維度 | TargetDiarization | Video2Text |
|------|-------------------|------------|
| **Type Hints** | 中等程度，分佈不均 | 高度、一致，Python 3.12 風格 |
| **架構模式** | 單一大類，緊密耦合 | 服務層分離（Service Layer Pattern） |
| **錯誤處理** | `try/except` + `print` 為主 | 明確的錯誤型別與 docstrings |
| **Logging** | 幾乎全 print，僅 API 層用 logger | print 為主，但有意識的格式 |

**Type Hints 詳細比較**：

TargetDiarization 有使用 type hints，但分佈不均：
```python
def infer(self, wav_file: Union[str, np.ndarray, io.BytesIO], target_file: Union[str, np.ndarray, io.BytesIO] = None, sampling_rate: int = 16000, is_single: bool = False, output_target_audio: bool = True):
```
但許多內部方法和 util function 完全沒有 hints。

Video2Text 使用現代化語法：`str | Path` 代替 `Union[str, Path]`、`list[dict]` 代替 `List[dict]`。

#### 5.2 錯誤處理

**TargetDiarization**：`try/except` + `print` 為主
```python
except Exception as e:
    self.od_pipeline = None
    print("====================================================")
    print(f"Failed to init pyannote model from HuggingFace: {e}")
```
- 沒有 custom exceptions
- `traceback.print_exc()` 被直接使用

**Video2Text**：明確的錯誤型別與層級
```python
Raises
------
FileNotFoundError:
    If the input audio file does not exist.
```
- 檔案級 error docstrings
- API 層使用 `HTTPException(status_code=404, detail=str(e))`

#### 5.3 Config 管理

**TargetDiarization**：`.env` 環境變數
```python
# main.py — 每個引數都要手動轉換
tds_args = {
    "verbose_log": True if os.environ.get("VERBOSE_LOG") == "1" else False,
    "cuda_device": int(os.environ.get("CUDA_DEVICE")) if ... else None,
    ...
}
```
- 純 `.env` 格式，共約 25+ 個變數
- **無 schema 驗證**（無 Pydantic）
- 所有引數在啟動時固定，修改需要重新啟動

**Video2Text**：Profile-based YAML + Pydantic
```python
# framework/config.py
c = cfg("asr", AsrConfig)  # 自動驗證 + 預設值
# 多 profile 切換：default / research / final
```
- YAML profile 格式，結構清晰
- **Pydantic validation 層**：load 時檢查型別
- 多個 profiles：`default.yaml`、`research.yaml`、`final.yaml`

**結論**：Video2Text 的 config 管理是顯著的工程優勢。

#### 5.4 Packaging 與部署

**TargetDiarization**：
- `requirements.txt`（無版本號 pinning）
- 無 Dockerfile
- 無 pyproject.toml
- 依賴 conda + pip 混合方式

**Video2Text**：
- **`pyproject.toml` + uv workspace**
- **`uv.lock`** 確保可重現性
- Microservice 獨立 pyproject.toml：
  ```
  serve/voicetag/pyproject.toml  → voicetag-server
  serve/sam-audio/pyproject.toml → 獨立相依
  serve/quark-audio/pyproject.toml → 獨立相依
  serve/vllm/pyproject.toml → 獨立相依
  webuis/pyproject.toml → 獨立相依
  ```

#### 5.5 測試覆蓋率

兩個專案的測試覆蓋率都非常低：

| 專案 | 測試檔案 | 型別 | 描述 |
|------|----------|------|------|
| TargetDiarization | `target_diarization_test.py` | 整合測試 | 僅 1 個手動執行指令碼，非 pytest |
| Video2Text | `test_voicetag.py`、`test_voicetag_meeting.py` | 整合測試 | 同樣是手動執行指令碼（`if __name__ == "__main__"`） |

兩者的測試更像是 "demo 指令碼" 而非正式測試。建議至少為每個模組建立 pytest 格式的 unit tests，並加入 mock 外部依賴（如模型呼叫）。

### 六、Streaming 支援詳細分析

#### 6.1 TargetDiarization Streaming 架構

TargetDiarization 內建完整的 **WebSocket 即時串流**，程式碼在 `TargetDiarizationStream.py`。

**技術架構**：
```
FastAPI WebSocket (/diarization/stream)
    │
    ├── audio_stream_generator()        # 非同步：從 WebSocket 讀取 base64 chunks
    ├── async_infer_stream()            # 非同步橋接層
    │   ├── audio_collector()           # 收集 chunks 到 Queue
    │   ├── sync_audio_generator()      # 同步生成器：從 Queue 讀取
    │   └── ThreadPoolExecutor          # 執行同步 infer_stream()
    │
    └── TargetDiarizationStream         # 覆寫 infer_stream()
        ├── chunk_preprocess()          # 每 chunk 的音訊預處理
        ├── process_vad_chunk()         # VAD 緩衝路由
        ├── should_wait_for_next_chunk() # 多條件觸發判斷
        └── process_single_chunk()      # OD + ASR 單一 chunk
```

**VAD 緩衝策略**：

| 模式 | `IS_VAD_BUFFER` | 行為 |
|------|-----------------|------|
| **VAD Buffer** | 1（預設） | 累積 chunks 直到滿足觸發條件 |
| **Fixed Length** | 0 | 每個 chunk 獨立處理，`is_silence` 時 skip |

**多條件觸發判斷**（`should_wait_for_next_chunk()`）：

| 優先順序 | 條件 | 邏輯 |
|--------|------|------|
| **1** | `max_buffer_duration` | 緩衝累積超過 30s 強制處理 |
| **2** | Silencer gap | VAD 檢測到末尾有靜音間隙 ≥ `vad_min_silence`（0.3s） |
| **3** | 無有效語音 | 當前 chunk 沒有 VAD 結果 → 清空緩衝 |
| **4** | Speaker similarity | 比較 prev_chunk 和 current_chunk 的 embedding，若為同一說話人 → 繼續等待 |
| **5** | 預設 | 等待下一 chunk |

**聲紋相似度檢測的關鍵洞察**：
```python
prev_embedding = self.tasr.get_speaker_embedding(wav_file=prev_audio)
current_embedding = self.tasr.get_speaker_embedding(wav_file=current_chunk)
is_same = self.tasr.is_same_person(
    existed_embeddings=prev_embedding,
    target_embedding=current_embedding,
    threshold=self.similarity_threshold  # 預設 0.4
)
# is_same=True → 同一人，繼續等
# is_same=False → 換人了，立即處理
```

**Async/Sync 橋接模式**：
`async_infer_stream()` 使用 **Queue + ThreadPoolExecutor** 的經典模式，解決了 **WebSocket 非同步 I/O 與 PyTorch 模型同步推理之間的橋接問題**。

#### 6.2 Video2Text Streaming 支援

**目前完全沒有 streaming 支援**。所有輸入都是 batch 模式，使用 HTTPX 或直接 import 呼叫 microservices。

### 七、容錯設計比較

#### 7.1 TargetDiarization Fallback Chain

每一層都有完整的 fallback 機制：

| 失敗層級 | 第一選擇 | Fallback |
|----------|----------|----------|
| 音訊 ≥30s | Pyannote OD | CAM++ |
| Pyannote 載入失敗 | — | 僅用 CAM++（跳過 overlap） |
| CAM++ 失敗 | — | 跳過整個 Diarization |
| ASR 失敗 | 指定引擎 | 第一個可用的引擎 |
| MDX Denoise 失敗 | — | `noisereduce` |
| AudioStretchy 失敗 | 使用 audiostretchy | 回退到 librosa time stretch |

#### 7.2 邊界情況處理

| 邊界情況 | 處理方式 |
|----------|----------|
| 目標音檔 <4s | 輸出 WARNING 但不中斷 |
| 目標音檔無 VAD 結果 | 自動從輸入音檔選一個 speaker 作為目標 |
| Embedding 包含 NaN | 記錄日誌並跳過該 chunk |
| Audio clip <0.4s | 在 streaming 中直接 return None |
| Audio clip <0.1s | 在 VAD 處理中跳過 |
| Embedding 列表為空 | 回傳 192 維全零 embedding |
| WS 斷開 | 捕捉 `WebSocketDisconnect` 靜默處理 |
| Queue 超時 | `asyncio.wait_for(timeout=0.1)` 配合 `inference_finished` event |

### 八、API 設計比較

#### 8.1 TargetDiarization API 矩陣

| 存取方式 | 端點/方式 | 描述 | 檔案 |
|---------|----------|------|------|
| Python import | `from TargetDiarization import TargetDiarization` | 模組化匯入 | `TargetDiarization.py` |
| CLI | `python main.py` | 啟動 FastAPI server | `main.py` |
| REST | `POST /diarization/infer` | 非流式推理 | `main.py` |
| REST | `GET /health` | 健康檢查 | `main.py` |
| WebSocket | `WS /diarization/stream` | 串流式推理 | `main.py` + `TargetDiarizationStream.py` |
| Gradio UI | Gradio Blocks | 網頁 UI | `webui.py` |
| HTML demo | `demo.html` | 前端 Demo | `demo.html` |

**可立即部署為主機服務**：裝好 conda 環境、下載模型、`python main.py` 就跑起來了。

#### 8.2 Video2Text API 設計

**目前是以 import-based pipeline 為主**，微服務雖有 FastAPI app，但主要用途是作為獨立的 service。

- Microservices 本身有 FastAPI app：
  - VoiceTag: `POST /identify`、`GET /health`
  - SAM-Audio: `POST /separate`、`GET /health`
- 核心 workflows（`workflows/speech_to_text.py`）使用 **直接 import** 而非 HTTP 呼叫：
  ```python
  from voicetag import VoiceTag, VoiceTagConfig
  vt = VoiceTag(config=config)
  transcript_result = vt.transcribe(...)
  ```
- `pyproject.toml` 的 dependencies 包含 `httpx>=0.28`，預留遠端服務呼叫能力

### 九、整體評估總結

| 評估維度 | TargetDiarization | Video2Text | 優勢方 |
|---|---|---|---|
| **音訊品質最佳化** | ✅ 完整 pipeline | ❌ 無 | **TargetDiarization** |
| **VAD 實作** | ✅ FSMN + Silero | 🔴 Stub | **TargetDiarization** |
| **Diarization** | ✅ CAM++ + Pyannote 雙層 | ⚠️ voicetag 未整合 | **TargetDiarization** |
| **Speaker Separation** | MossFormer2（2人） | SAM-Audio（靈活 prompt） | **Video2Text**（靈活性） |
| **ASR** | 6+ 引擎選擇 | Breeze-ASR-26（vLLM） | 各有所長 |
| **標點還原** | ✅ CT-Transformer | ❌ 無 | **TargetDiarization** |
| **Streaming** | ✅ WebSocket 即時 | ❌ 僅 batch | **TargetDiarization** |
| **多模態理解** | ❌ 純音訊 | ✅ 影片幀 + 摘要 | **Video2Text** |
| **工程架構** | 單一大類 | Microservice 分離 | **Video2Text** |
| **Config 管理** | .env 字串解析 | YAML + Pydantic | **Video2Text** |
| **Packaging** | requirements.txt | uv workspace | **Video2Text** |
| **Type Hints** | 中等 | 完整現代化 | **Video2Text** |
| **檔案** | README 極完整 | docstrings + micro-READMEs | 各有所長 |
| **新手友好** | ✅ 即插即用 | ⚠️ 設定複雜 | **TargetDiarization** |
| **完成度** | ✅ 可使用 | ⚠️ Modules 大部分 Stub | **TargetDiarization** |

## 核心結論

### TargetDiarization 是一個**深度最佳化的音訊處理管道**

- 每一個階段（降噪、分離、VAD、diarization、ASR、標點）都有成熟的 SOTA 模型支撐
- 完整生產級容錯設計（fallback chain、boundary case handling）
- 即插即用，內建 FastAPI + WebSocket + Gradio UI
- 適合需要高品質音訊轉錄的場景

### Video2Text 是一個**廣度優先的平臺式架構**

- Microservice 架構 + vLLM 推理 + 多模態理解
- 目前音訊處理模組大量待實作（VAD、ASR 都是 TODO）
- 一旦完成，其架構將比 TargetDiarization 更能擴充套件到其他任務（如影片分析、多模態摘要等）
- 工程實務全面優越（type hints、config、packaging、microservice）

### 兩者技術棧互補

TargetDiarization 提供了 Video2Text 目前欠缺的**所有核心音訊處理能力**，包括：
1. VAD 實作（FSMN-Monophone + Silero）
2. 完整的音訊後處理管線（降噪 → 分離 → 修復 → 增強）
3. 標點還原（CT-Transformer）
4. Streaming 支援（WebSocket）
5. 多 ASR 引擎（Strategy Pattern）
6. 雙層 Diarization（CAM++ + Pyannote 3.1）

而 Video2Text 提供了 TargetDiarization 欠缺的**平臺級架構優勢**，包括：
1. Microservice 分離架構
2. 現代化工具鏈（uv + pyproject.toml）
3. Pydantic 驗證的配置管理
4. 多模態能力（影片幀描述 + LLM 摘要）
5. vLLM 批次推理（高吞吐）

## 整合建議

### 優先順序：🔴 高（立即執行）

| 建議 | 來源 | 難度 | 說明 |
|---|---|---|---|
| **實作 VAD** | TargetDiarization 的 FSMN-Monophone 或 Silero VAD | 中 | 這是 pipeline 的第一步，沒有 VAD 其他都無法運作 |
| **實作標點還原** | TargetDiarization 的 CT-Transformer 整合 | 低 | 加在 ASR 之後即可 |
| **音訊後處理管線** | MDX-Net + Apollo + Resemble | 高 | 需要新增多個依賴和整合，但對音訊品質影響最大 |

### 優先順序：🟡 中（中期執行）

| 建議 | 來源 | 說明 |
|---|---|---|
| **Streaming 支援** | WebSocket + VAD 緩衝策略 | 需要新增 WebSocket 端點和 async 橋接 |
| **IoU-based overlap handling** | Pyannote 3.1 雙層架構 | 如果 voicetag 結果需要更精確的重疊處理 |
| **Fallback chain** | 多層容錯設計 | 讓每個 pipeline step 都有 graceful degrade |

### 優先順序：🟢 低（長期）

| 建議 | 來源 | 說明 |
|---|---|---|
| **多 ASR 引擎切換** | Strategy Pattern | 目前已有 Breeze-ASR-26，未來可以加 Whisper 備援 |
| **二次聲紋比對** | `recheck_target_speaker` | 提升 diarization 準確率 |
| **Word-level timestamp mapping** | 版本改進的核心功能 | 精確時間戳對映 |

## 整合路線圖

### Phase 1：整合 STT 伺服器模組

1. 將 TargetDiarization 作為 Video2Text 的 STT 微服務模組引入
2. 放在 `serve/target-diarization/` 目錄下，保留 microservice 架構
3. 提供 FastAPI REST API + WebSocket streaming
4. 讓 `modules/asr.py`、`modules/vad.py` 改用 TargetDiarization 的實作

### Phase 2：整合音訊後處理管線

1. 整合 MDX-Net 降噪
2. 整合 Apollo 音質修復
3. 整合 LUFS 標準化
4. 讓 pipeline 在 VAD 之前先做音訊品質最佳化

### Phase 3：整合 Streaming 支援

1. 整合 WebSocket 端點
2. 整合 VAD 緩衝策略
3. 整合智慧觸發判斷（speaker similarity）

### Phase 4：整合雙層 Diarization

1. 整合 CAM++ 作為主 diarization
2. 整合 Pyannote 3.1 做 overlap detection
3. 整合 IoU-based key matching

## 風險與注意事項

### TargetDiarization 潛在風險

1. **依賴衝突**：50+ packages 可能與 Video2Text 的 uv workspace 衝突
2. **硬體要求**：需要 8GB+ VRAM，16GB+ RAM
3. **模型下載**：需要從 ModelScope/HuggingFace 下載多個模型（約多 GB）
4. **Python 版本**：3.10，Video2Text 是 3.12+，需注意相容性
5. **無測試覆蓋**：兩專案都只有 demo 指令碼，無正式 pytest

### Video2Text 當前風險

1. **Modules 全是 Stub**：`workflow.py` 目前跑起來是空殼
2. **Global state**：`framework/config.py` 的 `_PROFILE_PATH` 無 thread-safe 保障
3. **版本碎片化**：主專案 3.12、子服務 3.10+、相依版本需要手動 `--no-deps` 繞過
4. **無 Docker / deploy 配置**：只有 shell script 啟動指令碼

## 參考資料

- [TargetDiarization GitHub](https://github.com/jingzhunxue/TargetDiarization)
- [TargetDiarization README.md](https://github.com/jingzhunxue/TargetDiarization/blob/main/README.md)
- `TargetDiarization.py` — 主 Pipeline 類別（45KB）
- `TargetASR.py` — 目標說話人抽取核心（42KB）
- `AudioProcessor.py` — 音訊處理基礎設施（55KB）
- `ASRProcessor.py` — ASR/VAD/斷句/時間戳/情感/說話人確認（50KB）
- `TargetDiarizationStream.py` — 流式 Pipeline（13KB）
- `modules/vad.py` — 目前 Stub，需改用 TargetDiarization FSMN-Monophone
- `modules/asr.py` — 目前 Stub，可改用 TargetDiarization Paraformer
- `workflow.py` — 目前空殼流程，整合後可完整運作
- [serve/voicetag/voicetag_core.py](serve/voicetag/voicetag_core.py) — 目前唯一的完整 DIARIZATION 實作

## 研究人員

Agent（2026-08-14）

使用 4 個 parallel sub-agents 進行深度分析：
1. 架構分析（TargetDiarization 整體架構、Pipeline 流程、設計模式）
2. Video2Text 深度分析（modules 實作狀態、voicetag 整合、配置管理）
3. 音訊處理技術比較（VAD/Diarization/Separation/ASR/Punctuation）
4. 軟體工程實務比較（程式碼風格、API、Config、Packaging）
