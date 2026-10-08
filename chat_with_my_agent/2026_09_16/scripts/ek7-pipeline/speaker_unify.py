#!/usr/bin/env python3
"""步驟 4：語者全域統一（centroid 相似度矩陣 + 段內唯一性約束合併）。

- 每段每 Sxx 一組：取 ≥MIN_SEG_S 的段，從 audio_full.wav 依絕對時間切音，
  resemblyzer 算 embedding，平均成 centroid（L2 正規化）；每組最多 MAX_SEGS 段均勻取樣
- 全部 centroid 兩兩 cosine → M×M 相似度矩陣（自相似矩陣）
- constrained union-find：pair 依相似度降序；sim>τ 且兩叢集不共享同一 part → 合併；
  否則記錄拒絕原因。不變量：每個全域叢集內同一 part 的標籤最多一個
  （chunk→global 單射，擋「一段一人配到另一段兩人」與多跳串連）
- 低邊界審查：合併時若勝出 pair 相對次優替代的 margin < δ → 事後記入
  low_margin_merges 供人工複查（不阻擋合併；阻擋式 top-2 規則在
  cross-person 基線 ~0.8 的 embedding 空間會把所有 pair 全數 flag，已由煙霧測試證實）
- 全域 ID 依首次出場時間排序（G01、G02…）；flag／無 centroid 的組標 U_p{part}_{spk}
- 產出 speaker_unify_report.json（矩陣＋決策日誌＋拒絕/flag 清單），
  並更新 transcript_combined.json（加入 speaker_global 欄）

用法：uv run speaker_unify.py [base_dir] [out_dir]
  base_dir 預設本實驗目錄；out_dir 預設同 base_dir
  （可用舊實驗目錄當 base、另指定 out_dir 做腳本煙霧測試，不動舊資料）
"""

from __future__ import annotations

import array
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

SR = 16000
MIN_SEG_S = 1.0  # 進 centroid 的最短段長
MAX_SEGS = 8  # 每組最多取樣段數（時間軸均勻取樣）
MIN_EMB_S = 0.2  # 靜音修剪後低於此長度放棄該樣本
TAU = 0.90  # 相似度合併門檻（煙霧測試實測：same-person 跨段 ~0.97+、cross-person ~0.77-0.81）
DELTA = 0.05  # 低邊界審查 gap


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_full(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert (
            w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
        ), f"{path.name}: 預期 16k/s16le/mono"
        a = array.array("h")
        a.frombytes(w.readframes(w.getnframes()))
    return np.asarray(a, dtype=np.float32) / 32768.0


def main() -> int:
    base = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent
    )
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else base
    out_dir.mkdir(parents=True, exist_ok=True)

    combined = json.loads(
        (base / "transcript_combined.json").read_text(encoding="utf-8")
    )
    segments = combined["segments"]
    log(f"載入 {len(segments)} segments（{base.name}）")

    # ── 段內分組 ──
    groups: dict[tuple[int, str], list[dict]] = {}
    for seg in segments:
        groups.setdefault((seg["part"], seg["speaker"]), []).append(seg)
    log(f"語者組數：{len(groups)}（parts {sorted({p for p, _ in groups})}）")

    # ── 抽音色 embedding ──
    from resemblyzer import VoiceEncoder, preprocess_wav

    encoder = VoiceEncoder(device="cpu", verbose=False)
    full = load_full(base / "audio_full.wav")

    centroids: list[dict] = []
    no_centroid: list[dict] = []
    for (part, spk), segs in sorted(groups.items()):
        total_s = sum(s["end"] - s["start"] for s in segs)
        qual = sorted(
            (s for s in segs if s["end"] - s["start"] >= MIN_SEG_S),
            key=lambda s: s["start"],
        )
        info = {
            "part": part,
            "spk": spk,
            "n_segments": len(segs),
            "n_qualifying": len(qual),
            "total_speech_s": round(total_s, 2),
        }
        if not qual:
            no_centroid.append({**info, "reason": f"無 ≥{MIN_SEG_S}s 的段"})
            log(f"  p{part} {spk}: {len(segs)} 段皆短於 {MIN_SEG_S}s → 無 centroid")
            continue
        picks = np.round(
            np.linspace(0, len(qual) - 1, min(MAX_SEGS, len(qual)))
        ).astype(int)
        embs = []
        for k in picks:
            s = qual[int(k)]
            wav = full[int(s["start"] * SR) : int(s["end"] * SR)]
            try:
                trimmed = preprocess_wav(wav, source_sr=SR)
            except Exception as e:  # noqa: BLE001
                log(f"  p{part} {spk} 段 {s['start']:.1f}s preprocess 失敗：{e}")
                continue
            if trimmed.size < int(MIN_EMB_S * SR):
                continue
            embs.append(encoder.embed_utterance(trimmed))
        if not embs:
            no_centroid.append({**info, "reason": "embedding 全數失敗"})
            log(f"  p{part} {spk}: embedding 全數失敗 → 無 centroid")
            continue
        c = np.mean(embs, axis=0)
        c /= np.linalg.norm(c)
        centroids.append({**info, "idx": len(centroids), "emb": c, "n_used": len(embs)})
        log(
            f"  p{part} {spk}: {len(segs)} 段（總長 {total_s:.1f}s），"
            f"取樣 {len(embs)} 段算 centroid"
        )

    M = len(centroids)
    labels = [f"p{c['part']}{c['spk']}" for c in centroids]
    log(f"有 centroid 的組數：{M}；無 centroid：{len(no_centroid)}")

    # ── 相似度矩陣 ──
    sim = np.zeros((M, M))
    for i in range(M):
        for j in range(M):
            sim[i, j] = float(np.dot(centroids[i]["emb"], centroids[j]["emb"]))
    print("相似度矩陣：")
    print("      " + " ".join(f"{l:>6}" for l in labels))
    for i in range(M):
        print(f"{labels[i]:>5} " + " ".join(f"{sim[i, j]:6.3f}" for j in range(M)))

    # ── constrained union-find ──
    parent = list(range(M))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    members: dict[int, set[int]] = {i: {i} for i in range(M)}
    merged_log: list[dict] = []
    low_margin_merges: list[dict] = []
    rejected: list[dict] = []
    pairs = sorted(
        ((float(sim[i, j]), i, j) for i in range(M) for j in range(i + 1, M)),
        reverse=True,
    )
    for s, i, j in pairs:
        if s <= TAU:
            break
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        parts_i = {centroids[k]["part"] for k in members[ri]}
        parts_j = {centroids[k]["part"] for k in members[rj]}
        if parts_i & parts_j:
            rejected.append(
                {
                    "pair": [labels[i], labels[j]],
                    "sim": round(s, 4),
                    "reason": "chunk-conflict",
                }
            )
            continue
        # 低邊界審查：勝出 pair 相對「次優替代」（其他叢集、異 part）的 margin
        alts = []
        for endpoint, r_own in ((i, ri), (j, rj)):
            for k in range(M):
                if k == i or k == j:
                    continue
                rk = find(k)
                if rk == ri or rk == rj:
                    continue
                if centroids[k]["part"] == centroids[endpoint]["part"]:
                    continue
                alts.append(float(sim[endpoint, k]))
        alt = max(alts) if alts else -1.0
        margin = s - alt if alts else 1.0
        parent[rj] = ri
        members[ri] |= members[rj]
        del members[rj]
        merged_log.append(
            {
                "pair": [labels[i], labels[j]],
                "sim": round(s, 4),
                "alt_sim": round(alt, 4),
            }
        )
        if margin < DELTA:
            low_margin_merges.append(
                {
                    "pair": [labels[i], labels[j]],
                    "sim": round(s, 4),
                    "alt_sim": round(alt, 4),
                    "margin": round(margin, 4),
                }
            )
            log(
                f"⚠ 低邊界合併：{labels[i]} ↔ {labels[j]}（sim {s:.3f}，"
                f"次優 {alt:.3f}，margin {margin:.3f} < δ）→ 列入複查"
            )
        else:
            log(f"合併：{labels[i]} ↔ {labels[j]}（sim {s:.3f}）")
    for r in rejected:
        log(f"拒絕：{r['pair'][0]} × {r['pair'][1]}（sim {r['sim']}，{r['reason']}）")

    # ── 全域標籤頒布 ──
    resolved = [ms for ms in members.values()]

    def first_app(ms: set[int]) -> float:
        return min(
            s["start"]
            for i in ms
            for s in groups[(centroids[i]["part"], centroids[i]["spk"])]
        )

    resolved.sort(key=first_app)
    group_to_global: dict[tuple[int, str], str] = {}
    for n, ms in enumerate(resolved, 1):
        gid = f"G{n:02d}"
        for i in ms:
            group_to_global[(centroids[i]["part"], centroids[i]["spk"])] = gid
    unresolved_map: dict[tuple[int, str], str] = {}
    for g in no_centroid:
        unresolved_map[(g["part"], g["spk"])] = f"U_p{g['part']}_{g['spk']}"
    group_to_global.update(unresolved_map)

    for seg in segments:
        seg["speaker_global"] = group_to_global.get(
            (seg["part"], seg["speaker"]), f"U_p{seg['part']}_{seg['speaker']}"
        )

    # ── 統計與報告 ──
    stats: dict[str, dict] = {}
    for seg in segments:
        g = seg["speaker_global"]
        st = stats.setdefault(
            g,
            {
                "n_segments": 0,
                "total_speech_s": 0.0,
                "parts": set(),
                "first": 1e9,
                "last": 0.0,
            },
        )
        st["n_segments"] += 1
        st["total_speech_s"] += seg["end"] - seg["start"]
        st["parts"].add(seg["part"])
        st["first"] = min(st["first"], seg["start"])
        st["last"] = max(st["last"], seg["end"])
    for st in stats.values():
        st["total_speech_s"] = round(st["total_speech_s"], 2)
        st["parts"] = sorted(st["parts"])
        st["first"] = round(st["first"], 2)
        st["last"] = round(st["last"], 2)
    log("全域語者統計：")
    for g in sorted(stats):
        st = stats[g]
        log(
            f"  {g}: {st['n_segments']} 段／{st['total_speech_s']}s／"
            f"parts {st['parts']}／{st['first']}~{st['last']}s"
        )

    report = {
        "tau": TAU,
        "delta": DELTA,
        "min_seg_s": MIN_SEG_S,
        "max_segs_per_group": MAX_SEGS,
        "n_groups": len(groups),
        "n_centroids": M,
        "labels": labels,
        "similarity_matrix": [
            [round(float(sim[i, j]), 4) for j in range(M)] for i in range(M)
        ],
        "groups_detail": [
            {k: v for k, v in c.items() if k != "emb"} for c in centroids
        ],
        "low_margin_merges": low_margin_merges,
        "merges": merged_log,
        "rejected": rejected,
        "no_centroid": no_centroid,
        "global_speakers": stats,
        "group_to_global": {f"p{p}_{s}": g for (p, s), g in group_to_global.items()},
    }
    report_path = out_dir / "speaker_unify_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"報告 → {report_path}")

    combined["segments"] = segments
    combined["note"] = (
        combined.get("note", "")
        + "；speaker_global 為全域統一標籤（U_ 開頭=未定案，待人工裁決）"
    )
    combined_path = out_dir / "transcript_combined.json"
    combined_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"更新逐字稿 → {combined_path}")
    log(f"全域語者數：{len(resolved)}＋未定案 {len(unresolved_map)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
