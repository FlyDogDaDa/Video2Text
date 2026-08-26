# 討論細節：重整 chat_with_my_agent 目錄結構

## 背景

`chat_with_my_agent/` 原為**扁平結構**：79 支 `.md` 日誌直接平鋪在根目錄，命名為
`{全域count}_{yyyy}_{mm}_{dd}_{role}_{topic}.md`（count 跨日期全域遞增 00–78），
另有 6 個以 `{count}_{date}_references_…` 命名的散根資料夾，內含 `.py` 腳本。

日誌技能（daily-log-writing）已更新為「**按日資料夾**」規範：

```
chat_with_my_agent/{yyyy}_{mm}_{dd}/
├── {count}_{agent|human}_{topic}.md   # 主日誌，count 當日從 00 重起
├── references/{count}_….md            # 討論細節
├── scripts/{folder_name}/             # 程式歸檔
└── assets/{folder_name}/              # 參考文件歸檔
```

目標：把既有檔案重構成此結構。

## 決策

1. **按日期分組**：從檔名抽出 `{yyyy}_{mm}_{dd}` 建資料夾；共 18 個日期（08_26 已存在）。
2. **count 改為「當日流水號」**：每個日期資料夾內從 `00` 重起，取代跨日期全域編號。
3. **role 補全**：`docs`（#03/#04/#21）與無 role 標記者（#39/#46/#49/#50 daily-log）一律歸為 `agent`。
4. **舊 references/資料夾 → `scripts/`**：6 個散根資料夾皆含 `.py`，依技能規範移入
   `{date}/scripts/{kebab-topic}/`；搬完清空後 `delete_path` 移除空目錄。
5. **孤兒檔** `18_vllm_audio_extraction_logic.md`（無日期/count/role）：依位置（夾在 06_09 #17 與 06_10 #19 之間）
   判斷屬 2026_06_09，命名為 `08_agent_vllm-audio-extraction-logic.md`（當日該日第 8 筆）。
6. **topic 全小寫 + 連字符**：`v0.1.1`→`v0-1-1`、`pkg_resources`→`pkg-resources`、`PyAV_and_MoviePy`→`pyav-and-moviepy`。

## 工具踩坑

- **路徑前綴**：`create_directory` / `move_path` / `delete_path` 需以專案根目錄名開頭，
  即 `Video2Text/chat_with_my_agent/…`；只寫相對 `chat_with_my_agent/…` 會回「Path … outside the project」。
  （`read_file` / `list_directory` / `grep` 用純相對路徑即可。）
- **`move_path` 不能改名到已存在的目錄**：預建空 `scripts/{topic}/` 後再想 `move_path` 整個舊資料夾會
  `File exists (os error 17)`。解法＝先建目標、再逐檔搬內層、最後 `delete_path` 舊空夾。

## 執行順序（4 輪 batch）

1. 建 17 個日期資料夾（08_26 已存在）＋ 6 個 `scripts/{topic}` 子夾。
2. 搬 06_xx：06_07(8)＋06_08(2 檔+1 腳本)＋06_09(8 檔+孤兒+1 腳本)＋06_10(4)＋06_11(12 檔+3 腳本)＋06_12(2)＋06_13(2 檔+1 腳本)。
   腳本資料夾用「逐檔搬＋刪空夾」。
3. 搬 07_xx：07_20(7)＋07_21(1)＋07_22(6，含重複 50)＋07_29(1)＋07_31(13)。
4. 搬 08_xx：08_03(3)＋08_06(1)＋08_07(2)＋08_14(2)＋08_18(4)；並 `delete_path` 清掉 6 個已空舊夾。
   08_26 已符合新格式，未動。

## 驗證

- `list_directory chat_with_my_agent`：根目錄只剩 18 個日期資料夾，無平鋪 `.md`、無舊 references 夾。
- 抽驗 `2026_06_11`（含 scripts/ 三子夾＋12 主檔）與 `2026_07_22`（重複 50 拆成 02/03）內容正確。
