---
created: 2026-09-17
author: agent
type: agent
tags: [video2text, long-audio, diarization, speaker-embedding, ek7qdwwxz6a, pipeline-complete]
---

# Ek7qDwwXZ6A 新管線全程完成（含語者統一品質旗標）

## What

- ASR 伺服器由使用者啟動（sglang-omni，port 8750）後，管線全程跑完：
  `transcribe_iterative.py` → **7 parts／4096 segments／零 fallback／零重試**（~29min）→
  `speaker_unify.py`（**10 全域語者＋2 未定案**）→ s2twp 轉繁體
- 新增 `scripts/check_separation.py`（分群品質檢驗：intra/inter 餘裕）
- ⚠ **品質旗標**：分離餘裕 **−0.103**
  - p3S01×p3S04 = 0.9494：同段受段內唯一性約束擋住、分屬 G05／G01
  - G07 最弱 intra pair 0.8464（p0S08×p4S04）
  - 判讀：直播檔噪音（BGM／酒後嗓音變化）使 embedding 空間比舊片擁擠；
    p3S01×p3S04 疑似段內 diarization 拆同一人（與「段內標籤可信」前提衝突），
    或兩人聲音極近——需人工抽聽裁決
- U_p0_S01／U_p6_S01：各僅 1 個 <1s 段，無法取可信 embedding → 依設計標未定案

## Why

- 繼 02（阻塞回報）之後完成執行；分離餘裕負值屬「有歧義明確列出等人」的設計範圍

## How

- 切點（絕對時間）：1436.810 → 2487.230 → 3510.320 → 4537.080 → 5661.720 →
  6751.820 → 7823.813（片尾）；全部由完整句界定
- 全域語者規模：G01–G08 各 160–700 段／194–876s；G06/G09/G10 為單例小群

## Follow-up

- [ ] 使用者抽聽複查：p3S01 vs p3S04（是否同一人）；G07 內部連結
- [ ] 依裁決調整（改 τ 重跑、或人工對映表）；確認後 02/03 合併結案

## Uncertainty

- 10 個全域語者是否即實際人數（片名 ≥5 人＋可能進出；負餘裕下可能多算或少算）
- 單例群（G06/G09/G10）是真語者短暫出場，還是 embedding 噪聲誤分

## References

- [執行受阻紀錄（前一晚）](02_agent_ek7-pipeline-execution.md)
- [執行時間軸](../../exp/Ek7qDwwXZ6A/execution-log.md)
- [語者統一報告](../../exp/Ek7qDwwXZ6A/speaker_unify_report.json)
