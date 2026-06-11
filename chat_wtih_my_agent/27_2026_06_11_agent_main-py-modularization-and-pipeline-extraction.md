---
created: 2026-06-11
author: agent
type: agent
status: final
tags: [main.py-refactor, modularization, pipeline, types-rename, structured-output, delayed-guided-decoding]
---

# Main.py Modularization — Pipeline Extraction

## What

Refactored `main.py` (430 → 79 lines) into a clean pipeline package under `src/pipeline/`.

Changes:
- `src/models.py` → `src/types.py` (rename for accuracy)
- Created `src/pipeline/` with `loader.py`, `slicer.py`, `extractor.py`
- `main.py` slimmed to a test entry point only
- Removed deprecated functions: `extract_frames()`, `swarm_extract()`, `test_multimodal()`, `_build_slice_prompt()`, old `extract_structured()`

## Why

`main.py` had been growing into a monolith mixing test harness code with production pipeline logic. The following problems were identified:

1. **Test/production mixing** — 4 test functions and `main()` coexisted with 3 production functions
2. **Duplicate slicing logic** — `swarm_extract()` and `extract_structured()` each reimplemented the same window+step loop
3. **Outdated prompt format** — `_build_slice_prompt()` used an old template format inconsistent with `SliceResult` schema
4. **No guided decoding** — the old `extract_structured()` was prompt engineering only, no `StructuredOutputsParams`
5. **Deprecated I/O** — `extract_frames()` relied on OpenCV despite the project migrating to PyAV
6. **No reasoning support** — missing `reasoning_parser="gemma4"` + `parse_thinking_output()` integration

## How

### 1. `src/models.py` → `src/types.py`

Renamed the file. Updated imports in:
- `src/__init__.py`: `from src.types import SliceResult`
- `test_vllm_delayed_guided_decoding.py`: already used `src.types` (no change needed)

### 2. `src/pipeline/loader.py` — `load_model()`

Moved the vLLM model loading function. Signature preserved with keyword-only extras:

```python
load_model(model_path, *, max_model_len=16384, limit_mm_per_prompt=None) → LLM
```

All existing parameters kept: `quantization`, `tensor_parallel_size`, `hf_overrides`, `mm_processor_kwargs`, etc.

### 3. `src/pipeline/slicer.py` — `slice_video()` + `SliceInput`

Consolidated the duplicate window+step loops from `swarm_extract()` into a single generator:

- Accepts **`IOCacheVideo`** instance (caller owns lifecycle via `with` block) — not `video_path`
- Yields `SliceInput` dataclasses: `{time_range, frames, audio_clips, info}`
- `SliceParams` re-exported from `src.utils.slice.SliceParams` (no duplicate definition)
- `slice_video(video, params)` replaces both `swarm_extract()` and the internal loop of old `extract_structured()`

### 4. `src/pipeline/extractor.py` — `extract_structured()`

Complete rewrite with real guided decoding:

- **`StructuredOutputsParams(json=schema)`** — vLLM enforces JSON schema at decode time (delayed guided decoding)
- **`enable_thinking=True`** in chat template — enables Gemma-4 reasoning
- **`parse_thinking_output()`** — separates reasoning from final JSON
- **`SliceResult.model_validate_json()`** — Pydantic validates the output
- Accepts **`IOCacheVideo`** instance (consistent with `slice_video()`)
- Caller opens video context, passes the object to `extract_structured()`

Contrast with old version:

| | Old (`main.py`) | New (`src/pipeline/extractor.py`) |
|---|---|---|
| Structured output | ❌ Prompt-only | ✅ `StructuredOutputsParams` |
| JSON parsing | Manual string split | `parse_thinking_output()` + Pydantic |
| Reasoning | ❌ None | ✅ `enable_thinking=True` |
| Video arg | `video_path: str` | `video: IOCacheVideo` |
| Prompt format | Old `{description: {}, transcription: {}}` | System prompt + SliceResult schema fields |

### 5. `main.py` — Slimmed to test harness

Before: 430 lines, mixed concerns.
After: 79 lines, only test flow:

```
main()
├── test_gpu()
├── load_model()     ← imported from src.pipeline
└── test_text_generation()
```

Removed: `extract_frames()`, `swarm_extract()`, `test_multimodal()`, `_build_slice_prompt()`, old `extract_structured()`, unused imports (`cv2`, `sys`, `Image`, `AutoProcessor`, `LLM` at module level).

### 6. Module structure

```
Video2Text/
├── main.py                  # 79 lines — test entry point
├── src/
│   ├── __init__.py          # from src.types import SliceResult
│   ├── types.py             # SliceResult (renamed from models.py)
│   └── pipeline/
│       ├── __init__.py      # Exports: load_model, slice_video, SliceInput, extract_structured
│       ├── loader.py        # load_model()
│       ├── slicer.py        # slice_video(), SliceInput
│       └── extractor.py     # extract_structured() (guided decoding + reasoning)
└── src/utils/               # IOCacheVideo, SliceParams (unchanged)
```

### 7. Import verification

```bash
uv run python -c "
from src.pipeline.loader import load_model
from src.pipeline.slicer import slice_video, SliceInput
from src.pipeline.extractor import extract_structured
from src.types import SliceResult
print('✅ all imports OK')
"
```

## Follow-up

- **Validation needed** — imports pass but full runtime behavior has not been tested:
  - `load_model()` with actual GPUs
  - `slice_video()` with real video files
  - `extract_structured()` end-to-end with guided decoding + reasoning
- Consider updating `src/__init__.py` to re-export pipeline functions if needed
- `swarm_extract()` callers (if any external) need migration to `slice_video()`
- The old `extract_structured()` pattern (prompt-only, no guided decoding) is completely gone — no remaining code uses it

## References

- [src/types.py](../src/types.py) (renamed from models.py)
- [src/pipeline/__init__.py](../src/pipeline/__init__.py)
- [src/pipeline/loader.py](../src/pipeline/loader.py)
- [src/pipeline/slicer.py](../src/pipeline/slicer.py)
- [src/pipeline/extractor.py](../src/pipeline/extractor.py)
- [main.py](../main.py)
- [src/utils/slice.py](../src/utils/slice.py)
- [25_2026_06_11_agent_vllm-delayed-guided-decoding-offline.md](./25_2026_06_11_agent_vllm-delayed-guided-decoding-offline.md)
