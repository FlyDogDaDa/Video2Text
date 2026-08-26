---
created: 2026-08-26
author: agent
type: agent
tags: [chat-log, reorganization, directory-structure]
---

# 重整 chat_with_my_agent 為按日資料夾結構

## What

把 `chat_with_my_agent/` 從**扁平 79 檔**（`{全域count}_{date}_{role}_{topic}.md` 平鋪）
重構為技能規範的**按日資料夾**：18 個 `{yyyy}_{mm}_{dd}/`，檔名改 `{當日count}_{role}_{topic}.md`；
6 個散根的 `.py` references 夾移入對應日期的 `scripts/{topic}/`。

## Why

- 日誌技能已改為按日分夾＋當日流水號命名；舊扁平結構與全域 count 不合規範。
- 散根 references 夾實為程式歸檔，應歸 `scripts/`。
- 順手修：role 缺漏（`docs`/無標記）補 `agent`、topic 全小寫＋連字符、孤兒檔歸位。

## How

- 依檔名日期分組建 18 個日期夾；count 改當日從 00 重起。
- 舊 `…_references_…`/`…_asr_audio_transcription` 夾＝程式，改掛 `scripts/` 下並重命名 kebab-case。
- 孤兒檔 `18_vllm_audio_extraction_logic.md` 依位置歸 `2026_06_09/08_agent_vllm-audio-extraction-logic.md`。
- 08_26 已符合新格式，未動。
- 踩坑：路徑需 `Video2Text/` 前綴；`move_path` 不能改名到已存在目錄，改逐檔搬＋刪空夾。

## Follow-up

- 若要入 git，可視需要 commit 這次結構重整（本次未提交）。

## Uncertainty

- 無。搬移為純路徑變更，未改任何日誌內容。

## References

- [討論細節](references/02_agent_reorganize-chat-log-archive.md)
