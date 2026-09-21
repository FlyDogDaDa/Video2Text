---
created: 2026-09-20
author: human
type: agent
tags: [speaker-diarization, tau-sweep, meeting-contrast, v3.1]
---

# 會議對照組實驗 ＋ τ 自適應平台期掃描

## What

1. 新工具 `tau_sweep.py`：τ 平台期掃描（自適應 τ 方案 1）——embed 一次、對 τ 網格（0.10–0.70）各跑一次叢集級凝聚分群、自動選最寬完全穩定平台期中心當 auto_tau。
2. 對照組實驗：乾淨會議音訊（頂尖工程部會議 2026-08-25，1:53:38）跑完整管線（ASR → 掃描 → v3.1 定版），與 Ek7（喝酒直播、多語者交疊）對比。
3. τ 概念語境說明（v3 cosine 刻度 vs v3.1 vote-affinity 刻度）與端到端耗時分析。

## Why

- Ek7 的 GT 評估停在 0.621 且 GT 本身有三角矛盾 → 需要乾淨對照組分離「算法問題」與「資料問題」
- 使用者問「τ 能自適應嗎」→ 平台期掃描把「用耳朵調 τ」變成「量測結構穩定性」

## How

- 轉檔：`ffmpeg -ac 1 -ar 16000 -c:a pcm_s16le` → `exp/Meeting20260825/audio_full.wav`（6818.6s，mp3 原生 16k mono）
- ASR：`transcribe_iterative.py`（5 段、2108 句，錨點句尾切點、零盲切 fallback）
- 掃描：`tau_sweep.py exp/Meeting20260825`；Ek7 對照：`tau_sweep.py exp/Ek7qDwwXZ6A exp/Ek7qDwwXZ6A/compare_tau_sweep`
- 定版：`speaker_unify_v31.py exp/Meeting20260825 --tau 0.30`（在平台期內）
- 過程 bug：`cluster_at_tau` 回傳 int 索引 frozenset，`partition_pairs` 期待標籤字串 → KeyError 'p0S01'，修正為回傳 labels frozenset

## 主要數字

| | 會議（乾淨） | Ek7（髒） |
|---|---|---|
| 全域語者 | 6G＋0U | 8G＋2U |
| 投票一致率 | 0.961（432 票） | 0.7529 |
| auto_tau | 0.225 | 0.2 |
| τ≥0.50 訊號 | 有（第二平台 0.55–0.65） | 全斷（37 叢集全開） |

結論：支持「Ek7 難度主要來自資料污染」假說；τ 自適應可行且近乎免費（embed 本來要算，多次分群僅秒級）。

## Follow-up

- 會議 6 叢集未經人耳確認（實際人數未知）；5 個投票衝突小組（p0S04/p0S05/p1S06/p3S03/p4S05）待驗
- Ek7 第三輪乾淨抽聽判定（listening_clips_v3_clean/，60 clips）未回收
- τ 自適應方案 2（ratio 保護）、方案 3（permutation null）未實作
- Ek7 execution-log.md 尚缺 v3.1 段落補帳

## Uncertainty

- 會議 6 叢集正確性未驗證（可能 5 人也可能 7 人）
- 低邊界平票合併（aff=0.50、margin=0.00）被接受是設計取捨，是否該擋未定案
- auto_tau「最寬平台期中心」策略目前只在兩個樣本上驗證

## References

- [討論細節](references/00_human_meeting-speaker-stitch-experiment.md)
- [tau_sweep 歸檔](scripts/tau-sweep/README.md)
- [會議實驗執行日誌](../../exp/Meeting20260825/execution-log.md)
- [Ek7 執行日誌](../../exp/Ek7qDwwXZ6A/execution-log.md)
