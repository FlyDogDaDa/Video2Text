---
date: 2026-08-18
topics: [moss-transcribe-diarize, playground, opencc, gradio]
status: final
author: agent
---

# MOSS-Transcribe-Diarize 單頁 Playground

## 時間

2026-08-18（日誌 77 之後）

## 做了什麼

- 使用者拍板：workflows 打掉重來，改以單頁 playground 體驗「模型最純粹的狀態」；上傳音訊 → 處理按鈕 → 輸出（text）→ 清理按鈕 → 最終輸出（text 轉 OpenCC 繁體＋regex 成 JSON）
- 建立 `webuis/moss-playground.py`（Gradio 單頁）＋ `webuis/launch-moss-playground.sh`（啟動腳本，預設埠 7862，可 `MOSS_PLAYGROUND_PORT`／`MOSS_VLLM_URL` 覆蓋）
- `webuis/pyproject.toml` 新增 `httpx`、`opencc-python-reimplemented`（已 `uv lock`，opencc v0.1.7）
- 完成 E2E 實測：`process()` 直測（2 分鐘會議 wav、baseline 與熱詞「潔心」兩組）＋ Gradio 啟動 smoke test（首頁 200）

## 頁面設計

- 由上而下：「🧹 清空全部」（最上方，重置整頁）→ 上傳音訊 → （選填，收在 Accordion）熱詞 → 「🚀 處理」→ 輸出（原文・簡體）→ 最終輸出 → 狀態資訊（最末行）
- 最終輸出是「資料清洗」結果（使用者原意，非 UI 操作）：OpenCC s2t 繁體＋regex JSON；整區用 `gr.Group(visible=False)` 包起來，**只在有原文輸出時顯示**；失敗或清空時隱藏並清空內容
- 狀態資訊（延遲／segments 數／usage／錯誤）放在最末行，避免使用者未看內容就誤判為錯誤
- 熱詞走官方 recipe：有值時 `prompt` = model card default prompt（全文，簡體）＋「熱詞提示：…」；無值不送 prompt（server 端 default）
- 串行：所有請求經 `threading.Lock`（日誌 77 併發錯位 bug 的對策）
- JSON 形狀：`{"segments": [{"start", "end", "speaker", "text"}]}`，text 為繁體（最終產物定位）
- 三個核心函式 `transcribe`／`parse_segments`／`build_prompt` 與 UI 分離，可直接被 `modules/asr.py` 重用

## 關鍵發現

### OpenCC s2t vs s2tw（使用者選「不轉換常用詞」→ s2t）

- s2t＝逐字簡繁＋最小歧義消解：`干净→乾淨`、`头发→頭髮`（保留），但不做常用詞（地區詞語）層轉換：`里→裏`（非 `裡`）、`着` 維持 `着`
- s2tw 才轉常用詞為臺灣寫法：`里→裡`（`他在这里→他在這裡`）、`着→著`
- 結論：模型輸出「他在这里」經 s2t 會得「他在這裏」（`裏`），若日後想要「這裡」須換 s2tw 或 LLM 潤稿層處理；目前照使用者決斷用 s2t

### 熱詞 prompt 法影響 diarization 粒度（首測，重要）

- baseline（無 prompt）：4 speakers（S01–S04，與 ground truth 吻合）、37 segments、約 9.6s
- `prompt` = default＋「熱詞提示：潔心」：3 speakers（一位短附和者被併掉）、39 segments、約 9.8s
- 日誌 77 的 prompt 熱詞測試只記錄了人名修正與時間戳保留，未記錄 speaker 數；本次補上：**熱詞不僅改文字，也會改變 diarization 結果**（與 `hotwords` form 欄位的 4→3 方向相同）
- 實務含義：需要完整 diarization 顆粒度時，熱詞與否要先比對 speaker 數再決定

### Gradio 陷阱（兩條）

- Gradio 6.22 的 `gr.Textbox` 不支援 `show_copy_button`（已移除；舊參數會 TypeError）
- **`gr.Textbox` 空值回傳 `None` 而非 `""`**：熱詞欄留空時 `re.split(pattern, None)` 丟 `TypeError: expected string or bytes-like object, got 'NoneType'`；對策：`build_prompt` 入口 `if not hotwords: return None`＋handler 端 `hotwords or ""` 雙重保險（使用者實測踩到）

### 其他

- vLLM json 回應的 `usage` 格式為 `{"type": "duration", "seconds": 121}`（音訊時長，非 token 用量）
- `uv run --project webuis` 使用根 workspace 的 `.venv`（`webuis/.venv` 為歷史殘留，未被使用）
- 延遲與日誌 77 一致（2 分鐘音訊約 7.5–10s）

## 對後續的意義

- `modules/asr.py` 重寫（日誌 77 的下一步）尚未動；playground 的三個核心函式就是它的雛形，重寫時直接吸收
- `workflows/` 與 `webuis/speech-to-text.py` 已被本 playground 取代（未刪除，待使用者拍板去留）
- 長音訊（≥10 分鐘）：目前未送 `max_completion_tokens`（server 預設行為）；model card 建議 65536，仍屬待測

## Follow-up

- 瀏覽器點擊層驗證（本次只測了 `process()` 直測＋啟動 200；gradio 事件接線在 `make_ui()` 建成時已驗證，handler 執行路徑未走 UI 觸發）
- `modules/asr.py` 重寫整合提案（吸收 playground 核心函式）
- 拍板：`workflows/`、`webuis/speech-to-text.py`、`webuis/.venv` 去留
- 長音訊 `max_completion_tokens=65536` 實測

## References

- [webuis/moss-playground.py](../../webuis/moss-playground.py)
- [webuis/launch-moss-playground.sh](../../webuis/launch-moss-playground.sh)
- [官方 transcript_parser.py（state-machine parse_transcript，regex 方案的後續 fallback）](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize/blob/main/moss_transcribe_diarize/transcript_parser.py)
- [77 vLLM live 驗證](77_2026_08_18_agent_moss-transcribe-diarize-vllm-live-verification.md)
- `test-audio/meeting_20260721.wav`
