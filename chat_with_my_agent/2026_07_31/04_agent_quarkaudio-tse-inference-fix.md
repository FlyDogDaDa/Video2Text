---
created: 2026-07-31
author: Vincent
type: agent
status: final
tags: [quark-audio, tse, bug-fix, inference]
---

# 修復 QuarkAudio-UniSE TSE 推理變數名稱錯誤

## What

修正 `serve/quark-audio/quark_audio/api.py` 中 `_tse_infer()` 方法的變數名稱錯誤，使 TSE 推理可以正常執行。

## Why

官方 `model/model.py` 的 `test_step` 實作中，TSE 推理使用 `src` 作為變數名，但我們在 API wrapper 中將輸入命名為 `mix`。第 255 行 `est.reshape(-1)[: src.size(-1)]` 會導致 `NameError`，因為 `_tse_infer(self, enroll, mix)` 作用域中沒有 `src` 變數。

此外，官方程式碼的 TSE 實作（第 199-228 行）使用 padding + reshape 批次處理，不需要分段疊加。之前的實作有概念性錯誤，已重新對齊官方邏輯。

## How

- `serve/quark-audio/quark_audio/api.py`:
  - `_tse_infer()` 第 228 行：新增 `orig_len = mix.size(-1)` 儲存原始音訊長度
  - `_tse_infer()` 第 256 行：將 `src.size(-1)` 改為 `orig_len`，避免變數不存在與正確截斷
- 對齊官方 `model/model.py` 第 199-228 行 TSE 實作邏輯

## Follow-up

- ✅ 執行實際 TSE 推理測試：成功！`workflows/quark-audio.py` 完成
- ✅ 輸出音訊驗證：`output/tse_result.wav` — 3.7MB, RIFF WAVE, 16-bit PCM, mono 16kHz
- 可考慮將 `checkpoints/` 加入 `.gitignore`（大型二進位檔案）
- 可封裝為服務端 API（FastAPI / HTTP endpoint）

## References

- [serve/quark-audio/quark_audio/api.py](../../serve/quark-audio/quark_audio/api.py)
- [serve/quark-audio/unified-audio/QuarkAudio-UniSE/model/model.py](../../serve/quark-audio/unified-audio/QuarkAudio-UniSE/model/model.py)
- [workflows/quark-audio.py](../../workflows/quark-audio.py)
- [QuarkAudio-UniSE GitHub](https://github.com/alibaba/unified-audio)