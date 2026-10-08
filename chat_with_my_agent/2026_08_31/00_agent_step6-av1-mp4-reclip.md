---
created: 2026-08-31
author: agent
type: agent
tags: [step6, edit-video, av1-nvenc, mp4, parallel, video2text]
---

# 步驟 6 追加：AV1（av1_nvenc）＋ MP4 重產 423 片到 clips_mp4/

## What

- 使用者授權執行 log 05 留的可選項：以 **MP4 + `av1_nvenc` + AAC** 重產全部
  423 片，輸出到獨立資料夾 **`clips_mp4/`**，不觸動既有 `clips/`（H.264 MKV）。
- GPU 復探：GB10 util 0%（vLLM/sglang 閒置）→ `av1_nvenc` 0.5s 試編**通過**
  （av1+aac，0.521s，`tmp/test_av1.mp4`）。
- 改裝 `exp/N9boWvU-KkA/scripts/edit_video.py`：新增 `--encoder {x264,av1_nvenc}`
  與 `--outdir`；`ENCODERS` 對照表帶 vcodec/vargs/副檔名；預設行為完全不變。
- 新產出：`clips_mp4/clip_0001.mp4 … clip_0423.mp4` ＋ `clips_mp4_manifest.json`。

## Why

- log 05 當時 NVENC 因視訊記憶體被佔滿而 fallback；如今 GPU 空閒，AV1 硬體編碼可用，
  檔案更小、編碼更快（使用者指定容器為 MP4）。
- 保留 `clips/` H.264 版：剪輯軟體相容性最大；兩版並存供選用。
- 改裝原指令碼而非新指令碼：切片政策（視窗解析/合併/去重/最小時長）完全複用，
  只引數化編碼與輸出路徑，避免兩份邏輯漂移。

## How

- `--encoder av1_nvenc --outdir clips_mp4`；編碼引數
  `-c:v av1_nvenc -preset p5 -rc vbr -cq 24 -b:v 0`（CQ 恆品質，≈x264 crf18
  視覺近似）＋ `aac 192k`；`-ss` 置 input 前保幀精確。
- 併發原規畫維持 `ProcessPoolExecutor(18)`，**實測後偏離為序列 `--workers 1`**
  （見 Execution Results）；每 process `-threads 2`。
- 流程：`--limit` 目檢 → 全量 → `--verify`（ffprobe 逐片，容差 0.15s）。

## Execution Results

- 指令碼改裝完成：`--encoder {x264,av1_nvenc}`、`--outdir`、`--workers`、`--retries`；
  dry-run 雙模式驗證通過（423 clips 統計一致），x264 預設路徑不回歸。
- 單程式 0.5s 試編 av1_nvenc 通過（`tmp/test_av1.mp4`）。但 `--limit 2` 並行
  （--workers 2 試點）：clip_0001 成功、clip_0002 失敗，錯誤
  `cuCtxCreate CUDA_ERROR_OUT_OF_MEMORY`，殘留 0 bytes 檔。
- **根因**：GB10 統一記憶體被 `sglang serve --mem-fraction-static 0.97`
  （port 8744，即本 agent 推論後端，不可停）佔 ~114 GiB，系統 free 僅 ~1 GiB；
  多 NVENC context 同時建立必然 OOM。單 context 序列則沒問題。
- **定案**：序列 `--workers 1 --retries 3`（每次失敗 backoff sleep 2×attempt）；
  產物不變，僅耗時拉長（估 ~10 分鐘）。

## Follow-up

- [x] `--limit` 試切：單程式通過；並行失敗 → 定案序列
- [ ] 序列全量切 423 片（`--workers 1 --retries 3`）＋ ffprobe 抽驗
- [ ] `--verify` 全量驗證 423/423
- [ ] 歸檔改裝後指令碼與 manifest 至本資料夾 `scripts/`、`assets/`
- [ ] 既有遺漏補檔：`inspect_words.py`、`download_yt.sh` 從未歸檔（見下）

## Uncertainty

- 【後續】本 log 的 NVENC 路線連序列也失敗（視訊記憶體比初次試編時更緊），已由
  [log 02](02_agent_step6-av1-mkv-full-reclip.md) 以 CPU libsvtav1 ＋ MKV 容器定案。

- AV1 MP4 在剪輯軟體的支援度不如 H.264；若使用者工作流依賴特定軟體，以
  `clips/` 為主力。
- ~~18 並行~~ 已實證並行不可行（sglang 佔 97% 統一記憶體）；序列吞吐量待全量
  實測後回填實際耗時。
- `clips_mp4/clip_0002.mp4` 目前為 0 bytes、`clips_mp4_manifest.json` 僅含部分
  entry：重跑全量會被正常覆蓋，勿手動補救。

## References

- [討論與決策細節（GPU 復探、試編證據、編碼引數、指令碼改裝設計）](references/00_agent_step6-av1-mp4-reclip.md)
- [步驟 6 H.264 版執行紀錄（log 05）](../2026_08_27/05_agent_step6-execution.md)
- [指令碼源檔](../../exp/N9boWvU-KkA/scripts/edit_video.py)（exp/ 下，不入 git）
