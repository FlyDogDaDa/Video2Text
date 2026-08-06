---
created: 2026-07-31
author: agent
type: agent
status: final
tags: [workflow, speech-to-text, device-auto, voicetag, integration]
---

# speech-to-text 工作流程完成 — auto device 偵測與端對端測試

## What

- 完成 `workflows/speech-to-text.py` 工作流程，整合 voicetag 與 Breeze-ASR-26
- 加入 `device: auto` 選項，自動偵測 GPU 並選擇 `cuda:0` 或 `cpu`
- 使用 `test-audio/保修工程會議.wav`（40 分鐘）完成端對端測試，成功輸出 JSON

## Why

- 使用者需要一套可重複使用的 Speech-to-Text 工作流程：指定 speaker 參考資料夾、輸入音訊、輸出 JSON
- 不同環境可能沒有 GPU，`auto` 選項確保在任何機器上都能正常運作
- 這是階段性成果，OVERLAP TSE 尚未實作，先記錄目前進度

## How

### 修改檔案

- **`workflows/config.yaml`**：
  - `speech_to_text.voicetag.device` 預設值改為 `"auto"`
  - 註解更新為 `"auto" / "cpu" / "cuda:0" / "cuda:1" / "mps"`
- **`workflows/speech-to-text.py`**：
  - `main()` 的 `--device` 參數新增 `"auto"` 選項
  - `run_pipeline()` 加入 `resolve_device(device)` 呼叫，在 config 合併後解析 `auto`
  - 修復 `workflows/voicetag.py` 與 voicetag package 同名的 circular import：手動載入 `site-packages/voicetag` 到 `sys.modules`
  - 修正 `profile.embeddings.shape[0]` → `profile.num_samples`（SpeakerProfile 無 `embeddings` 屬性）

### 測試結果

| 項目 | 結果 |
|------|------|
| **device 偵測** | `auto` → `cuda:0` 正確 |
| **speaker 註冊** | 4 位（婕、文、陳、黃），各 1 個樣本 |
| **segments** | 813 個，含 OVERLAP 偵測 |
| **audio 長度** | 2404.9 秒（約 40 分鐘） |
| **處理時間** | 250.4 秒（約 4 分鐘） |
| **輸出** | `output/保修工程會議_stt.json` |

### 使用方式

```bash
# 使用 config.yaml 預設值
uv run --directory serve/voicetag python ../workflows/speech-to-text.py

# 覆蓋參數
uv run --directory serve/voicetag python ../workflows/speech-to-text.py \
    --input "test-audio/保修工程會議.wav" \
    --output "output/會議結果.json" \
    --speaker-dir "test-audio/speaker-ref"

# 指定 device
uv run --directory serve/voicetag python ../workflows/speech-to-text.py \
    --device cpu
```

### Python API

```python
from workflows.speech_to_text import run_pipeline

result = run_pipeline(
    input_audio="test-audio/會議.wav",
    speaker_ref_dir="test-audio/speaker-ref",
    output_json="output/會議結果.json",
    device="auto",  # 或 "cpu" / "cuda:0"
)
```

## Follow-up

- [ ] OVERLAP 片段的 TSE（Target Speaker Extraction）尚未實作
- [ ] 測試更多不同長度的音訊檔
- [ ] 評估 `cuda:0` 下 resemblyzer embedding 是否會卡住（CPU 測試時有 GPU memory 問題）

## References

- [workflows/speech-to-text.py](../../workflows/speech-to-text.py)
- [workflows/config.yaml](../../workflows/config.yaml)
- [workflows/voicetag.py](../../workflows/voicetag.py)
- [serve/voicetag/voicetag_core.py](../../serve/voicetag/voicetag_core.py)
- [66_2026_07_31_agent_voicetag-transcribe-json-output](./66_2026_07_31_agent_voicetag-transcribe-json-output.md)