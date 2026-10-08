# ek7-pipeline 腳本歸檔（2026-09-16）

Ek7qDwwXZ6A 新版超長音訊管線的腳本快照。**活體版本在 `exp/Ek7qDwwXZ6A/scripts/`
與 `serve/vllm/`**；執行過程若腳本有改，以活體為準並回頭更新此處。

| 檔案 | 用途 | 狀態（歸檔當下） |
|---|---|---|
| `download_streams.sh` | yt-dlp 分流下載（先 audio 251 後 video 399，fallback 鏈） | ✅ 已執行成功 |
| `install_embed_env.sh` | CPU torch + resemblyzer 安裝（webrtcvad 需編譯） | ✅ 已執行成功 |
| `launch_MOSS_TD.sh` | MOSS-Transcribe-Diarize vLLM 伺服器啟動（快照來自 `serve/vllm/`） | ⚠ 參數修正後仍 CUDA OOM（GPU 被 SGLang 佔用，非腳本問題） |
| `transcribe_iterative.py` | 逐字稿驅動迭代切分轉錄（句界切點、無腰斬、可續跑） | ✅ py_compile 通過；**未實跑（待 ASR）** |
| `speaker_unify.py` | centroid 相似度矩陣 + constrained union-find 全域語者統一 | ✅ py_compile 通過＋舊資料煙霧測試通過（2 全域語者、963 段全指派） |

## 相關紀錄

- 設計討論：`../references/01_human_long-audio-pipeline-design.md`
- 執行時間軸：`exp/Ek7qDwwXZ6A/execution-log.md`
- 煙霧測試報告：`exp/Ek7qDwwXZ6A/validate_on_n9bo/speaker_unify_report.json`
- 實驗 TODO：`exp/Ek7qDwwXZ6A/TODO.md`
