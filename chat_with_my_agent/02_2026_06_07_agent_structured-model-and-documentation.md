---
created: 2026-06-07
author: Zed Agent
type: agent
status: final
tags: [pydantic-models, slice-result, terminology, documentation]
---

# Structured Data Model and Documentation

## What

- 建立 `src` 套件與 `src/models.py`
- 新增 `SliceResult` 及其子模型的 Pydantic schema
- 在系統設計檔案中新增 Terminology 章節，統一 Window = Slice 的命名
- 新增 `pydantic` 依賴至 `pyproject.toml`

## Why

設計檔案中的 JSON schema 需要對應到可執行、可驗證的程式碼。使用 Pydantic 的 `BaseModel` 可確保：
1. 格式驗證 — LLM 輸出的 JSON 結構可透過 Pydantic 解析與驗證
2. 型別安全 — `frozen=True` 確保不可變性，避免執行期意外修改
3. 自動 JSON schema 產生 — 可直接作為 vLLM 的 `response_format` 使用
4. 統一命名 — Window 與 Slice 的對照讓設計檔案與程式碼保持一致

## How

### 檔案修改

1. **`src/models.py`** — 新增 5 個 Pydantic model（全部 `frozen=True`）：
   - `TimeRange` — `start`, `end`（Decimal, ≥0），附帶 `duration` property
   - `Description` — `visual`, `audio`（str）
   - `TranscriptionEntry` — `text`, `speaker`（可選）
   - `Transcription` — `audio: list[TranscriptionEntry]`, `visual: str`（視覺描述）
   - `SliceResult` — 完整輸出，包含 `description`, `transcription`, `time_range`

2. **`pyproject.toml`** — 新增 `"pydantic>=2.0.0"` 依賴

3. **`01_2026_06_07_human_video2text-system-design.md`** — 新增 Terminology 章節，說明 Window（設計檔案用詞）= Slice（程式碼用詞）

### 設計決策

- **Decimal 而非 float**：時間戳記使用 Decimal 避免浮點精度問題（如 28.0 可能被誤存為 27.999999）
- **frozen=True**：所有 model 均不可變，確保 round 之間狀態不會被意外修改
- **可選的 speaker**：`TranscriptionEntry.speaker` 設為可選，因為某些情況下無法識別語者
- **預設空集合**：`Transcription.audio` 預設為空 list，而非要求每次都有轉錄結果
- **`Transcription` 的 `visual` 欄位**：視覺描述放在 transcription 中（預設為空字串），與 description.visual 不同，這裡記錄的是語意級別的視覺描述（如「一個人在廚房煮飯」），而非純影像事件的文字說明
- **`Description` vs `Transcription`**：
  - `Description` — 高層次的事件與音訊理解（LLM 分析輸出）
  - `Transcription` — 具體的文字化內容（對話轉錄 + 視覺畫面描述）

## Follow-up

- [ ] 執行 `uv sync` 安裝 pydantic
- [ ] 建立 `src/__init__.py` 公開 `SliceResult`
- [ ] 撰寫 unit test 驗證模型序列化/反序列化
- [ ] 建立影片切片工具（視窗切割、FPS 抽幀）

## References

- [01_2026_06_07_human_video2text-system-design.md](./01_2026_06_07_human_video2text-system-design.md)
- [src/models.py](../src/models.py)
- [pyproject.toml](../pyproject.toml)
