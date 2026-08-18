---
date: 2026-08-18
topics: [moss-transcribe-diarize, vllm, stt-server-module, live-verification]
status: final
author: agent
---

# MOSS-Transcribe-Diarize vLLM 部署 live 驗證

## 時間

2026-08-18（日誌 76 之後）

## 做了什麼

- 使用者將推理引擎由 sgl-omni 換成 vLLM（同模型、同埠 8750）；前段 500／崩潰根因為未裝 `vllm[audio]`（soundfile import 失敗），裝妥重啟後全通
- 重新探測 API 面（OpenAPI 存於 `scratch/openapi_vllm.json`），并完成全數 live 驗證：短音訊、2 分鐘會議 wav/mp3、json 格式、SSE 串流、word 時間戳、hotwords、prompt、並發行為
- 依 model card 官方方法補測熱詞（`prompt` = default prompt＋熱詞提示）與 script 指令
- 完成 diarization 品質對照（4 人 ground truth）
- 使用者拍板：text 與 json 內容相同時**用 json**（多 usage、較好取用）；此模型非繁體模型，簡→繁後續再處理

## 關鍵發現

### 可用格式與結構

- 此模型在此 build 只接受 `text`／`json`／`verbose_json`（enum 另有 srt/vtt，實際請求 srt/vtt 回 400「Currently only support response_format: text, json or verbose_json」）
- `verbose_json` 被模型層 gate（400「Currently do not support verbose_json for ...」）×3 次確認
- **結構化資訊全部嵌在 text 裡**：`[start][Sxx]內容[end]` segment 標記（例：`[0.81][S01]来[1.24]`）；json 格式回 `{text, usage}`
- `timestamp_granularities[]=word` 被忽略（輸出與 baseline 完全相同，無 word 級時間戳）
- `text` 格式未單獨測，預期等同 json 內的 text 欄位
- openai SDK 非串流可用：`model_dump()` 回 `text`／`usage` 完整；SDK 無 transcriptions 串流 API，串流需 httpx

### Diarization 品質（2 分鐘會議，對照 ground truth）

- **4 個 speaker 全數分出**：S01／S02 為兩位主講；S03 兩個短段（「杰星，对」「他听不懂台语」）、S04 一個短段（「重要的」）＝ 兩位附和者，與 ground truth 吻合
- 時間戳合理：start/end 近單調遞增，交談處有 ≤0.1s 輕微重疊（正常）
- 輸出文字為**簡體中文**（音訊本身是口語，模型未依提示轉繁體）

### 延遲（warm）

- 2 分鐘音訊 ≈ 7.5–10s（RTF ≈ 0.07–0.08）；5 秒短音訊 ≈ 0.2s
- 串流 TTFT ≈ 0.07s

### 串流（vLLM build）

- `stream=true` 可行：SSE（content-type: text/event-stream），OpenAI 風格 `transcription.chunk`＋`choices[0].delta.content` 逐字增量 → 末筆 `finish_reason: stop` → `data: [DONE]`
- 串流輸入仍不支援（部署無 `/v1/realtime`；與 sgl-omni 版同，offline 定位不受影響）

### 並發（重要，疑似 bug）

- 兩支不同 `response_format` 的請求並發時觀察到**回應錯位**：mp3+json 客戶端收到 srt 特有的 400 錯誤；srt 客戶端反而收到 200，且 body 位元組數（2604B）與 mp3 單獨結果完全一致
- 同格式並發 ×2 全 200（同內容無法區分是否錯位）；一側被 validation 拒回、另一側正在推理時最可能錯位
- 對策：**生產管線串行化（一次一支請求）**；此現象宜報修伺服器端（附重現：不同 response_format 的兩支請求同刻發出）

### 熱詞（hotwords）

- `hotwords` form 欄位**勿用**：附上後所有 [start][end] 時間戳消失（只剩 speaker 前綴＋空格）、專名誤寫「杰欣」（baseline 為「杰星」）、speaker 數 4→3、品質整體變差；此欄位是 Whisper 系模型的機制，與此模型的時間戳輸出互斥
- **官方方法（已驗證可行）**：`prompt` 欄位附上「default prompt＋熱詞提示」：`...并在段末标注结束时间戳，以清晰标明该段语音范围。热词提示：潔心`（default prompt 全文見 References）→ 人名「洁心」全數修正正確（baseline 為「杰星」）、時間戳完整保留；model card 與 examples/prompts.md 皆同此寫法
- `prompt` 取代 vs 附加 server 端 default 的語義未測完（hint-only 測試中斷）；實務上照官方 recipe 附完整 default＋hint 即可，兩種語義下都正確

### script 指令無效（非繁體模型）

- 繁體中文指令未被跟隨：`prompt` 附加「請以繁體中文輸出」（繁體寫法）與「输出的所有文字请使用繁体中文」（簡體寫法）皆無效，輸出維持簡體——此模型非繁體模型，屬預期行為（使用者確認：後續管線再處理）
- 熱詞提示則被跟隨（見上），顯示 `prompt` 欄位確實生效；模型只是不跟隨 script 層指令，格式維持 built-in default 的時間戳輸出

### 檔案格式

- 16 kHz mono wav、48 kHz mono wav、48 kHz stereo mp3 皆接受（vllm[audio] 負責載入與重採樣）
- 裝 vllm[audio] 前所有音訊皆 400「Invalid or unsupported audio file」（含正常 wav），根因即 soundfile 缺裝

## 對整合設計的意涵（asr.py 重寫輸入）

- **response_format 用 json**（使用者拍板：text 與 json 內容相同，json 多 usage 較好取用）
- 結構化解析：以 regex 從 text 抽 `[start][Sxx]text[end]` segments（不依賴 verbose_json）；可參照官方 `parse_transcript`（`moss_transcribe_diarize` package，GitHub repo）
- 客戶端：openai SDK 非串流 json；串流走 httpx（目前 offline 場景非必須）
- 串行佇列（併發錯位風險）
- 熱詞走官方方法：`prompt` = default prompt＋熱詞提示（`hotwords` form 欄位勿用）
- 管線需簡→繁轉換（使用者確認後續再處理，可併入 LLM 潤稿）
- 解析後的 segments（speaker＋時間戳＋文字）可直接餵語者音色分類與 LLM 潤稿，符合 offline 會議整理定位
- 背景：model card 明言「CUDA 12 環境 SGLang 不支援、應改用 vLLM」，即使用者由 sgl-omni 轉 vLLM 之原因；長音訊建議調高 max 輸出 token（model card 例：65536）

## Follow-up

- 重寫 `modules/asr.py` 整合計畫：MOSS-TD client ＋ text 解析器 ＋ 串行佇列（正式取代日誌 73）
- 可選：將並發錯位 bug 報給伺服器端（重現步驟：不同 response_format 兩支請求同時 POST）
- 延後：簡→繁轉換（使用者確認後續處理）；≥10 分鐘長音訊跨塊 speaker 一致性；單次 ~90 分鐘上限未驗證；`prompt` 取代 vs 附加語義（hint-only 測試中斷，官方 recipe 下不影響實務）
- 整合定案後正式 `uv add openai`

## References

- [75 MOSS-Transcribe-Diarize 研究](75_2026_08_18_agent_moss-transcribe-diarize-research.md)
- [76 整合方向拍板與重測狀態](76_2026_08_18_agent_moss-transcribe-diarize-decisions-and-retest-status.md)
- [MOSS-Transcribe-Diarize HF model card](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)（default prompt 全文）
- [官方 prompt recipes（examples/prompts.md）](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize/blob/main/examples/prompts.md)
- [GitHub repo（parse_transcript 等 utilities）](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize)
- [scratch/moss_test.py](../../scratch/moss_test.py)
- 測試輸出：`scratch/meeting_json.json`（baseline）、`scratch/meeting_mp3.json`、`scratch/dup_mp3.json`／`scratch/dup_wav.json`（並發）、`scratch/meeting_hotwords.json`（hotwords 欄位反例）、`scratch/meeting_prompt_zh_tw.json`、`scratch/meeting_prompt_default_plus.json`（官方熱詞方法）、`scratch/meeting_prompt_simplified_instr.json`、`scratch/openapi_vllm.json`
- `modules/asr.py`、`modules/vad.py`、`test-audio/`
