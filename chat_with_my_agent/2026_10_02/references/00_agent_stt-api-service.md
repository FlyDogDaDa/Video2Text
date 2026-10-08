---
created: 2026-10-02
author: agent
type: agent
tags: [stt-api, fastapi, meeting-transcribe, deployment, debugging]
---

# STT API 服務化：討論與推進全記錄（00 細節檔）

## 任務目標（human 原始需求）

- 老闆要求 10/10 前把上傳檔案版轉錄功能包成 API（FastAPI 即可），上傳檔案可留記憶體、不必長存一次性檔案。
- 用法寫成 Agent 技能包，整包可裝進老闆的 agent 擴充「會議記錄轉錄」功能。
- GB10 的 IP 是 10.46.219.5；服務要跑在另一個 GNU screen 叫 `STT`。
- 目標：API endpoint 接收會議錄音檔（不限長度）→ 回傳轉錄稿 JSON（含語者）。
- human 提供背景：老闆後續可能做企業知識庫、Agent 自動化整理、會議歸檔（此背景不寫進對外檔案）。

## 探勘階段的發現

### 環境盤點

- 本機 hostname `spark-cfcd`，網絡卡上確實有 `10.46.219.5/24`（ZeroTier 介面 ztktiy5upo），即 GB10 本體。
- `exp/` 實際存在三個實驗資料夾（N9boWvU-KkA / Ek7qDwwXZ6A / Meeting20260825）。
  **陷阱**：`list_directory` 工具曾回報 `exp/` 為空（誤報），以終端 `ls` 為準。
- 活體管線指令碼在 `exp/Meeting20260825/scripts/`（最新，含 tau_sweep 與 v31）；
  `exp/Ek7qDwwXZ6A/scripts/` 為較舊版本（無 tau_sweep）。
- 既有 screen：`gemma`（attached）、`asr`（detached）。GPU：NVIDIA GB10（nvidia-smi 顯示記憶體 N/A，
  統一記憶體架構；實際用量要用 --query-compute-apps 看）。

### 關鍵發現 1：ASR 伺服器實際 port 是 8754、模型是 Breeze

- `transcribe_iterative.py` 預設 `EK7_ASR_URL=http://10.46.219.5:8750/...`，但實際監聽 8750 的是……沒有。
- `ss -tln` 只見 8754；screen `asr` 的 hardcopy 顯示 vLLM APIServer pid 113633，
  serve 的是 `MediaTek-Research/Breeze-ASR-26`（max_model_len=448），來自
  `/home/freespace/inference-recipes/engines/vllm/launchs/launch_script_2026_09_26_breeze-asr-26.sh`
  （gpu_memory_utilization=0.10），log 顯示 22:04~22:05 有來自 10.46.219.68 的請求。
- **決策：不動 `asr` screen**（他機在使用中），另開 screen `moss-td` 跑 MOSS-Transcribe-Diarize @8750。
- GPU 記憶體：Breeze worker 佔 ~11.2GB，機器 119.7GB 可見記憶體，餘裕充足；
  MOSS TD 以預設 GPU_MEM_UTIL=0.12（≈14GB）成功啟動，兩者共存無衝突。

### 關鍵發現 2：管線三指令碼的契約

讀完 `transcribe_iterative.py`（341 行）、`tau_sweep.py`（284 行）、`speaker_unify_v31.py`（614 行）：

- `transcribe_iterative.py`：`BASE = Path(__file__).resolve().parent.parent` → 把指令碼放在
  `<job>/scripts/` 即可讓 BASE=`<job>`；吃 `<job>/audio_full.wav`（強制 16k/s16le/mono，wave 模組 assert）；
  產出 `audio_parts.json`、`transcript_part_N.json`、`transcript_combined.json`。
  ASR URL 可用環境變數 `EK7_ASR_URL` 覆蓋；video_id/source 寫死 "Ek7qDwwXZ6A"（服務副本已改為
  `EK7_VIDEO_ID`/`EK7_SOURCE` 環境變數可覆蓋）。
- `tau_sweep.py`：吃 `transcript_combined.json` + `audio_full.wav`，`--model` 指定 CAM++ onnx；
  輸出 `tau_sweep_report.json`，`auto_tau`=最寫完全穩定平臺期中心（無平臺期 → null）。
- `speaker_unify_v31.py`：吃同上，`--tau` 覆蓋、`--model` 指定 onnx；寫回
  `transcript_combined.json`（加 `speaker_global`）+ `speaker_unify_report.json`。
  campplus 後端不需 torch（sherpa_onnx CPU 即可）；resemblyzer 後端需要 torch，服務不用它。

### 依賴坑：sherpa-onnx 的 manylinux wheel 不捆 libonnxruntime

- 服務 venv 裝 `sherpa-onnx==1.13.8`（manylinux_2_17_aarch64 wheel）後 import 報
  `ImportError: libonnxruntime.so: cannot open shared object file`。
- `readelf -d` 顯示 `_sherpa_onnx...so` NEEDED libonnxruntime.so，RPATH 含
  `$ORIGIN/../../sherpa_onnx.libs`，但該目錄只有 libasound——wheel 沒捆 onnxruntime。
- Ek7 venv 之所以能動，是因為多裝了 **`sherpa-onnx-core==1.13.8`**（把
  libonnxruntime.so / libsherpa-onnx-c-api.so 等放進 `sherpa_onnx/lib/`，正好在 RPATH 第一層）。
- 解法：服務 `uv add sherpa-onnx-core==1.13.8`，import 即正常。此依賴已寫進 `pyproject.toml`。

## 服務設計決策

- **位置**：`serve/stt-api/`（沿用 serve/<name> 慣例；vllm/voicetag/quark-audio/sam-audio 同層）。
- **Port 8760**（避開既有 8750/8754 與其他服務；盤點過監聽清單）。
- **單 worker queue**：GPU ASR 是瓶頸，上傳即回 202，任務排隊依序處理；不做並行。
- **一次性檔案策略**：每 job 獨立工作目錄 `serve/stt-api/jobs/<job_id>/`（上傳檔、audio_full.wav、
  分段 wav、各 json、log），完成後**整目錄刪除**，僅結果 JSON 留在記憶體（TTL 24h，
  sweeper thread 每十分鐘清）。符合 human「不必真的存一堆一次性檔案」的要求；
  純記憶體持有整支 2h+ WAV（~350MB/h）在多人使用時風險高，故採磁碟暫存＋立即清除。
- **管線指令碼逐 job 複製**：指令碼以自身位置推導工作目錄，複製到 `<job>/scripts/` 天然隔離、可續跑。
- **τ 決策鏈**：使用者指定 `tau` 引數 > tau_sweep 的 auto_tau > speaker_unify_v31 內建預設（0.55）。
  tau_sweep 失敗不擋任務，fallback 繼續。
- **簡轉繁**：預設 `traditional=true`（OpenCC s2twp，opencc-python-reimplemented 純 Python 套件）；
  `--raw`/`traditional=false` 保留模型原始簡體輸出。
- **進度回報**：status 端點直接讀工作目錄的 `audio_parts.json`（parts_done / processed_s /
  total_s / fraction），不額外開執行緒；目錄刪除後回報凍結的 progress_frozen。
- **warnings**：從 `audio_parts.json` 收集 `fallback-blind-cut`（盲切，句子可能腰斬）與
  `empty-advance`（無輸出段）數量，寫進結果 JSON，讓 Agent 端能自覺引用風險。
- **無語音防護**：ASR 結果 0 段時跳過 tau_sweep 與 unify（v31 對空輸入會炸），直接回
  n_speakers=0 的結果。
- **健康檢查**：`/health` 打 ASR 的 `/v1/models`（3s timeout）回報 ready/model。

## 服務面設定

- screen `moss-td`：`serve/vllm/launch_MOSS_TD.sh`（該檔無 +x 許可權，用 `bash ./launch_MOSS_TD.sh` 執行；
  PORT=8750、GPU_MEM_UTIL=0.12）。HF 模型快取已有，無需下載。
- screen `STT`：`serve/stt-api/.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8760`。
- `.gitignore` 新增 `serve/stt-api/jobs/`。
- 無鑑別機制：內網限定，檔案中已註明勿暴露公網。

## 技能包設計

- 位置 `.agents/skills/meeting-transcribe/`（SKILL.md + scripts/meeting_transcribe.py）。
- SKILL.md 含 frontmatter（name/description，仿專案內既有技能格式）、端點表、回傳 JSON 結構、
  重要須知（耗時比、排隊、不留檔、TTL、內網限定、錯誤處理）。
- 輔助指令碼僅用標準庫（urllib + 自寫 multipart 串流），`python3` 即可跑，不需 pip 安裝——
  考量是裝進老闆的 agent 時環境不可控。
- 技能包不含任何老闆後續計畫的動機描述，只有功能本身。

## 除錯記錄（值得留檔的四個）

### Bug 1：vLLM 音檔大小上限 25MB（第一次大檔失敗）

- 症狀：大檔 part 0（24min WAV ≈ 46MB）被 ASR 伺服器 HTTP 400
  `Maximum file size exceeded (audio_filesize_mb=43.9)`。
- 追蹤：vLLM 原始碼 `envs.VLLM_MAX_AUDIO_CLIP_FILESIZE_MB` 預設 25（另有解碼時長上限 600s）。
- 為何九月沒事：09-16/20 大檔實驗的 ASR 是 **sglang-omni**（無此限制），本次換回 vLLM 才踩到。
- 修法：moss-td 啟動時 `VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=64`、`VLLM_MAX_AUDIO_DECODE_DURATION_S=1800`
  （已寫進 launch_MOSS_TD.sh 的可覆蓋預設）。

### Bug 2：vLLM encoder cache 2048 < 18000 audio tokens（第二次大檔失敗）

- 症狀：修完大小上限後 part 0 又被拒：`audio item with 18000 embedding tokens exceeds
  the pre-allocated encoder cache size 2048`。
- 追蹤：`input_processor.py` 檢查 `num_embeds > mm_encoder_cache_size`；
  `encoder_cache_size = max(scheduler_config.encoder_cache_size, max_tokens_per_mm_item)`，
  而 scheduler 的 encoder_cache_size = max_num_batched_tokens（預設 2048）。
- 修法：`launch_MOSS_TD.sh` 加 `--max-num-batched-tokens 24576`，GPU 利用率 0.12→0.25。

### Bug 3：MOSS TD generation_config 的 max_new_tokens: 5120 截斷長音訊轉錄

- 症狀：大小與 cache 都放寬後，大檔能跑了但切點異常（part 0 切在 545s 而非 ~1436s、
  只有 199 段，九月同視窗是 504 段）。
- 追蹤：`199/504 ≈ 0.39` 與 `5120 / (504×~20tok) ≈ 0.5...` 之比對——vLLM STT serving 層的
  `get_max_tokens()` 會取 `default_sampling_params`（讀自模型 generation_config.json 的
  `max_new_tokens: 5120`）當生成上限 → 24min 視窗約需 11k tokens → 40% 處截斷。
  關鍵：內容**不會丟**（切點接續重轉），但 parts 翻倍、效率差、語者組數變多。
- 修法：launch 加 `--override-generation-config '{"max_new_tokens": 16384}'`。
  修復後 part 0：cut 1436.73s、513 段——與九月基準（1436.73s、502 段）一致。
- 此修復讓大檔最終跑完：2266 段／7 語者／auto_tau=0.275／無 warnings／1428.8s。

### Bug 4：multipart body 少了 closing delimiter 前的 CRLF（輔助指令碼）

- 症狀：curl -F 可以上傳（202），自寫 stdlib MultipartBody 永遠 422 "file Field required"。
- 隔離過程：
  1. 先修自寫 `read()`：檔案串流結束回傳空 bytes 會讓 http.client 視為 EOF 截斷 footer →
     改位元組佇列連續讀取。**仍然 422**。
  2. 懷疑 boundary 前導破折號問題 → 換純 hex boundary 重測。**仍然 422**。
  3. 本地 socket 抓包：headers 與開頭 bytes 完全正確。
  4. 決定性 bisect：同一 http.client transport，分別送 httpx 產生的 body 與我的 body
     → httpx body 202、我的 body 422 → **bytes 本身有問題**。
  5. 骨架比對（依 `\r\n--boundary` 切開）：httpx 3 段、我的只有 2 段 →
     **檔案內容結尾直接接 closing boundary，少了 RFC 2046 要求的 CRLF**，
     parser 把整個檔案吞進未終結的 part，file 欄位憑空消失。
- 修法：footer 改為 `\r\n--{boundary}--\r\n`。
- 教訓：「看起來對」的 bytes 要跟參考實作逐段比對；bisect 變因（transport 固定、body 互換）
  是最快路徑。

### 依賴坑：sherpa-onnx manylinux wheel 不捆 libonnxruntime

（詳見探勘階段的「依賴坑」段——服務 venv 以 `uv add sherpa-onnx-core==1.13.8` 解決。）

## 時鐘異常事件

- 工作期間系統時鐘先顯示 2026-10-01 23:22 CST，約 45 分鐘後 `date` 顯示 2026-10-02 08:27 CST
  （NTP 校正，timedatectl 確認 Asia/Taipei +8、synchronized）。先前 screen 建立時間戳
  （23:40）是時鐘錯誤時期記錄的。日誌資料夾因此定為 `2026_10_02`。

## 驗證記錄（最終）

| 測試 | 檔案 | 結果 |
|---|---|---|
| 21s 英文對話 | test-audio/gaokao-listening.wav（1.0MB） | 4 segments／2 語者／auto_tau=0.4／2~3s |
| 2min 中文會議 mp3 | test-audio/meeting_20260721.mp3（2.9MB） | 37 segments／4 語者／12.3s／繁體輸出正常 |
| 1h53m 大檔 | exp/Meeting20260825/audio_full.wav（218.2MB） | 2266 segments／7 語者／auto_tau=0.275／無 warnings／1428.8s |
| tau 覆蓋 | 同 21s + tau=0.9 | tau_used=0.9、跳過掃描 |
| raw 路徑 | 同 21s + --raw | traditional_applied=false |

- 大檔對照 09-20 基準（sglang-omni）：2108 段／6 語者／auto_tau=0.225；
  本次 7 語者落在「5~7 人未經人耳驗證」區間，屬引擎取樣差異。
- 失敗的兩次大檔 job（舊 server 引數）已 DELETE 清除；jobs 目錄確認無殘留。
