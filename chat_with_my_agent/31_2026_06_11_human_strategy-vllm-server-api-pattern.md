# 專案策略轉向：從離線推理到 Server API 模式評估

## What

系統性評估 vLLM 離線推理（`LLM.generate()`）與 Server API（OpenAI-compatible `/v1/chat/completions`）兩條路徑，確定專案最終架構方向。

**結論：Server API 模式為明確的贏家，專案將轉向此架構。**

## Why

### 當前離線模式的痛點

1. **模型載入開銷巨大**：每次 `main.py` 啟動需 4-5s 載入 + 16s init，頻繁重啟就頻繁重付
2. **離線多模態已確定有 bug**：
   - 文字推論輸出 `01111111...` 亂碼（無意義重複）
   - 音訊 `multi_modal_data["audio"]` 不接受 numpy array，格式不匹配
   - 文字推論 + 音訊同時使用時觸發 `Failed to apply prompt replacement for mm_items['audio'][0]`
3. **async 需求**：當前所有操作串列執行，需要大量重構
4. **guided decoding + reasoning**：需要手動 `parse_thinking_output()`，容易出錯

### Server 模式已在 nightly dev301 驗證通過

| 模態 | 狀態 | 來源 |
|------|------|------|
| 純文字 | ✅ | `16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md` |
| 圖片 | ✅ | 同上，dev301 已修復 `num_soft_tokens` bug |
| 影片 | ✅ | dev301 原生支援 `video_url` |
| 音訊 | ✅ | dev301 支援 `audio_url` |

## How

### 1. 架構複雜度對比

#### 離線推理（現況）— 厚重、容易出錯

```python
# main.py 當前流程
llm = load_model()  # 4-5s 載入 + 16s init
with IOCacheVideo(path) as video:
    for inp in slice_video(video, params):
        # 每一片都需要：
        prompt = processor.apply_chat_template(messages)  # 模板化
        multi_modal_data = {"image": [Image.fromarray(f) for f in inp.frames]}
        multi_modal_data["audio"] = [inp.audio_clips[0]]  # ❌ 格式錯誤
        outputs = llm.generate({"prompt": prompt, "multi_modal_data": multi_modal_data})
        parsed = parse_thinking_output(outputs[0].outputs[0].text)  # 手動分離 reasoning
        SliceResult.model_validate_json(parsed.text)  # 手動驗證
```

**問題：**
- 每一片都是 Python → vLLM C++ → GPU → Python 往返
- numpy array 格式與 vLLM 期望不一致
- `mm_processor_kwargs` 和 `hf_overrides` 對純文字推論有副作用
- 全部串列執行，無法並行

#### Server API 模式 — 輕量、穩定

```python
# client.py — 純粹的 HTTP client（使用 OpenAI SDK）
from openai import AsyncOpenAI

async def extract_structured(video_path: str, params: dict) -> list[dict]:
    """Split video → send each slice as API request → collect results."""
    slices = await _slice_video(video_path, params)  # 只切，不跑推理
    
    async with AsyncOpenAI(
        base_url="http://localhost:8746/v1",
        api_key="EMPTY",
    ) as client:
        tasks = [_request_slice(client, s) for s in slices]
        results = await asyncio.gather(*tasks)  # 並行傳送
    return results

async def _request_slice(client, slice_data):
    """Send one slice to vLLM OpenAI API."""
    response = await client.chat.completions.create(
        model="google/gemma-4-12B-it-qat-w4a16-ct",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": slice_desc},
                    *[{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}} for f in frames_b64],
                    *[{"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{b64}"}} for wav_b64 in audio_b64],
                ],
            },
        ],
        max_tokens=512,
        temperature=0.1,
    )
    return parse_structured_output(response.choices[0].message.content)
```

**優勢：**
- vLLM 內部自行處理：template、image encoding、audio encoding、guided decoding、reasoning parsing
- 不需要手動 `parse_thinking_output()` — server 啟動時 `--reasoning-parser gemma4` 自動處理
- 不需要 `StructuredOutputsParams` — vLLM 自動解析 schema
- 並行請求：多個 request 同時處理
- 模型載入一次，永久可用

### 2. Server 模式完整優勢對比

| 維度 | 離線推理 | Server API |
|------|---------|-----------|
| **模型載入開銷** | 每次啟動過載（+20s） | 一次載入，持續可用 |
| **async 並行** | 需要 asyncio/gather 大改 | 同時多個 request，內建 |
| **GPU VRAM 管理** | 多模型共存會 OOM | 單一例項，穩定 |
| **video_url 支援** | ❌ 需要 custom branch | ✅ dev301 原生支援 |
| **audio 格式** | ❌ numpy array 格式不匹配 | ✅ `data:audio/wav;base64,...` |
| **guided decoding** | ❌ 需要手動 StructuredOutputsParams | ✅ vLLM 自動處理 |
| **reasoning 分離** | ❌ 需要 parse_thinking_output() | ✅ `--reasoning-parser gemma4` |
| **重啟/熱更新** | 重寫 main.py + 重跑 | 重啟 server 即可 |
| **遠端部署** | ❌ 需要 SSH 到 GPU 機器 | ✅ API 呼叫即可 |
| **重試/容錯** | 需要手動實現 | HTTP client 內建 |
| **多語言支援** | ❌ 只能 Python | ✅ 任何語言呼叫 API |

### 3. Server 模式的劣勢與緩解

| 專案 | 說明 | 緩解策略 |
|------|------|----------|
| **需要維護 server 生命週期** | 需要確保 server 在跑 | 啟動 script + 健康檢查 `/health` |
| **網路延遲** | HTTP roundtrip 比 `llm.generate()` 多 ~50ms | 對影片分析而言可忽略（推論需數秒） |
| **media encoding** | 需要自己 base64 encode 圖片/音訊 | PyAV + base64 很輕量，不影響整體效能 |
| **max_num_seqs** | 同時請求受限（當前設 16） | 可調高或 queue 管理 |

### 4. 最終建議架構

```
┌─────────────────────────────────────────────┐
│                 main.py                      │
│  - 讀取影片                                 │
│  - slice_video() → list[SliceInput]         │
│  - 呼叫 async extract_structured()           │
│  - 收集結果                                 │
└──────────────┬──────────────────────────────┘
               │ HTTP POST
               ▼
┌─────────────────────────────────────────────┐
│       vllm serve (server, port 8746)         │
│  - 載入模型一次，永久可用                     │
│  - 處理：template + multimodal + reasoning   │
│  - guided decoding + structured output       │
└─────────────────────────────────────────────┘
```

**關鍵改變：**
- `main.py` 不再負責模型載入、template、推理
- `main.py` 只負責：切片 → HTTP 傳送 → 結果收集
- 所有多模態處理由 vLLM server 內部完成
- 需要維護一個長駐 server 程式

### 5. 具體實作步驟

1. **確認 server 在 dev301 上的 multimodal 狀態**
   - 測試 `video_url`、`image_url`、`audio_url` 格式
   - 驗證 `--reasoning-parser gemma4` 是否正常分離 reasoning

2. **重寫 client.py**
   - 使用 `AsyncOpenAI`（非 httpx）呼叫 `/v1/chat/completions`
   - 支援並行請求（asyncio.gather）
   - 內建重試機制

3. **重構 main.py**
   - 移除所有 `load_model()`、`llm.generate()` 邏輯
   - 改為呼叫 `extract_structured(client, video_path)`
   - 保持切片邏輯（IOCacheVideo + slice_video）

4. **測試端到端流程**
   - 對 `short_test.mp4` 跑一次完整 pipeline
   - 驗證 JSON schema 輸出正確性

## Follow-up

- [ ] 確認 server 上 multimodal 推論狀態（dev301）
- [ ] 實作 `client.py`（OpenAI SDK 版）
- [ ] 重寫 `main.py`（僅切片 + 呼叫 API）
- [ ] 端到端測試

## References

- [08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py](./08_2026_06_08_references_gemma4-vllm-inference-fixes/try_video.py)
- [12_2026_06_09_agent_vllm-multimodal-video-research.md](./12_2026_06_09_agent_vllm-multimodal-video-research.md)
- [14_2026_06_09_agent_vllm-multimodal-online-testing.md](./14_2026_06_09_agent_vllm-multimodal-online-testing.md)
- [16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md](./16_2026_06_09_human_vllm-nightly-installation-and-storage-optimization.md)
- [23_2026_06_11_references_swarm-structured-extraction/main.py](./23_2026_06_11_references_swarm-structured-extraction/main.py)

---

更新日期：2026-06-11
