# fa-pooling-test — Qwen3-ForcedAligner vLLM 對齊測試腳本

測試 vLLM 部署的 `Qwen/Qwen3-ForcedAligner-0.6B`（pooling / token_classify 端點）
能否產出逐單位（逐字）時間戳。

## 檔案

- `test_fa.py`：對齊測試主腳本（2026-08-26 最終版，**已跑通並經使用者逐幀驗證**）
  - 音訊轉 16k mono wav → base64 data-uri
  - messages(text+audio_url)，text 內含 `<|audio_start|><|audio_pad|><|audio_end|>` 前綴
    與 `word<timestamp><timestamp>...` 序列
  - `/pooling` 請求帶自訂 `chat_template="{{ messages[0]['content'] }}"`
    （需伺服器以 `--trust-request-chat-template` 啟動；官方 online 範例做法）
  - `/tokenize`（同 messages + 同 chat_template）取實際 token 序列，定位
    `<timestamp>`；`argmax(5000 bins) × 80ms` 得時間戳
  - 含 sanity check（單調、不超出音訊長度）與 `usage.prompt_tokens` 長度交叉驗證
- `asr_crosscheck.py`：用 MOSS-Transcribe-Diarize ASR（`10.46.219.5:8750`
  `/v1/audio/transcriptions`）獨立轉錄同一音檔，作為 FA 對齊的交叉驗證。

## 怎麼跑

```sh
cd <專案根>   # 需要 output/ 下有測試音檔
# FA 對齊測試
exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/test_fa.py \
    --audio output/是我用AI跑出來的.opus --text "是我用AI跑出来的。"
# ASR 交叉驗證
exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/asr_crosscheck.py
```

## 依賴

- `httpx`（在 `exp/N9boWvU-KkA/.venv` 內）
- 系統 `ffmpeg` / `ffprobe`（音訊轉 16k mono wav）
- FA 伺服器：`http://10.46.219.5:8755`（model `Qwen/Qwen3-ForcedAligner-0.6B`，
  需 `--trust-request-chat-template`）
- ASR 伺服器：`http://10.46.219.5:8750`（model `OpenMOSS-Team/MOSS-Transcribe-Diarize`）

## 已知特性（2026-08-26 確認）

- 音訊頭尾留空（剪輯不貼合）時，靠近該端的 token 預測會被「均勻攤開」
  （首字釘在 0、末字被拉寬）。訓練即如此，非 bug。
  → 主流程切段送對齊時，前後 padding 應保持小（~100–200ms）。
- 簡體/繁體輸入對時間戳無影響（同段音訊兩者結果完全一致）。
