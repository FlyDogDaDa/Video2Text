# STT API（serve/stt-api）

長音訊會議轉錄 HTTP API：包裝 09-16~09-20 驗證過的超長音訊管線
（`transcribe_iterative.py` → `tau_sweep.py` → `speaker_unify_v31.py`）。

- 上傳會議音訊（不限長度）→ 輪詢 → 取回含全域語者標籤的 JSON 逐字稿。
- 使用端請看 Agent 技能包：`.agents/skills/meeting-transcribe/SKILL.md`。

## 架構

```
client ──POST /transcribe──▶ FastAPI (8760) ──▶ worker queue（單執行緒依序處理）
                                   │
                                   ├─ ffmpeg 轉 16k/s16le/mono → audio_full.wav
                                   ├─ 複製 pipeline_scripts/* 到 jobs/<id>/scripts/
                                   ├─ transcribe_iterative.py ──▶ MOSS TD vLLM (8750)
                                   ├─ tau_sweep.py（自適應 τ）
                                   └─ speaker_unify_v31.py（全域語者統一）
                                   │
結果 JSON 留在記憶體（TTL 24h）◀─ 工作目錄完成即刪除
```

## 啟動（GNU screen）

```bash
# 1) ASR 後端（MOSS-Transcribe-Diarize @8750；與 8754 的 Breeze 服務共存）
screen -dmS moss-td bash -c 'cd /home/freespace/檔案/Video2Text/serve/vllm && PORT=8750 bash ./launch_MOSS_TD.sh 2>&1 | tee -a moss_td.log; exec bash'

# 2) 本服務（@8760）
screen -dmS STT bash -c 'cd /home/freespace/檔案/Video2Text/serve/stt-api && .venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8760 2>&1 | tee -a server.log; exec bash'
```

健康檢查：`curl http://127.0.0.1:8760/health`（`asr.ready` 應為 true、model 應為
`OpenMOSS-Team/MOSS-Transcribe-Diarize`）。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `STT_ASR_URL` | `http://127.0.0.1:8750/v1/audio/transcriptions` | MOSS TD endpoint |
| `STT_PORT` | `8760` | 本服務 port |
| `STT_JOBS_DIR` | `./jobs` | 工作目錄根（完成即刪） |
| `STT_RESULT_TTL_H` | `24` | 結果 JSON 保留時數 |
| `STT_MODEL_ONNX` | `./models/speech_campplus_sv_zh_en_16k-common_advanced.onnx` | 聲紋模型 |

## 注意

- `sherpa-onnx` 必須搭配 **`sherpa-onnx-core`**（manylinux wheel 不捆 libonnxruntime.so）。
- `pipeline_scripts/` 是 `exp/Meeting20260825/scripts/` 的副本，其中
  `transcribe_iterative.py` 的 video_id/source 改為可由 `EK7_VIDEO_ID`/`EK7_SOURCE` 覆蓋。
- 內網限定、無鑑別，勿暴露公網。
