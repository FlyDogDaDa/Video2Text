# Video2Text

影片／音訊轉文字管線：對輸入影片先做語音活動偵測（VAD）切出說話段落，逐段語音辨識（ASR）產生逐字稿，同時以視覺模型抽取逐幀畫面描述；接著以 LLM 清除逐字稿冗詞，最後整合音訊與畫面兩路資訊產出摘要。

```
video.mp4 ─┬─ VAD ──▶ ASR（逐字稿 JSONL）──┐
           │                              ├─▶ 冗詞清除 ──▶ 摘要
           └─ 影片描述（逐幀 caption）──────┘
```

主入口為 `workflow.py`，五個階段以明確的函式呼叫依序執行，各階段參數由 profile YAML 提供。

## 目錄結構

```
Video2Text/
├── workflow.py            # 主入口：VAD → ASR → 影片描述 → 冗詞清除 → 摘要
├── modules/               # 管線模組（每階段一檔，附 pydantic 設定模型）
├── framework/             # 設定載入：profile YAML + pydantic 驗證（framework/config.py）
├── profiles/              # default / final / research 三種設定檔
├── workflows/             # 獨立管線腳本
├── serve/                 # 五個隔離微服務（各自 .venv）
├── webuis/                # Gradio 網頁介面
├── scripts/               # 手動煙霧測試腳本
├── data/                  # 本機產物樹（media/、out/、tmp/），整體 gitignore
└── chat_with_my_agent/    # agent 開發對話紀錄（本地參考用）
```

### modules/ — 管線模組

| 模組 | 用途 |
|---|---|
| `modules/vad.py` | 以靜音為基礎切出說話段落（`threshold`、`min_silence_duration_ms`、`chunk_seconds`） |
| `modules/asr.py` | 將各段送語音辨識（預設 `MediaTek-Research/Breeze-ASR-26`），輸出 JSONL 逐字稿 |
| `modules/video_desc.py` | 以視覺模型取逐幀 caption（`fps` 預設 1.0） |
| `modules/clean.py` | LLM 輔助移除逐字稿重複／近重複段落（`chunk_size` 分塊處理） |
| `modules/summarize.py` | 整合清洗後逐字稿與影片描述，產生多模態摘要 |
| `modules/sam_audio.py` | SAM-Audio 的輕量 HTTP client；重型模型邏輯在 `serve/sam-audio` |

### framework/ 與 profiles/

`framework/config.py` 以全域 profile 路徑運作：啟動時由 `workflow.py` 呼叫 `set_profile()` 設定 YAML 檔，各模組再以 `cfg(key, model)` 讀取對應區段並用 pydantic 模型驗證。

| Profile | 差異 |
|---|---|
| `profiles/default.yaml` | 全部採預設值，含 `sam_audio` 區段（`facebook/sam-audio-small`、`cuda:2`） |
| `profiles/final.yaml` | `summarize.temperature` 降為 0.7，ASR 模型改為 `google/gemma-4-12B-it-qat-w4a16-ct` |
| `profiles/research.yaml` | 放寬 VAD（`threshold` 0.4、`chunk_seconds` 180），ASR `batch_size` 降為 32 |

### workflows/ — 獨立管線腳本

- `workflows/quark-audio.py` — QuarkAudio-UniSE 目標說話人提取（TSE）推理腳本，呼叫 `serve/quark-audio` 的 Python API。
- `workflows/speech_to_text.py` — 整合 voicetag（speaker diarization）與 Breeze-ASR-26（STT），輸出「誰在何時講了什麼」JSON。
- `workflows/voicetag.py` — voicetag speaker identification 端到端腳本。

## 快速開始

```bash
# 安裝主專案相依（uv 管理，Python >= 3.12）
uv sync

# 執行完整管線（--profile 預設即 profiles/default.yaml，可省略）
uv run python workflow.py --input video.mp4 --profile profiles/default.yaml
```

各階段進度會直接印在 stdout（VAD 段數、逐字稿、影片描述、清洗結果、最終摘要）。

## serve/ — 隔離微服務

| 服務 | 用途 | 啟動方式 |
|---|---|---|
| `serve/vllm` | vLLM ASR 後端：Breeze-ASR-26 與 MOSS-Transcribe-Diarize 兩組啟動腳本 | `PORT=8750 bash serve/vllm/launch_MOSS_TD.sh`；`bash serve/vllm/launch_BreezeASR26.sh` |
| `serve/stt-api` | 長音訊會議轉錄 HTTP API（port 8760）：上傳 → 輪詢 → 取回含全域語者標籤的 JSON 逐字稿；依賴 MOSS TD vLLM（port 8750） | `cd serve/stt-api && .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8760` |
| `serve/voicetag` | Speaker diarization + identification API（port 8001，`/identify`、`/health`）：回答「誰在何時說話」 | `serve/voicetag/.venv/bin/python serve/voicetag/server.py`（需 `HF_TOKEN`） |
| `serve/sam-audio` | SAM-Audio 聲音分離服務（port 8000）：依 anchor 時段與文字描述分離目標聲音，回傳 speaker／residual 兩軌 | `serve/sam-audio/.venv/bin/python serve/sam-audio/start_server.py`（安裝 SOP 見 `serve/sam-audio/INSTALL.md`） |
| `serve/quark-audio` | QuarkAudio-UniSE 目標說話人提取（TSE）Python API：從混合音訊中抽取指定說話人 | 無常駐 HTTP 服務；權重先以 `download_checkpoints.sh` 下載，再由 `workflows/quark-audio.py` 以 Python API 呼叫 |

細節請參考各服務目錄內的說明文件：`serve/stt-api/README.md`、`serve/voicetag/README.md`、`serve/sam-audio/INSTALL.md`。

### webuis/ — Gradio 網頁介面

- `webuis/speech-to-text.py` — 上傳音訊 → diarization + STT → 下載 JSON；另附 speaker 參考檔管理（上傳、改名、刪除）。
  執行：`uv run --directory serve/voicetag -- python -m webuis.speech_to_text`
- `webuis/moss-playground.py` — MOSS-Transcribe-Diarize 單頁 playground：上傳即送 vLLM，輸出簡體原文、OpenCC 轉繁結果與 segments JSON。
  執行：`uv run --project webuis webuis/moss-playground.py`（環境變數 `MOSS_VLLM_URL`、`MOSS_PLAYGROUND_PORT`，預設 7862）

## 設計說明：為什麼 serve/* 各自帶獨立 .venv

五個服務的依賴版本互相衝突，也與主專案不同，單一環境無法同時滿足：

- `serve/quark-audio` 需要 `transformers==4.46.1`（Python >= 3.10），主專案是 Python >= 3.12。
- `serve/sam-audio` 的 `perception-models` 硬編 `decord==0.6.0`（Python 3.12 無 Linux wheel，須以 `decord2` 替代），且 `transformers` 必須 `<5.0`、`setuptools<69`，需 `--no-deps` 手動安裝——uv 的 dependency override 無法穿透第二層相依（詳見 `serve/sam-audio/INSTALL.md`）。
- `serve/voicetag` 依賴 `pyannote.audio`、`torch>=2.0`；`serve/vllm` 鎖定自己的 vLLM 版本；`webuis` 的 torch 則固定走 cu130 index。

因此每個服務各自帶 `.venv`，CUDA／torch 版本彼此隔離，也與主專案解耦：各服務可獨立啟動／停止、獨立升級，不互相汙染。

## 開發注意

- 測試框架為 **pytest**，放在 dev dependency group：`uv sync --group dev` 後以 `uv run pytest` 執行。
- **`.venv/` 與資料檔不入 git**：`.gitignore` 已涵蓋 `.venv`（含各 `serve/*/.venv`）、`data/`（本機產物樹）、`exp/`、`serve/stt-api/jobs/`、`serve/quark-audio/checkpoints/` 等。
- voicetag 與 sam-audio 的模型位於 Hugging Face gated repo，需設定 `HF_TOKEN` 並接受模型授權。
- `serve/stt-api` 為內網限定、無鑑別服務，勿暴露公網。
