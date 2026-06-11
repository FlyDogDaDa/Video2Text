---
created: 2026-06-11
author: agent
type: agent
status: final
tags: [naming-cleanup, module-rename, factory-pattern]
---

# Naming Cleanup — slice→video, container→factory, load_bytes→create_bytes_io

## What

Corrected three misleading file/function names in `src/utils/` to better reflect their actual responsibilities.

Changes:
- `src/utils/slice.py` → `src/utils/video.py`
- `src/utils/container.py` → `src/utils/factory.py`
- `load_bytes()` → `create_bytes_io()`

## Why

Each name was semantically inaccurate:

| Old Name | Problem |
|----------|---------|
| `slice.py` | The file contains `IOCacheVideo` (PyAV container wrapper), `VideoInfo`, `SliceParams` — the core responsibility is **video I/O**, not slicing. Slicing logic now lives in `src/pipeline/slicer.py`. |
| `container.py` | The file contains a single function that reads a file and returns `BytesIO`. It has nothing to do with containers (video or otherwise). |
| `load_bytes()` | The function returns a `BytesIO` object, not `bytes`. The name suggests loading bytes from somewhere, which is misleading. |

Accurate names prevent future confusion and reduce the mental overhead of reading the codebase.

## How

### 1. `src/utils/slice.py` → `src/utils/video.py`

- Renamed file via `move_path`.
- Updated docstring usage example to import from `src.utils.video`.
- `src/utils/__init__.py`: updated import path.
- `src/pipeline/slicer.py`, `src/pipeline/extractor.py`: updated imports.

### 2. `src/utils/container.py` → `src/utils/factory.py`

- Renamed file via `move_path`.
- Updated module docstring to describe it as a "BytesIO factory".
- Updated usage example in docstring.
- `src/utils/__init__.py`: updated import path.
- `src/utils/video.py`: updated `from src.utils.factory import ...`.

### 3. `load_bytes()` → `create_bytes_io()`

- Renamed the function in `factory.py`.
- Updated internal call in `video.py` (`av.open(create_bytes_io(source))`).
- In `src/utils/__init__.py`, kept `load_bytes` as a **backwards-compatible alias**: `load_bytes = create_bytes_io`.
- Updated `__all__` to export both names.

### 4. Verification

```bash
uv run python -c "
from src.utils.video import IOCacheVideo, SliceParams
from src.utils.factory import create_bytes_io
from src.utils import create_bytes_io as cbi2, load_bytes
assert cbi2 is load_bytes  # alias check
print('✅ all imports OK')
"
```

## Follow-up

- After confirming everything works, remove the `load_bytes` alias from `__init__.py` in a future cleanup pass.
- Review the docstring example in `22_2026_06_10_agent_restructure-video-slicing-to-pyav.md` which references `load_bytes` and `container.py` — this is archival content so it's fine to leave as-is (it documents the state at that time).

## References

- [src/utils/video.py](../src/utils/video.py) (renamed from slice.py)
- [src/utils/factory.py](../src/utils/factory.py) (renamed from container.py)
- [src/utils/__init__.py](../src/utils/__init__.py)
- [src/pipeline/slicer.py](../src/pipeline/slicer.py)
- [src/pipeline/extractor.py](../src/pipeline/extractor.py)
- [22_2026_06_10_agent_restructure-video-slicing-to-pyav.md](./22_2026_06_10_agent_restructure-video-slicing-to-pyav.md) — archival reference
