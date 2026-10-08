---
created: 2026-09-16
author: human
type: human
tags: [video2text, long-audio, diarization, speaker-embedding, pipeline-design, exp-ek7qdwwxz6a]
---

# 超長音訊管線設計定案（執行前計畫）

## What

- 完成「超長音訊處理」管線的完整設計討論並定案，四階段架構：
  1. **迭代切分轉錄**：逐字稿尾端回掃句界定切點，循環到片尾
  2. **段內分群抽音色**：每段每語者一個 centroid
  3. **全域相似度矩陣 + 約束合併**：constrained union-find 頒布全域唯一語者標籤
  4. **組裝輸出**：offset 平移 + `speaker_global` 欄位
- 建立新實驗環境 `exp/Ek7qDwwXZ6A/`（`scripts/` 目錄 + `.venv`：yt-dlp 2026.8.19、httpx）
- 探測新測試影片後設資料（見下方 Why／References）

## Why

- 舊管線（N9boWvU-KkA）兩個已知缺陷：等分盲切（句子腰斬、段頭失去語境）、speaker 跨 part 不具同一性
- 舊測試資料太簡單：只有 2 位語者且編號恰好沒亂，無法驗證語者統一邏輯
- human 裁決：管線每一處都換掉 → **全部重跑**，另開實驗資料夾較穩妥；新測試片用
  Ek7qDwwXZ6A（直播存檔，7824s ≈ 2h10m，多人喝酒對談，難度遠高於舊片）

## How

- 設計細節與推進過程全記錄於 References 討論檔（含流程圖、參數表、陷阱修正）
- 環境：`uv venv exp/Ek7qDwwXZ6A/.venv`；`uv pip install yt-dlp httpx`
- 探測：yt-dlp `-J` 取得 title／duration／formats（video 248/399/616、audio 251-drc/140/251）

## Follow-up（執行清單，TODO）

- [ ] 下載 Ek7qDwwXZ6A（video + audio 分流，`-c copy` 合 MKV；格式適用性下載時實測）
- [ ] 抽 `audio_full.wav`（PCM s16le 16kHz mono）
- [ ] 寫 `scripts/transcribe_iterative.py`（Phase 1：逐字稿驅動迭代切分轉錄）
- [ ] 寫 `scripts/speaker_unify.py`（Phase 2–4：centroid → 相似度矩陣 → 約束合併 → 組裝）
- [ ] 驗證：相似度矩陣目檢、flag 清單人工裁決、最終逐字稿抽查
- [ ] 完成後回寫日誌＋歸檔腳本

## Uncertainty

- τ=0.75、δ=0.05、margin=2s、guard=0.3s、NOMINAL=24min 皆暫定，待實測分佈調整
- 直播檔特性未知：BGM／掌聲／長沉默對 diarization 與 embedding 的干擾
- 實際語者人數未知（片名可見 ≥5 人，可能有進出）
- resemblyzer 依賴 torch（CPU 版），安裝大小與耗時未驗證
- ASR 伺服器 `10.46.219.5:8750` 執行當下的可用性
- 「無輸出=結束」規則在長直播中段遇長沉默是否誤判（是否加「離片尾遠→前進」分支未定案）

## References

- [討論全記錄](references/01_human_long-audio-pipeline-design.md)
- [舊實驗 TODO（流程與慣例基準）](../../exp/N9boWvU-KkA/TODO.md)
- [新測試影片](https://www.youtube.com/watch?v=Ek7qDwwXZ6A)
