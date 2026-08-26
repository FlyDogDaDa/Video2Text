---
created: 2026-06-10
author: Agent
type: agent
status: draft
tags: [restructure, pyav, io-cache, video-slicing, architecture]
---

# Restructure video-slicing: PyAV as sole backend, IOCacheVideo, Container utility

## What

Complete rewrite of `src/utils/slice.py` — replaced the old multi-backend architecture (OpenCV + soundfile + PyAV for audio only) with a single PyAV-based core (`IOCacheVideo`) plus a pure-file `load_bytes()` utility.

## Why

The previous `slice.py` had three backends (OpenCV for frames, soundfile for audio, PyAV for audio extraction), each with lazy imports and separate extraction helpers. This made the code harder to maintain and inconsistent in how audio vs. video were accessed.

Key insights from the discussion:
- PyAV can open files **both by path and by `io.BytesIO`**, making in-memory caching trivial.
- PyAV's seek is precise enough for both video and audio — no need for OpenCV's seek-buffering trick.
- The architecture should be minimal: one core class (`IOCacheVideo`), one utility function (`load_bytes`), and the rest can be higher-level tools (like `Calculator`, pending).
- `InputContainer` doesn't have a `time_base` attribute — frame timestamps come from `frame.pts * frame.time_base` directly.
- AAC audio frames can be extremely small (2 samples per frame), which is fine — the extraction logic handles it correctly.

## How

### File changes

| File | Action | Description |
|------|--------|-------------|
| `src/utils/container.py` | **Created** | Pure function `load_bytes(path: Path | str) → BytesIO` — uses ``pathlib`` throughout |
| `src/utils/audio.py` | **Created** | `normalize_audio(data) → data` — extracted from ``slice.py`` |
| `src/utils/slice.py` | **Rewritten** | 691 lines → ~393 lines. Old classes replaced by ``IOCacheVideo`` only (``create_slices`` removed). Removed ``SliceSource``, ``SliceResult``, ``_normalize_audio``. ``IOCacheVideo`` accepts ``Path | str | BytesIO``, ``av.open()`` no longer forces ``format``. |
| `src/utils/__init__.py` | **Updated** | New exports: ``IOCacheVideo``, ``load_bytes``, ``normalize_audio``. Removed: ``create_slices``, ``SliceSource``, ``SliceResult``, ``VideoReader``, etc. |

### Architecture

```
src/utils/
├── container.py          ← load_bytes(path) → BytesIO
└── slice.py              ← IOCacheVideo (core), create_slices() (convenience)
```

**`IOCacheVideo`** — single class that:
1. Accepts ``str``, ``Path``, or ``io.BytesIO`` as source
2. Opens with ``av.open()`` (no forced ``format`` — auto-detects container type)
3. Provides ``get_frames(start, end)`` → ``[N, H, W, 3]`` RGB
4. Provides ``get_audio(start, end)`` → list of 16kHz mono clips
5. Exposes ``.container``, ``.video_stream``, ``.audio_streams`` for power users who want direct PyAV

**Cached mode**: ``IOCacheVideo(path, cached=True)`` loads the file into ``BytesIO`` before passing to PyAV, improving seek performance for repeated random access.

### Bug fixes and refinements discovered during implementation

1. **`InputContainer` has no `time_base`** — PyAV 17.x doesn't expose it. Must use `stream.time_base` for seek calculations.
2. **Frame timestamps**: `frame.pts * frame.time_base` is already in seconds (since `av.time_base` = `Fraction(1, 1)`). No division by container timebase needed.
3. **AAC audio seek**: AAC frames are very small (2 samples per frame), but the time-range filtering in the decode loop handles this correctly.
4. **`container.decode(stream)` accepts no fps parameter** — PyAV's decode method signature is ``decode(streams=None, video=None, audio=None, subtitles=None, data=None)``. Our per-frame time filtering approach is the correct way to achieve target sampling rate.
5. **`av.open()` format parameter is optional** — defaults to auto-detect. Removed hardcoded ``format="mp4"`` so the code works with MKV, WEBM, AVI, etc.

### `create_slices()` removal

``create_slices`` was removed as a convenience function. The design decision is: ``IOCacheVideo`` is the sole interface — users who need sliding windows can write a short loop or use the upcoming ``Calculator`` module. This keeps the codebase minimal and gives users full control.

### Validation

Tested against `short_test.mp4` (60s, 1920×1082, H.264 + AAC):

- **`str` path**: opens and extracts frames correctly
- **`Path` object**: opens and extracts frames correctly
- **`cached=True` + `Path`**: loads to BytesIO, extracts correctly
- **`BytesIO` input**: `IOCacheVideo(load_bytes(...))` works
- **Basic open + info**: duration, fps, resolution all correct
- **`get_frames(0, 5)`**: returns 4 frames at 1fps, shape `(4, 1082, 1920, 3)`, uint8 RGB
- **`get_audio(0, 5)`**: returns 1 clip (AAC format means small frames, but extraction is correct)
- **Cached mode**: `IOCacheVideo(path, cached=True)` works, frames match non-cached
- **Time range slices**: seeking to arbitrary positions (15-20s, 45-50s) works correctly
- **Empty range**: returns empty array/list gracefully
- **Power user direct AV**: `video.container.seek()` + `video.container.decode()` works as expected

### Follow-up

- [ ] Implement `Calculator` module (sliding window, range list, full video calculators)

### Iteration 2 (post-initial rewrite)

| Change | Details |
|--------|---------|
| Removed `SliceSource` | Dataclass replaced with plain dicts in `create_slices` |
| Removed `SliceResult` | `slice.py`'s `SliceResult` was a duplicate of `src/models.py`'s Pydantic ``SliceResult`` — keep only the Pydantic version |
| Removed `create_slices` | Convenience function removed — ``IOCacheVideo`` is the sole interface |
| Removed `format="mp4"` | `av.open()` auto-detects container type; works with MKV, WEBM, AVI, etc. |
| Added `Path` support | `IOCacheVideo.__init__` accepts ``Path | str | BytesIO`` |
| Extracted `_normalize_audio` | Moved to standalone ``src/utils/audio.py`` as ``normalize_audio(data)`` |
| Updated `__init__.py` | Exports: ``IOCacheVideo``, ``SliceParams``, ``VideoInfo``, ``load_bytes``, ``normalize_audio`` |
- [ ] Run against the 57.7-minute test video (`2026_05_11-19_18_26_louder4x.mp4`) for real-world validation
- [ ] Update existing `tests/test_slice_utils.py` to use new API

## References

- [src/utils/container.py](../../src/utils/container.py)
- [src/utils/slice.py](../../src/utils/slice.py)
- [src/utils/__init__.py](../../src/utils/__init__.py)
- [19_2026_06_10_agent_slice-utils-implementation.md](./19_2026_06_10_agent_slice-utils-implementation.md) — previous implementation (now replaced)
- [20_2026_06_10_agent_ffmpeg-runtime-setup.md](./20_2026_06_10_agent_ffmpeg-runtime-setup.md) — FFmpeg/ffprobe setup
