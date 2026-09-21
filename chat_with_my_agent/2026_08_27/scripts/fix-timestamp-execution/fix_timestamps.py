#!/usr/bin/env python3
"""對 filtered_aligned.json 套用官方 Qwen3-ForcedAligner 的 fix_timestamp 後處理。

官方 qwen_asr/inference/qwen3_forced_aligner.py 的 parse_timestamp 在配對
start/end 前，會先對整條原始 timestamp 序列跑 fix_timestamp：
- LIS（最長非遞增多項式）標出「正常」值
- 異常段長度 <=2：逐點指派左/右最近正常值的較近側
- 異常段較長：兩側最近正常值線性插值
filter_align.py 直接落檔了 raw argmax，本腳本移植該演算法，把既有數據補整，
不需重跑模型。

用法:
    exp/N9boWvU-KkA/.venv/bin/python exp/N9boWvU-KkA/scripts/fix_timestamps.py

行為:
- 執行前備份原檔至 tmp/filtered_aligned_pre_fix.json
- units[i]: start_s/end_s 換為修補值，原值留 start_s_raw/end_s_raw，
  被修者加 "fixed": true
- word_matches: 依 text_span 對回單位後用修補值重算（原值留 *_raw）
- issues: 依 filter_align.py process_segment 同規則重算
- meta.fix: 記錄方法與統計
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ALIGNED = BASE / "filtered_aligned.json"
BACKUP = BASE / "tmp" / "filtered_aligned_pre_fix.json"


def fix_timestamp(data: list) -> list:
    """逐字移植官方 Qwen3ForceAlignProcessor.fix_timestamp（輸入為 ms 整數）。"""
    data = [int(x) for x in data]
    n = len(data)

    dp = [1] * n
    parent = [-1] * n

    for i in range(1, n):
        for j in range(i):
            if data[j] <= data[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j

    max_length = max(dp)
    max_idx = dp.index(max_length)

    lis_indices = []
    idx = max_idx
    while idx != -1:
        lis_indices.append(idx)
        idx = parent[idx]
    lis_indices.reverse()

    is_normal = [False] * n
    for idx in lis_indices:
        is_normal[idx] = True

    result = data.copy()
    i = 0

    while i < n:
        if not is_normal[i]:
            j = i
            while j < n and not is_normal[j]:
                j += 1

            anomaly_count = j - i

            if anomaly_count <= 2:
                left_val = None
                for k in range(i - 1, -1, -1):
                    if is_normal[k]:
                        left_val = result[k]
                        break

                right_val = None
                for k in range(j, n):
                    if is_normal[k]:
                        right_val = result[k]
                        break

                for k in range(i, j):
                    if left_val is None:
                        result[k] = right_val
                    elif right_val is None:
                        result[k] = left_val
                    else:
                        result[k] = (
                            left_val if (k - (i - 1)) <= ((j) - k) else right_val
                        )

            else:
                left_val = None
                for k in range(i - 1, -1, -1):
                    if is_normal[k]:
                        left_val = result[k]
                        break

                right_val = None
                for k in range(j, n):
                    if is_normal[k]:
                        right_val = result[k]
                        break

                if left_val is not None and right_val is not None:
                    step = (right_val - left_val) / (anomaly_count + 1)
                    for k in range(i, j):
                        result[k] = left_val + step * (k - i + 1)
                elif left_val is not None:
                    for k in range(i, j):
                        result[k] = left_val
                elif right_val is not None:
                    for k in range(i, j):
                        result[k] = right_val

            i = j
        else:
            i += 1

    return [int(res) for res in result]


def split_text_units(text: str) -> list[str]:
    """與 filter_align.py 一致：CJK 單字各一個單位、連續 ASCII 字母數字一個單位。"""
    units: list[str] = []
    buffer: list[str] = []

    def flush_ascii() -> None:
        if buffer:
            units.append("".join(buffer))
            buffer.clear()

    for char in text:
        if "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf":
            flush_ascii()
            units.append(char)
        elif char.isascii() and char.isalnum():
            buffer.append(char)
        else:
            flush_ascii()
    flush_ascii()
    return units


def char_unit_map(text: str) -> list:
    """與 filter_align.py 一致：字元位置 -> 單位索引（不在單位者為 None）。"""
    count = 0
    m: list = [None] * len(text)
    in_ascii = False
    for i, ch in enumerate(text):
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            m[i] = count
            count += 1
            in_ascii = False
        elif ch.isascii() and ch.isalnum():
            if not in_ascii:
                m[i] = count
                count += 1
                in_ascii = True
        else:
            in_ascii = False
    return m


def recompute_issues(seg: dict) -> list[str]:
    """依 filter_align.py process_segment 同規則重算 issues（以修補後值為準）。"""
    abs_base = seg["chunk_abs_start_s"]
    chunk_end = abs_base + seg["chunk_dur_s"]
    issues: list[str] = []
    prev_end = -1e9
    for u in seg["units"]:
        s = u["start_s"]
        e = u["end_s"]
        if e < s:
            issues.append(f"unit '{u['unit']}' end<start ({s}-{e})")
        if s < abs_base - 0.02:
            issues.append(
                f"unit '{u['unit']}' start {s} 早於 chunk 起點 {abs_base:.3f}"
            )
        if e > chunk_end + 0.02:
            issues.append(f"unit '{u['unit']}' end {e} 超出 chunk 尾 {chunk_end:.3f}")
        if s < prev_end - 0.08:
            issues.append(f"unit '{u['unit']}' 非單調（prev_end={prev_end:.3f}）")
        prev_end = max(prev_end, e)
    for wm in seg["word_matches"]:
        ws, we = wm["start_s"], wm["end_s"]
        if we <= ws:
            issues.append(f"詞 '{wm['word']}' 時間區間異常 {ws}-{we}")
    return issues


def main() -> None:
    data = json.loads(ALIGNED.read_text(encoding="utf-8"))
    segments = data["segments"]

    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ALIGNED, BACKUP)
    print(f"備份: {BACKUP}")

    stats = {
        "segments": len(segments),
        "units_total": 0,
        "units_repaired": 0,
        "words_total": 0,
        "words_repaired": 0,
        "segments_affected": 0,
        "issues_before": sum(len(s.get("issues", [])) for s in segments),
        "reversed_words_before": sum(
            1
            for s in segments
            for w in s.get("word_matches", [])
            if w["start_s"] > w["end_s"]
        ),
    }

    for seg in segments:
        units = seg["units"]
        stats["units_total"] += len(units)

        seq_ms = []
        for u in units:
            seq_ms.append(round(u["start_s"] * 1000))
            seq_ms.append(round(u["end_s"] * 1000))
        fixed_ms = fix_timestamp(seq_ms)

        seg_changed = False
        for i, u in enumerate(units):
            old_s, old_e = u["start_s"], u["end_s"]
            new_s = round(fixed_ms[i * 2] / 1000.0, 3)
            new_e = round(fixed_ms[i * 2 + 1] / 1000.0, 3)
            u["start_s_raw"] = old_s
            u["end_s_raw"] = old_e
            if (new_s, new_e) != (old_s, old_e):
                u["fixed"] = True
                stats["units_repaired"] += 1
                seg_changed = True
            else:
                u.pop("fixed", None)
            u["start_s"] = new_s
            u["end_s"] = new_e

        cjk_map = char_unit_map(seg["text"])
        for wm in seg["word_matches"]:
            stats["words_total"] += 1
            a, b = wm["text_span"]
            ui = cjk_map[a]
            uj = cjk_map[b - 1]
            if ui is None or uj is None:
                continue
            old_ws, old_we = wm["start_s"], wm["end_s"]
            new_ws = units[ui]["start_s"]
            new_we = units[uj]["end_s"]
            wm["start_s_raw"] = old_ws
            wm["end_s_raw"] = old_we
            if (new_ws, new_we) != (old_ws, old_we):
                wm["fixed"] = True
                stats["words_repaired"] += 1
                seg_changed = True
            else:
                wm.pop("fixed", None)
            wm["start_s"] = new_ws
            wm["end_s"] = new_we

        seg["issues"] = recompute_issues(seg)
        if seg_changed:
            stats["segments_affected"] += 1

    stats["issues_after"] = sum(len(s.get("issues", [])) for s in segments)
    stats["reversed_words_after"] = sum(
        1
        for s in segments
        for w in s.get("word_matches", [])
        if w["start_s"] > w["end_s"]
    )

    data["meta"]["fix"] = {
        "method": "Qwen3-ForcedAligner 官方 fix_timestamp（LIS 非遞增＋異常段補整）",
        "source": "QwenLM/Qwen3-ASR qwen_asr/inference/qwen3_forced_aligner.py",
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "note": "start_s/end_s 為修補值；模型原始值在 start_s_raw/end_s_raw；fixed=true 表示該值經插值/最近值重建，非模型直接測量",
    }
    data["meta"]["n_segments_with_issues"] = sum(1 for s in segments if s["issues"])

    tmp_out = ALIGNED.with_name(ALIGNED.name + ".tmp")
    tmp_out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_out.rename(ALIGNED)

    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"完成 -> {ALIGNED}")


if __name__ == "__main__":
    main()
