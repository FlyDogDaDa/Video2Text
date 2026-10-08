# tau-sweep 歸檔

## 檔案

- `tau_sweep.py`：τ 平台期掃描工具（v3.1 語者銜接的自適應 τ）

## 用途

v3.1 銜接算法的 τ 原為手調常數。此工具把「選 τ」變成量測：
embed 一次，對 τ 網格各跑一次叢集級凝聚分群，記錄「τ → 叢集數」曲線與
相鄰 τ 分區穩定度，取最寬完全穩定平台期（相鄰穩定度皆 1.0）的中心當 auto_tau。

## 怎麼跑

```bash
# 需求：sherpa-onnx（exp/Ek7qDwwXZ6A/.venv 已有）、numpy、soundfile
# 前置：<base_dir> 內需有 transcript_combined.json、audio_full.wav、models/*.onnx
# tau_sweep.py 需與 speaker_unify_v31.py 同放於 <base>/scripts/
exp/Ek7qDwwXZ6A/.venv/bin/python tau_sweep.py <base_dir> [out_dir]
```

輸出：`<out_dir>/tau_sweep_report.json`（curve、plateaus、auto_tau）

## 實測（2026-09-20）

| 資料 | auto_tau | 最寬平台期 | 定版叢集數 |
|---|---|---|---|
| Meeting20260825（乾淨會議） | 0.225 | [0.10, 0.35]（5 格） | 6 |
| Ek7qDwwXZ6A（污染直播） | 0.2 | [0.10, 0.30]（4 格） | 8 |

## 依賴

- `speaker_unify_v31.py`（同目錄，import 其函式與常數）
- sherpa-onnx、numpy、soundfile
