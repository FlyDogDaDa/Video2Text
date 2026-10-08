---
created: 2026-08-26
author: agent
type: agent
tags: [fa-aligner, vllm, forced-alignment, 字幕, 實驗]
---

# FA 對齊驗證通過 + 黑底白字字幕預覽

## What

- FA 支線收尾：使用者以 `--trust-request-chat-template` 重啟
  `Qwen3-ForcedAligner-0.6B`（`10.46.219.5:8755`）後，改 `test_fa.py`
  依 vLLM 官方 online 範例在 `/pooling` 與 `/tokenize` 都帶
  `chat_template="{{ messages[0]['content'] }}"`，對齊正式跑通。
- 對 `output/是我用AI跑出來的.opus`（1.532s）完成逐字對齊（8 單位），
  另產黑底白字字幕預覽片 `output/2026-08-26_FA對齊字幕預覽.mp4`
  （ASS 置中、Noto Sans CJK TC、音訊用 opus 重產並覆蓋舊版）。
- 交叉驗證對齊精度：`ffmpeg silencedetect` + MOSS ASR 獨立轉錄
  （`asr_crosscheck.py`），兩者皆與 FA 時間戳吻合。
- 使用者剪輯程式逐幀檢查確認：繁體/簡體兩版對齊皆準確；先前看到的
  偏移是 VLC 音畫分離造成的，非對齊問題。

## Why

主流程步驟 5（過濾肯定詞 + 精準對齊）依賴 FA；先在小音檔上把
端點用法、token 對齊邏輯、精度都驗證過，之後才能放心套用到 4 段切分音訊。

## How

- `test_fa.py` 關鍵改動：raw-content `chat_template`（官方做法）+
  `usage.prompt_tokens` 長度交叉驗證；token 序列仍用伺服器 `/tokenize`
  取得（免本地 HF 依賴）。對齊 = 各 `<timestamp>` 位置
  `argmax(5000 bins) × 80ms`，偏移公式 `i + audio_token_shift`
  （本例 shift=0）。
- 字幕預覽：`subs_preview.ass`（1920x1080、Alignment=2、80pt）+
  `ffmpeg color=black` 合成，抽幀目視確認渲染正確。
- 驗證鏈：FA 對齊 → silencedetect（語音 0.0–1.46s）→ MOSS ASR
  （整句 0.00–1.50s）→ 使用者逐幀目測，四重一致。
- 確認模型特性：音訊頭尾留空時靠近該端的預測會「均勻攤開」
  （aac 有 0.2s 前導靜音 → 首字撐寬到 0.160–0.400；opus 貼合 → 首字 0.000–0.160）。
  屬訓練特性，對主流程切段送對齊的 padding 策略有影響。

## Follow-up

- 回主流程步驟 1：`yt-dlp` 下載 `N9boWvU-KkA` 影片（最高畫質+音質）。
- 切段送對齊時 padding 取小（~100–200ms），避免攤開效應。
- `filter_align.py` 可直接沿用 `test_fa.py` 的請求/對齊邏輯（batch=4 執行緒池）。

## Uncertainty

- 「攤開」特性在真实 4 段切分音訊上的實際影響幅度未實測
  （目前只有 1.5s 小樣本），以 padding 策略先行對沖。
- 中文字檔名經 terminal 指令會簡繁混轉，目前以 glob 規避；
  正式腳本內部走 Python 路徑不受影響，但命令行參數需注意。

## References

- [討論細節](references/04_agent_fa-alignment-verified.md)
- [程式歸檔](scripts/fa-pooling-test/README.md)（test_fa.py 最終版、asr_crosscheck.py）
- [對齊結果與產出歸檔](assets/fa-alignment-preview/test_fa_result.json)
- [ASR 交叉驗證結果](assets/fa-alignment-preview/asr_crosscheck_result.json)
- [ASS 字幕檔](assets/fa-alignment-preview/subs_preview.ass)
- [前一條目（卡點與探測過程）](03_agent_fa-alignment-test.md)
- [vLLM 官方 online 範例](https://github.com/vllm-project/vllm/blob/main/examples/pooling/token_classify/forced_alignment_online.py)
- [模型卡](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B)
