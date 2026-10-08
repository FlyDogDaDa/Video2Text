#!/usr/bin/env python3
"""量測各 part 檔相對於 audio_full.wav 的實際起點偏差。

方法：取 part 檔前 1s 樣本，在 [名義 offset ± 100ms] 內以 1ms 步距滑動，
計算 L2 樣本距離，argmin 即實際起點；同時記錄該處是否 bit-exact（距離 0）。
純標準庫，不修改任何檔案。
"""

from __future__ import annotations

import array
import json
import wave
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PARTS = json.loads((BASE / "audio_parts.json").read_text(encoding="utf-8"))
FULL = BASE / PARTS["audio_full"]
SR = 16000
WIN_S = 1.0  # 比對視窗
SEARCH_S = 0.1  # 搜尋範圍（±）
STEP_S = 0.001  # 1ms 步距


def load(path: Path) -> array.array:
    with wave.open(str(path), "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        assert sw == 2 and sr == SR, f"{path.name}: 預期 16k/s16le，實際 {sr}Hz/{sw}B"
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
        return a[::ch] if ch > 1 else a


def main() -> None:
    full = load(FULL)
    n_full = len(full)
    print(f"audio_full: {n_full} samples = {n_full / SR:.6f}s")
    for i, p in enumerate(PARTS["parts"]):
        part = load(BASE / p["file"])
        nom_s = round(p["offset_s"] * SR)
        win = part[: int(WIN_S * SR)]
        lo = max(0, nom_s - int(SEARCH_S * SR))
        hi = min(n_full - len(win), nom_s + int(SEARCH_S * SR))
        step = int(STEP_S * SR)
        best_off, best_d = None, float("inf")
        for off in range(lo, hi + 1, step):
            d = sum((x - y) ** 2 for x, y in zip(win, full[off : off + len(win)]))
            if d < best_d:
                best_d, best_off = d, off
        nom_d = sum((x - y) ** 2 for x, y in zip(win, full[nom_s : nom_s + len(win)]))
        drift_ms = (best_off - nom_s) / SR * 1000
        exact = "bit-exact" if best_d == 0 else f"L2={best_d}"
        print(
            f"part_{i}: 實際 {len(part)} samples ({len(part) / SR:.6f}s) "
            f"名義起點 {p['offset_s']:.6f}s → 實際起點偏差 {drift_ms:+.0f}ms "
            f"（{exact}；名義處 L2={nom_d}）"
        )


if __name__ == "__main__":
    main()
