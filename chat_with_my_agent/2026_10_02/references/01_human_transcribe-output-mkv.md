# 轉錄 output.mkv → testing.json：執行全記錄

## 任務來源

使用者直接指派：「用這個技能（meeting-transcribe），轉錄 `output.mkv`，輸出到 `testing.json`」。
屬 00 條目（STT API 服務化＋技能包）完成後的首次實戰使用。

## 執行過程

### 1. 載入技能與定位輸入檔

- 載入 `meeting-transcribe` 技能，取得 API 位址（GB10 `http://10.46.219.5:8760`）、
  輔助指令碼用法、回傳結構與注意事項。
- `output.mkv` 不在預期搜尋路徑：`find_path` 以 `output.mkv` 與 `**/output.mkv` 兩次 glob 皆無結果，
  改用 `list_directory` 列專案根目錄才確認檔案就在根目錄
  （glob 對根目錄單層檔案的匹配行為與預期不符，屬工具使用經驗）。
- 附帶確認技能包結構完整：`scripts/meeting_transcribe.py` 存在（另有 `__pycache__`）。

### 2. terminal 前置檢查

- 依規範先載入 `terminal-navigation-guard`，確認 `cd` 只給根目錄、子路徑放 command。

### 3. 前置偵察（一條指令同時做兩件事）

```
ffprobe -v error -show_entries format=duration ... output.mkv; curl -s http://10.46.219.5:8760/health
```

- 音訊長度 **2145.968s ≈ 35m46s**。
- `/health`：`status=ok`、ASR ready（MOSS-Transcribe-Diarize @ 127.0.0.1:8750）、`jobs={}` 無排隊。
- 依技能聲明「轉錄約為音檔長度的 1/4～1/6」估算需 6～9 分鐘 → terminal timeout 設 40 分鐘。

### 4. 執行轉錄

```
python3 .agents/skills/meeting-transcribe/scripts/meeting_transcribe.py output.mkv --out testing.json
```

- 參數取捨：用技能推薦的輔助指令碼（上傳→輪詢→存檔一條命令）；`--out testing.json`
  覆蓋預設的 `<輸入檔>.transcript.json` 命名；其餘用預設（輪詢 20s、整體上限 7200s、
  簡轉繁開啟、不自訂 tau）。
- 上傳 418.4MB → `job_id = 85401caa1954`。
- 進度軌跡：`queued` → `convert` → `transcribe`（66.9% 時 1435s/2146s）→
  `tau_sweep`（100%）→ `speaker_unify`（100%）→ 完成。
- **實際耗時 253.3s（約 4m13s）**，結果：402 segments／2 語者。

### 5. 驗證

用 `python3 -c` 讀回 JSON 驗證關鍵欄位：

| 欄位 | 值 | 判讀 |
|---|---|---|
| `status` | done | 完成 |
| `audio_duration_s` | 2145.954 | 與 ffprobe 2145.968 一致（容差內） |
| `n_segments` | 402 | — |
| `n_speakers` | 2（G01、G02） | 未經人耳驗證 |
| `warnings` | `[]` | 無盲切／無輸出降級 |
| `traditional_applied` | True | 已簡轉繁 |

首段樣本：`start=349.98, end=353.28, speaker=G01, text="今天是2026年7月7號禮拜二"`。

### 6. 觀察與疑點

- **耗時比 1/8.5**，明顯快於 00 條目大檔實測的 1/4.8。可能原因：GPU 當下負載較低、
  或此音檔語音密度較低（開頭 350s 無語音）——未深入查證。
- **前 349.98s 無任何語音段**：第一段從 349.98s 才開始。若該開頭理應有聲音，
  需回頭檢查音軌（影片前段可能是純畫面／音樂）。
- 首段文字自述「今天是2026年7月7號禮拜二」，與音檔 mtime（8月26日）不同——
  這是錄音內容中的口述日期，非檔案後設資料，兩者本就可不一致，僅記錄備查。
- 00 條目驗證用的是 wav／mp3，本次為首次以 `.mkv` 容器輸入，服務端 `convert` 階段
  正常完成解Containers，路徑可用。

## 歸檔決策

- 無新寫程式 → 不走 scripts 歸檔。
- `testing.json`（72,481 bytes）屬「產出的資料檔」→ 依 assets 指引複製到
  `assets/output-mkv-transcript/testing.json`（保留原始檔名與內容，原檔留專案根目錄）。
