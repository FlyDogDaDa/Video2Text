#!/usr/bin/env python3
"""量測 audio_part_N.wav 實際內容起點相對於 audio_full.wav 名義 offset 的偏差 δ。

方法：取 part N 前 20ms，在 audio_full 名義 offset ±0.1s 視窗內找最佳樣本位移 s；
s=0 且得分低 → 切點精確（δ≈0）；s 顯不等 0 → 該 part 的內容起點偏移了 s 個樣本。
純標準庫（wave + struct），無依賴。

用法:
    exp/N9boWvU-KkA/.venv/bin/python check_part_starts.py
"""

import struct
import wave

BASE = "exp/N9boWvU-KkA/"
FULL = BASE + "audio_full.wav"
PARTS = [
    (BASE + "audio_part_0.wav", 0.0),
    (BASE + "audio_part_1.wav", 1416.753922),
    (BASE + "audio_part_2.wav", 2833.507844),
    (BASE + "audio_part_3.wav", 4250.261766),
]
SR = 16000
MATCH_SAMPLES = 320  # 20ms 對齊視窗
SCAN_HALF = 1600  # ±0.1s


def read_window(path: str, start_pos: int, n: int):
    with wave.open(path, "rb") as w:
        assert (
            w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
        ), f"{path}: {w.getnchannels()}ch {w.getsampwidth()}B {w.getframerate()}Hz"
        w.setpos(start_pos)
        raw = w.readframes(n)
    return struct.unpack(f"<{n}h", raw)


def main() -> None:
    for part_path, offset in PARTS:
        off_idx = int(round(offset * SR))
        lo = max(0, off_idx - SCAN_HALF)
        read_n = (off_idx + SCAN_HALF + MATCH_SAMPLES) - lo
        full_win = read_window(FULL, lo, read_n)
        part_head = read_window(part_path, 0, MATCH_SAMPLES)

        best_shift, best_score = None, None
        for s in range(lo - off_idx, SCAN_HALF + 1):
            base = off_idx + s - lo
            seg = full_win[base : base + MATCH_SAMPLES]
            score = sum(abs(a - b) for a, b in zip(part_head, seg))
            if best_score is None or score < best_score:
                best_score, best_shift = score, s
        base0 = off_idx - lo
        score0 = sum(
            abs(a - b)
            for a, b in zip(part_head, full_win[base0 : base0 + MATCH_SAMPLES])
        )
        print(
            f"offset {offset:>10.6f}s: best shift = {best_shift:+6d} samples "
            f"({best_shift / SR * 1000:+7.1f} ms)  score {best_score:>10d} | score@0 {score0:>10d}"
        )


if __name__ == "__main__":
    main()
