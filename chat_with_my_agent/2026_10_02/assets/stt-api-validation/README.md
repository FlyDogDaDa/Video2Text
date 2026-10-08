# STT API 驗證產物歸檔（2026-10-02）

API 服務（`serve/stt-api/`）三層驗證與路徑補測的原始輸出。

| 檔案 | 內容 |
|---|---|
| `stt_api_test_21s.json` | 21s 英文對話（gaokao-listening.wav）：4 段／2 語者／auto_tau=0.4 |
| `stt_api_test_2min.json` | 2min 中文會議（meeting_20260721.mp3）：37 段／4 語者／12.3s |
| `stt_api_big_meeting.json` | **1h53m 大檔**（Meeting20260825 audio_full.wav，218MB）：2266 段／7 語者／auto_tau=0.275／無 warnings／耗時 1428.8s |
| `stt_api_tau_override.json` | `tau=0.9` 覆蓋路徑：tau_used=0.9、跳過掃描 |
| `stt_api_raw.json` | `traditional=false` 路徑：保留模型原始（簡體/原文）輸出 |
| `stt_api_big_run3.log` | 大檔輔助指令碼的輪詢過程 log（進度回報樣本） |

大檔對照 09-20 基準（同音檔、sglang-omni 後端）：2108 段／6 全域語者／auto_tau=0.225。
本次（vLLM 後端）2266 段／7 語者／auto_tau=0.275——引擎不同導致的取樣差異，
語者數落在九月實驗「5~7 人未經人耳驗證」的區間內。
