# References：AV1 MKV 全量重產實測資料（2026-08-31）

## 試片矩陣（clip_0001：start 412.870s，dur 0.320s）

| 路線 | 容器 | 結果 | 單片耗時 | 大小 |
|---|---|---|---|---|
| av1_nvenc（GPU） | mp4 | ❌ `cuCtxCreate` OOM（序列也失敗，sglang 佔 114 GiB） | — | — |
| libsvtav1（CPU） | mp4 | ✅ 規格正確，但 **Resolve 黑幀** | 27.7s（實測單跑） | 336 KB |
| libx264（CPU） | mp4 | ✅（對照用，0.93s） | 0.93s | 303 KB |
| libsvtav1（CPU） | **mkv** | ✅ **Resolve 可讀、有聲、無黑幀（使用者目檢）** | 6.7s（20 緒全開） | 328 KB |

- `-c copy` 對照（同一視窗）：輸出 5.2s/156 幀＝整段 GOP，證明必須重編碼
  （呼應 08-27 log 04 keyframe GOP 實測）。
- SVT-AV1 v1.7.0，main profile 1080p30，CRF 24 / preset 5 / GOP 161。

## log 00 教訓（彙整）

1. **GPU 不可用**：「GPU util 0%」≠「視訊記憶體可用」；GB10 統一記憶體被 sglang
   `--mem-fraction-static 0.97` 佔死，NVENC 多 context 必 OOM，單 context 序列也
   在 10:2x 後開始失敗（free 僅 ~1 GiB）。CPU 是唯一路線。
2. **外部刪檔事件**：10:55–11:15 間 `clips_mp4/` 完成檔被持續清除；直接旁證是
   11 個切片失敗訊息 `Error opening output ...`（ffmpeg 開檔瞬間路徑已不存在）。
   指令碼無刪除邏輯（grep `unlink|rmtree` 無匹配）、資源筒為空、home 內找不到移入
   痕跡、無同步常駐。來源未確認（已問過使用者）。迴避策略：換輸出目錄。
3. **verify 是必需防線**：log 00 那輪若只看切片成功數（412/423）會誤判完成，
   verify 立刻揭發 392 MISSING。

## 打包決策

- 推薦 **zip**：媒體檔（AV1/AAC）熵已近極限，任何壓縮器省下 <3%；zip 為
  Windows//macOS/Linux 原生可解，使用者下載後零依賴。7z 僅在要省傳輸量時值得。
- 打包內容：`clips_mkv/*.mkv`＋`clips_mkv_manifest.json`。
