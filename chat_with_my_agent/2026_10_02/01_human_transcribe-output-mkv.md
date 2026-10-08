---
created: 2026-10-02
author: human
type: human
tags: [meeting-transcribe, stt-api, transcription, video2text]
---

# 用 meeting-transcribe 技能轉錄 output.mkv

## What

- 依指示以 `.agents/skills/meeting-transcribe/` 技能，把專案根目錄 `output.mkv`
  （35m46s／418.4MB，首次以 mkv 容器輸入）送 GB10 STT API 轉錄，輸出至根目錄 `testing.json`。
- 結果：**402 segments／2 全域語者（G01、G02）／無 warnings／已簡轉繁**，實際處理 253.3s。
- `job_id = 85401caa1954`；`audio_duration_s` 與 ffprobe 量測一致，結果完整性已驗證。

## Why

- 使用者直接指派；同時是 00 條目 STT API＋技能包上線後的首次實戰使用，
  順帶驗證 mkv 輸入路徑可用。

## How

- 前置：ffprobe 量得 2145.968s；`/health` 確認 ASR ready、無排隊；依此設定 40 分鐘 timeout。
- 執行：`python3 .agents/skills/meeting-transcribe/scripts/meeting_transcribe.py output.mkv --out testing.json`
  （其餘參數全用預設：輪詢 20s、簡轉繁開、不自訂 tau）。
- 詳細流程、進度軌跡與驗證數據見 References 討論細節；逐字稿已複製歸檔，
  原檔 `testing.json` 留在專案根目錄。

## Follow-up

- 視需要檢視 402 段逐字稿內容，並抽聽驗證 2 語者分組是否正確。
- 音檔前 350s 無語音段（首段自 349.98s 起）：若該開頭理應有聲音，需回頭檢查音軌；
  若為冗長片頭，未來可先修剪再上傳以省時間。

## Uncertainty

- 2 語者分組未經人耳驗證（沿用技能聲明之限制）。
- 本次耗時比 1/8.5 明顯快於 00 條目實測的 1/4.8，原因未查證（GPU 負載或語音密度差異皆可能）。

## References

- [討論與執行全記錄](references/01_human_transcribe-output-mkv.md)
- [逐字稿歸檔](assets/output-mkv-transcript/testing.json)
- [Agent 技能包](../../.agents/skills/meeting-transcribe/SKILL.md)
- [同日前置條目：STT API 服務化](00_agent_stt-api-service.md)
