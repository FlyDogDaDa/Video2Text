# Repo Cleanup — 全過程細節（agent 報告彙整）

日期：2026-10-03（工作發生日；日誌歸在 2026_10_02 資料夾隔壁新日）
發起：human（「如果專案要整理的話你會怎麼進諫？」→ 選定 8 項 → 要求全平行 sub-agent 作業）

## Phase 1：專案健檢（進諫依據）

實際掃描：目錄結構、pyproject.toml、.gitignore 全文、workflow.py、framework/config.py、
test_voicetag.py 開頭、testing.json 開頭、serve/voicetag、serve/stt-api 結構。
磁碟量測：`chat_with_my_agent` 3.5M、`.venv` 5.8G、`exp` 13G、`serve` 7.1G、
`output.mkv`/`output.webm` 各 400M。

grep 驗證（imports）：
- 根層程式碼（modules/、framework/、workflows/、workflow.py）只用 httpx、pydantic、pyyaml。
- requests、vllm、imagebind 在根層零 import；vllm/imagebind 只出現在 chat 紀錄與 serve/sam-audio 的環境。
- README.md 為空檔案；pyproject description 仍是 "Add your description here"。

產出 13 項進諫清單（含目標結構與四層執行順序）。human 選了其中 8 項：
#2 死依賴、#3 800MB 影音檔、#4 測試腳本調查後刪、#5 README+描述、
#6 gitignore 打地鼠、#7 空目錄整併、#9 main.py 殘留、#10 testing.json 歸位。
未選：#1 workflow 改名（連動大）、#8 chat_with_my_agent 處置、#11 workspace 統一、#12 src layout、#13 token 模式。

## Phase 2：拆題（sub-agent-delegation 技能判斷）

通過三檢查：可拆、各自自我完備、寫入範圍互不重疊。關鍵衝突解法：
- pyproject.toml 有兩個任務要碰（#2 deps、#5 description）→ 整併給「依賴瘦身」agent 獨佔；README agent 只寫 README.md。
- .gitignore 只有「目錄整併」agent 可寫。
- data/ 慣例（media/out/tmp）統一廣播給搬檔 agent，mkdir -p 併發安全。

6 個 sub-agent 同時發射 + 我自己刪 main.py（#9，刪前 grep 確認無 `import main`——唯一命中在 chat 紀錄內的實驗腳本，指向該目錄自己的 main.py）。
刪前另查：testing.json 無程式碼引用（只有 chat 紀錄 .md 提到）；test_voicetag 兩檔只有彼此 docstring 提到。

## Phase 3：六路 agent 回報

### A 依賴瘦身＋描述（session 0551ee3c）✅
- pyproject.toml：移除 requests、vllm、imagebind；刪 [tool.uv.sources]；pytest → [dependency-groups] dev；description 填入。
- `uv lock` 成功：Resolved 169 packages，移除 37 套件（vllm、imagebind、transformers、ray、xformers、fschat、timm…）；`uv lock --check` 通過。
- 補充：requests 仍在 lock（傳遞依賴，正常）；numpy 保留（根層其實也沒直接用，但不在授權範圍）。
- 未跑 uv sync（依指示不動 .venv），下次 uv run 會自動 prune。

### B 影音檔搬遷（session b6dde553）✅
- output.mkv、output.webm → data/media/（各 400M），根目錄確認清空。

### C 測試腳本調查（session a9031e94）✅ → 兩檔兩檔刪除
證據鏈：
1. 輸入全失效：test-audio/speech-reference.mp3（test_voicetag.py L27）、test-audio/2026_07_21_test.mp3（L64）、test-audio/speaker-ref/{黃,文,婕,陳}.wav（meeting L16–22）、test-audio/保修工程會議.wav（L56,63）、output/voicetag/*（兩檔多處）——目錄皆空。
2. import 鏈仍通（voicetag_core.enroll L108、identify L156、_vt L29），但全專案除兩腳本外無人呼叫 voicetag_core.enroll()；workflows/speech_to_text.py L239 的活躍 enroll 是 voicetag 套件的 vt.enroll()，不同鏈。
3. 服務化取代：workflows/voicetag.py identify_audio()（L29–101）涵蓋 identify→結構化→存 JSON＋CLI；serve/voicetag/api/main.py 有 POST /identify、GET /health。
4. 無其他引用（排除 chat 紀錄）。
結論：三條件全符合 → 刪除 test_voicetag.py、test_voicetag_meeting.py（皆為 git 追蹤追蹤檔，刪除會顯示在 status）。
重建路徑：voicetag_core.enroll() + vt.save()，或比照 workflows/speech_to_text.py。

### D README 撰寫（session 1d3d6609）✅
章節：簡介＋流程圖、目錄結構（整併後目標狀態）、快速開始、serve 五服務表、
設計說明（serve 獨立 .venv 的四個實際原因：transformers 版本互斥、decord 無 Py3.12 wheel、
torch CUDA index 不同、uv 不穿透第二層相依）、開發注意。
取材發現的文件不一致（未動作，列為後續）：
1. serve/quark-audio/、serve/vllm/ 無 README。
2. webuis/README.md 是空檔案，但 webuis/pyproject.toml 宣告 readme = "README.md"。
3. serve/stt-api/README.md 的 screen 範例路徑寫 /home/freespace/檔案/Video2Text，實際是 /文件/。
4. stt-api README 的 Breeze 服務寫 @8754，launch_BreezeASR26.sh 預設 PORT=8750。
5. profiles/final.yaml 的 asr.model 是 google/gemma-4-12B-it-qat-w4a16-ct（LLM 名稱，疑實驗殘留）。

### E gitignore＋目錄整併（session be384f61）⚠️ 部分完成
- .gitignore 尾段：48 行 → 17 行，打地鼠條目（output.mkv/webm/mp4、short_test.mp4、temp.wav、
  2026_03_17-20_27_48.mkv、main copy.py、*copy.py、_transcriptions.zip、空段落）全數移除；
  保留 .agents/、serve checkpoints/jobs、exp/、chat 參考路徑；新增 data/。
- **rmdir 5/5 全失敗**：scratch/（26 檔：stt_api_*.json/log 活動到 10/2、實驗腳本）、
  output/（12 檔 ~4.9MB：STT JSON、FA mp4、音檔）、test-audio/（gaokao-listening.wav、
  meeting_20260721.mp3/wav、speaker-ref/、tests/）、tmp/（clip1 影片與 log）、
  runtime/（ffprobe 76MB，且已被 git 追蹤）。
  → 與我第一輪 list_directory「五目錄皆空」的回報矛盾；疑似 STT API 等背景程序持續寫入。
  依安全指示（rmdir 非 rm -rf）全部保留。
- data/{media,out,tmp} 骨架建立成功；exp/ 未動。
- git status 副作用：ignore 條目移除後 output/、scratch/、test-audio/、tmp/ 變 untracked 噪音。

### F testing.json 歸位（session 08b25d37）✅
- 引用複查：8 個匹配全在 chat 紀錄 .md，無程式碼引用 → 搬移。
- testing.json → data/out/testing.json（71K），根目錄清空確認。

### 我自己（#9）
- main.py（uv 模板 hello world）刪除。

## Phase 4：收尾止血與驗證（我自己）

1. .gitignore 尾段再加回五個 legacy 目錄條目（output/、scratch/、test-audio/、tmp/、runtime/），
   註記 pending migration into data/——因為目錄非空、#7 前提不成立，先消 git status 噪音。
2. `serve/vllm/launch_MOSS_TD.sh`（+12/−2）確認非任何 agent 所為：內容是長音訊參數調校
   （GPU_MEM_UTIL 0.12→0.25、max_num_batched_tokens 24576、override max_new_tokens 16384、
   audio clip 64MB / decode 1800s），屬 human 自己的未提交修改 → 不動。
3. 終態驗證：git status 只剩本次變更 + 兩個既有 untracked（chat_with_my_agent/2026_10_02/、
   serve/stt-api/ 整個服務從未入庫）；data/media 兩檔、data/out/testing.json 就位；
   `uv lock --check` 通過。

## 決策與理由摘要

- 為何用 rmdir 不用 rm -rf：空目錄整併的前提靠 rmdir 驗證，非空即擋——這次正是它救了 13G 以外的本地資料。
- 為何 #7 不硬做：內含今日活動的 STT 產物與被追蹤的 ffprobe，硬遷移可能弄壞仍在跑的服務；改為保留＋ignore＋待 human 決定遷移方案。
- 為何 numpy 保留：不在 human 授權清單，寧可保守。
- 為何不 commit：human 未要求。
