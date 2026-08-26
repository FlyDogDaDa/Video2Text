---
created: 2026-06-11
author: Zed Agent
type: agent
status: final
tags: [gemma4, video-understanding, timestamp, research]
---

# Gemma 4 Video Understanding — Timestamp Format Research

## What

Researched and documented how Gemma 4 handles timestamps for video understanding tasks, specifically how to format timestamps so the model can correctly associate time points with visual and audio events.

## Why

The project requires Gemma 4 to understand temporal relationships between video frames and audio. Understanding the correct timestamp format is essential for building reliable video QA, event localization, and cross-modal consistency checking features.

## How

Researched Gemma 4's timestamp handling through official documentation, community guides, and source code examples. Found two distinct timestamp formats depending on usage context:

### Two Timestamp Formats

| Context | Format | Example | Notes |
|---------|--------|---------|-------|
| Gemini API (cloud) | `MM:SS` | `01:15`, `00:05` | Official format for Gemini API video prompts |
| Local deployment (edge) | `[X.Xs]` or `Frame {seconds}:` | `[30.0s]`, `Frame 0.63:` | Manual embedding required; model has no built-in timestamp awareness |

### Key Findings

- **Gemma 4 exists** — released 2026-03-31 by Google DeepMind (not Gemma 3 as previously assumed). The "Gemma 4 12B" variant was released 2026-06-03.
- **No built-in timestamp awareness** — when processing frames locally, the model does not automatically receive timestamps. Timestamps must be manually embedded in text captions alongside frames.
- **Two API contexts**:
  - **Gemini API** (cloud): handles video as a single file, samples at 1 FPS + 1 Kbps audio, and uses `MM:SS` format for timestamp references in prompts.
  - **Local (Hugging Face / llama.cpp)**: requires manual frame extraction and timestamp embedding via text interleaving.
- **Model support varies**:
  - E2B/E4B/12B: support video + audio (E2B/E4B up to 60s video, 30s audio)
  - 26B A4B / 31B Dense: support video but **no audio input**

### Sources Consulted

- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core) — official capabilities
- [Gemma 4 12B Developer Guide](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/) — encoder-free architecture details
- [Gemma 4 Audio/Video Guide (DEV.to)](https://dev.to/pulkitgovrani/gemma-4s-audio-and-video-inputs-a-hands-on-guide-nobody-has-written-yet-2m2c) — practical code examples and limitations
- [Gemma 3 Video Understanding Notebook](https://colab.research.google.com/github/merveenoyan/smol-vision/blob/main/Gemma_3_for_Video_Understanding.ipynb/) — interleaving pattern with `Frame {seconds}:` format
- [Gemini API Video Understanding](https://ai.google.dev/gemini-api/docs/video-understanding) — `MM:SS` timestamp format for API prompts

### Model Support Table

| Model | Video | Audio | Context |
|-------|-------|-------|---------|
| Gemma 4 E2B | ✅ (60s) | ✅ (30s) | 128K |
| Gemma 4 E4B | ✅ (60s) | ✅ (30s) | 128K |
| Gemma 4 12B | ✅ | ✅ | 256K |
| Gemma 4 26B A4B | ✅ | ❌ | 256K |
| Gemma 4 31B Dense | ✅ | ❌ | 256K |

## Follow-up

- Decide which Gemma 4 variant to use (E4B for edge, 12B for desktop, 31B for server) based on hardware constraints
- Implement timestamp embedding logic for local frame-based video processing
- Test both `MM:SS` (API) and `[X.Xs]` (local) formats in actual video QA prompts
- Consider video clipping/segmentation for longer videos exceeding 60s frame limit

## References

- [25_2026_06_11_agent_vllm-delayed-guided-decoding-offline.md](../25_2026_06_11_agent_vllm-delayed-guided-decoding-offline.md) — previous day's VLLM offline research
- [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core)
- [Gemma 4 12B Developer Guide](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/)
- [Gemma 4 Audio/Video Guide (DEV.to)](https://dev.to/pulkitgovrani/gemma-4s-audio-and-video-inputs-a-hands-on-guide-nobody-has-written-yet-2m2c)
- [Gemini API Video Understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
