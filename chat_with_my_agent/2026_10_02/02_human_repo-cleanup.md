---
created: 2026-10-03
author: agent
type: human
tags: [repo-cleanup, parallel-agents, pyproject, gitignore, readme]
---

# Repo Cleanup：8 項整理任務全平行執行

## What

- 依人類選定的 8 項整理清單，拆成 6 個寫入範圍互不重疊的 sub-agent 同時發射＋1 項由主 agent 直接執行，全部完成或安全止步。
- 完成項：#2 根依賴瘦身（移除 requests/vllm/imagebind、pytest 入 dev group、補 description＋`uv lock`）、#3 800MB 影音檔遷入 `data/media/`、#4 兩個 voicetag 手動測試腳本調查後刪除、#5 README 從零寫入、#6 .gitignore 尾段 48→17 行、#9 刪除 uv 模板殘留 `main.py`、#10 `testing.json` 遷入 `data/out/`。
- 部分止步項：#7 五個目錄整併——實測非空（與健檢時的回報矛盾），`rmdir` 安全機制全擋，未強刪，改為保留目錄＋回補 ignore 條目。

## Why

- 健檢結論：專案核心結構（modules/framework/profiles/serve）清晰，亂點集中在根目錄與邊界；8 項任務互相獨立、爆炸半徑小，適合最大並行。
- 拆題衝突解法：pyproject.toml 由依賴 agent 獨佔（#2＋#5 的 description 半邊），README agent 只寫 README.md；.gitignore 只由目錄整併 agent 寫。
- #4 不直接刪：先跑四項證據檢查（輸入檔失效、import 鏈 dead-end、服務化已取代、無外部引用）全過關才刪。

## How

- 六路 agent 並行：依賴瘦身、影音搬遷、測試腳本調查、README、gitignore＋目錄、testing.json 歸位；`main.py` 刪除由主 agent 執行（刪前 grep 確認無引用）。
- 依賴：`uv lock` Resolved 169 packages、移除 37 套件、`uv lock --check` 通過；未跑 `uv sync`（.venv 待下次 uv run 自動 prune，或手動跑以釋放數 GB）。
- 檔案遷移：`output.mkv`/`output.webm` → `data/media/`；`testing.json` → `data/out/`；`data/{media,out,tmp}` 骨架建立。
- 收尾：.gitignore 尾段回補五個 legacy 目錄條目（消除 untracked 噪音）；`serve/vllm/launch_MOSS_TD.sh` 的 +12/−2 經 diff 查核確認是 human 自己的長音訊調校，未動。

## Follow-up

- [x] `serve/stt-api/` 已入庫（commit `c6c1edc`，7 檔 2279 行；`models/` 權重新增 ignore 條目排除）
- [x] 清理變更已入庫（commit `83d96d5`：deps 瘦身＋README＋gitignore 整併＋刪 main.py/test 腳本）
- [ ] #7 遺留決策：五個非空目錄（scratch/、output/、test-audio/、tmp/、runtime/）——經查證 test-audio 是程式指向的素材庫、runtime 是工具箱、output 是設定指向的輸出槽、scratch/tmp 是無引用暫存；結論為維持現狀，僅 tmp/（1.7MB）與舊實驗檔可選擇性清除，等使用者一句話
- [ ] 跑 `uv sync` 釋放 .venv 約數 GB（37 個已從 lock 移除的套件）
- [ ] README 取材時發現的文件不一致五項：quark-audio/vllm 缺 README、webuis/README.md 空檔卻被 pyproject 引用、stt-api README 路徑誤寫「檔案」、Breeze 埠號 8754 vs 8750 矛盾、profiles/final.yaml 的 asr.model 疑似實驗殘留。
- [ ] numpy 根層也未直接使用，可再評估是否移除。

## Uncertainty

- 五個目錄「健檢時空、整併時非空」的成因未定案：推測 STT API 等背景程序持續寫入（scratch 內 stt_api_*.log 活動到當日），但也可能是最初 list_directory 回報失準——未做逐檔 mtime 對時驗證。
- `chat_with_my_agent/2026_10_02/` 與 `serve/stt-api/` 整目錄 untracked 是既有狀態（本次未處理），是否該入庫屬人類決策。

## References

- [討論細節：健檢清單、拆題、六路 agent 回報全文](references/02_human_repo-cleanup.md)
