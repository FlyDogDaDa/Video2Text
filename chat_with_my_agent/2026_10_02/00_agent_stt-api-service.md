---
created: 2026-10-02
author: agent
type: agent
tags: [stt-api, fastapi, meeting-transcribe, deployment, vllm, debugging, skill-package]
---

# 會議轉錄功能服務化：STT API ＋ Agent 技能包

## What

- 把 09-16~09-20 驗證過的超長音訊管線包成 HTTP API 服務（FastAPI），部署在 GB10：
  - 新服務 `serve/stt-api/`（`app.py`＋`pyproject.toml`＋`README.md`），跑在 GNU screen `STT`，port 8760。
  - MOSS-Transcribe-Diarize vLLM 伺服器另開 screen `moss-td`（port 8750），與既有 Breeze 服務（8754，他機使用中）共存。
- API 行為：`POST /transcribe` 上傳音訊（multipart，長度不限）→ 回 `job_id`；
  `GET /jobs/{id}` 輪詢狀態與進度（含百分比）；`GET /jobs/{id}/result` 取回 JSON 逐字稿；
  另有 `/jobs`、`DELETE /jobs/{id}`、`/health`。檔案全收錄在 `/docs`（OpenAPI）。
- 一次性檔案不長存：每個任務用獨立工作目錄，完成後立即整目錄刪除；只有結果 JSON 留在
  記憶體（TTL 24 小時，sweeper 定期清）。
- Agent 技能包 `.agents/skills/meeting-transcribe/`：`SKILL.md`（端點表、回傳結構、注意事項）
  ＋ `scripts/meeting_transcribe.py`（純標準庫，一條命令完成上傳→輪詢→存檔），整包可攜。
- 三層驗證全數通過：21 秒英文對話（4 段／2 語者）、2 分鐘中文會議 mp3（37 段／4 語者／12.3s）、
  1h53m 大檔（218MB wav，結果見下）。
- 過程中發現並修正三個部署層問題（見 How／References）。

## Why

- 老闆要求 10/10 前把上傳檔案版轉錄功能包成 API：讓使用者或 Agent 把音訊傳進去、
  查狀態、拿轉錄稿 JSON，功能就能「甩給 Agent」自動打逐字稿。
- 選 FastAPI：專案生態已以 Python 為主，且 OpenAPI 檔案自動生成方便對接。
- 不動既有 `asr` screen（Breeze，另一臺機器正在用）：管線需要的是 MOSS TD 的
  `[start][Sxx]text[end]` 輸出（內建 diarization），另開 `moss-td` 共存。
- 上傳檔案「可留記憶體」的詮詮釋：採「磁碟暫存＋完成即刪」——純記憶體持有 2h+ WAV
  （約 115MB/小時）在多人併發時風險高，且管線指令碼本來就吃檔案路徑。

## How

### 服務端

- `serve/stt-api/app.py`：單 worker queue（GPU ASR 是瓶頸，任務依序處理）、
  job 狀態機（queued → processing[convert/transcribe/tau_sweep/speaker_unify/build_result] → done/error）、
  進度從工作目錄的 `audio_parts.json` 即時推算、warnings（盲切／無輸出段數）寫進結果、
  無語音防護（0 段時跳過後段）、τ 決策鏈（使用者指定 > auto_tau > v31 預設）。
- 管線指令碼逐 job 複製（`pipeline_scripts/` → `jobs/<id>/scripts/`）：指令碼以自身位置推導
  工作目錄，天然隔離且可續跑。副本中 `video_id`/`source` 改為環境變數可覆蓋。
- 依賴：fastapi、uvicorn、python-multipart、httpx、numpy、sherpa-onnx、**sherpa-onnx-core**、
  soundfile、opencc-python-reimplemented（Python 3.12，uv 管理）。

### 部署層問題與修正（除錯細節見 References）

1. **vLLM 音檔大小上限 25MB**（`VLLM_MAX_AUDIO_CLIP_FILESIZE_MB`，環境變數）：
   24 分鐘 16k WAV ≈ 46MB 被拒。09-16/20 的大檔實驗其實是打 sglang-omni（無此限），
   換回 vLLM 才踩到 → 啟動指令碼設 64MB（另同步放寬解碼時長上限 1800s）。
2. **vLLM encoder cache 2048 < 18000 audio tokens**：`encoder_cache_size = max_num_batched_tokens`
   → `launch_MOSS_TD.sh` 加 `--max-num-batched-tokens 24576`、GPU 利用率 0.12→0.25。
3. **sherpa-onnx manylinux wheel 不捆 libonnxruntime.so** → 補裝 `sherpa-onnx-core==1.13.8`。
4. **MOSS TD `generation_config.json` 帶 `max_new_tokens: 5120`**：vLLM STT serving 層拿它當
   生成上限，24 分鐘視窗約需 11k tokens → 在 ~40% 處截斷（199/504 段，與九月 sglang 基準比對吻合）。
   內容不會丟（切點會接著轉）但 parts 數量翻倍 → 啟動指令碼加
   `--override-generation-config '{"max_new_tokens": 16384}'`，修復後 part 0 切點 1436.73s、
   513 段，與九月基準一致。

### 技能包

- `SKILL.md` 走 Zed skill 慣例（frontmatter name/description），含 curl 三步用法與輔助指令碼用法；
  不含任何未來計畫的動機描述，只有功能本身。
- 輔助指令碼用 urllib ＋自寫 multipart 串流（大檔不吃滿記憶體）；除錯過程發現
  **closing delimiter 前少了 CRLF** 會讓 python-multipart 把整個檔案吞進未終結的 part
  （curl 正常、自寫 client 永遠 422 的根因），已修正。

## 成果數字

| 測試 | 檔案 | 結果 |
|---|---|---|
| 21s 英文對話 | gaokao-listening.wav（1.0MB） | 4 segments／2 語者／auto_tau=0.4／2~3s |
| 2min 中文會議 | meeting_20260721.mp3（2.9MB） | 37 segments／4 語者／12.3s／輸出已轉繁體 |
| **1h53m 大檔** | Meeting20260825 audio_full.wav（218MB） | **2266 segments／7 語者／auto_tau=0.275／無 warnings**／耗時 1428.8s（ASR 1290s＋掃描 69s＋統一 68s）≈ 音檔長度的 1/4.8 |
| tau 覆蓋路徑 | 同 21s 檔 + `tau=0.9` | tau_used=0.9、跳過掃描，正常完成 |
| raw 路徑 | 同 21s 檔 + `--raw` | traditional_applied=false，保留原始輸出 |

大檔對照 09-20 基準（同音檔、sglang-omni 後端）：2108 段／6 全域語者／auto_tau=0.225。
本次（vLLM 後端）語者數落在九月實驗「5~7 人未經人耳驗證」的區間內，屬引擎取樣差異而非退步。

## Follow-up

- 服務重啟後 jobs 清單消失（結果只在記憶體）——設計如此，但若要「重啟不丟結果」需另做持久化。
- 08-18 併發回應錯位問題在服務化後的併發場景需再觀察（目前單 worker 依序，風險低）。
- 老闆驗收時的展示流程建議：用 2 分鐘 mp3 現場跑一輪（約 12 秒完成）。
- 大檔結果的 7 語者分組未經人耳驗證（與九月 6 語者結果的差異需抽聽比對才有定論）。

## Uncertainty

- 耗時比已實測（1/4.8），但僅單一樣本；與 sglang-omni 時代的體感（~1/3.5）不同，
  實際速率受 GPU 當下負載影響。
- `n_speakers` 來自聲紋自動群聚，未經人耳驗證（與 09-20 實驗的結論一致，沿用其限制）。
- vLLM 0.26 在 GB10 上以 max_num_batched_tokens=24576 處理 24min 音訊的穩定性，
  僅本次大檔驗證一輪，長期併發行為未知。
- 系統時鐘曾在工作期間被 NTP 從 10-01 23:22 校正到 10-02 08:27（快了約 9 小時），
  screen 建立時間戳等紀錄有偏移，但不影響服務行為。

## References

- [討論與除錯全記錄](references/00_agent_stt-api-service.md)
- [服務原始碼](../../serve/stt-api/app.py)、[服務說明](../../serve/stt-api/README.md)
- [啟動指令碼（已加長音訊引數）](../../serve/vllm/launch_MOSS_TD.sh)
- [Agent 技能包](../../.agents/skills/meeting-transcribe/SKILL.md)
- [驗證產物歸檔](assets/stt-api-validation/README.md)
