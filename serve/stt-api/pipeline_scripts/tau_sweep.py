#!/usr/bin/env python3
"""τ 平台期掃描（自適應 τ，方案 1）：embed 一次、多 τ 凝聚分群、自動選最寬平台期中心。

重用 speaker_unify_v31 的 CampplusEncoder / embed_segment / robust_centroid，
自含 v3.1 的叢集級投票親和度凝聚迴圈（含 margin 記錄）。

輸出：<out_dir>/tau_sweep_report.json
- curve: 每個 τ 的叢集數、合併數、與相鄰 τ 的分區穩定度
- auto_tau: 最寬完全穩定平台期的中心
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import speaker_unify_v31 as v31  # noqa: E402

TAU_GRID = [
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
]


def log(msg: str) -> None:
    import time

    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def cluster_at_tau(centroids, tau: float, delta: float):
    """v3.1 叢集級凝聚合併（複製自 speaker_unify_v31 主迴圈）。"""
    M = len(centroids)
    labels = [f"p{c['part']}{c['spk']}" for c in centroids]
    clusters: list[set[int]] = [{i} for i in range(M)]

    def cluster_centroid(ms: set[int]) -> np.ndarray:
        V = np.array([centroids[i]["emb"] for i in ms])
        c = V.mean(axis=0)
        n = np.linalg.norm(c)
        return c / n if n > 0 else c

    def vote_affinities(cls: list[set[int]]) -> np.ndarray:
        cents = [cluster_centroid(ms) for ms in cls]
        K = len(cls)
        affm = np.zeros((K, K))
        for ci, ms in enumerate(cls):
            vecs = []
            for i in ms:
                c = centroids[i]
                for ki in c["keep"]:
                    dur, v = c["items"][ki]
                    if dur >= v31.MIN_VOTE_S:
                        vecs.append(v)
            if not vecs:
                continue
            parts_own = {centroids[i]["part"] for i in ms}
            targets = [
                cj
                for cj in range(K)
                if cj != ci
                and not ({centroids[i]["part"] for i in cls[cj]} & parts_own)
            ]
            if not targets:
                continue
            TV = np.array([cents[cj] for cj in targets])
            VS = np.array(vecs)
            S = VS @ TV.T
            best_idx = np.argmax(S, axis=1)
            for bi in best_idx:
                affm[ci, targets[bi]] += 1.0 / len(vecs)
        return affm

    merged_log: list[dict] = []
    while True:
        affm = vote_affinities(clusters)
        aff_sym = np.minimum(affm, affm.T)
        K = len(clusters)
        best = None
        for a in range(K):
            for b in range(a + 1, K):
                if {centroids[i]["part"] for i in clusters[a]} & {
                    centroids[i]["part"] for i in clusters[b]
                }:
                    continue
                v = float(aff_sym[a, b])
                if best is None or v > best[0]:
                    best = (v, a, b)
        if best is None or best[0] <= tau:
            break
        v, a, b = best
        alts = [float(aff_sym[a, k]) for k in range(K) if k not in (a, b)] + [
            float(aff_sym[b, k]) for k in range(K) if k not in (a, b)
        ]
        alt = max(alts) if alts else -1.0
        margin = v - alt if alts else 1.0
        la = "+".join(labels[i] for i in sorted(clusters[a]))
        lb = "+".join(labels[i] for i in sorted(clusters[b]))
        clusters[a] |= clusters[b]
        del clusters[b]
        merged_log.append(
            {
                "pair": [la, lb],
                "aff": round(v, 4),
                "alt_aff": round(alt, 4),
                "margin": round(margin, 4),
            }
        )
    return [frozenset(labels[i] for i in c) for c in clusters], merged_log


def partition_pairs(
    clusters: list[frozenset], all_labels: list[str]
) -> set[tuple[str, str]]:
    m: dict[str, int] = {}
    for cid, c in enumerate(clusters):
        for lab in c:
            m[lab] = cid
    pairs = set()
    for i, a in enumerate(all_labels):
        for b in all_labels[i + 1 :]:
            if m[a] == m[b]:
                pairs.add((a, b))
    return pairs


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("base_dir")
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    base = Path(args.base_dir)
    out_dir = Path(args.out_dir) if args.out_dir else base
    out_dir.mkdir(parents=True, exist_ok=True)

    combined = json.loads(
        (base / "transcript_combined.json").read_text(encoding="utf-8")
    )
    groups: dict[tuple[int, str], list[dict]] = {}
    for seg in combined["segments"]:
        groups.setdefault((seg["part"], seg["speaker"]), []).append(seg)
    log(f"載入 {len(combined['segments'])} segments，組數 {len(groups)}")

    model_path = (
        Path(args.model)
        if args.model
        else Path(__file__).resolve().parent.parent
        / "models"
        / "speech_campplus_sv_zh_en_16k-common_advanced.onnx"
    )
    encoder = v31.CampplusEncoder(model_path)
    full = v31.load_full(base / "audio_full.wav")

    seg_list: list[tuple[tuple[int, str], dict, np.ndarray]] = []
    for (part, spk), segs in sorted(groups.items()):
        for s in sorted(segs, key=lambda x: x["start"]):
            v = v31.embed_segment(encoder, full, s["start"], s["end"])
            if v is not None:
                seg_list.append(((part, spk), s, v))
    log(f"逐段 embed 完成：{len(seg_list)} 段")

    by_part: dict[int, list[int]] = {}
    for gi, ((part, _spk), _s, _v) in enumerate(seg_list):
        by_part.setdefault(part, []).append(gi)
    crowd_of_part: dict[int, np.ndarray] = {}
    for part, idxs in by_part.items():
        if len({seg_list[i][0][1] for i in idxs}) < 2:
            continue
        V = np.array([seg_list[i][2] for i in idxs])
        mu = V.mean(axis=0)
        crowd_of_part[part] = mu / max(np.linalg.norm(mu), 1e-9)

    centroids: list[dict] = []
    for (part, spk), _segs in sorted(groups.items()):
        items = [
            (s["end"] - s["start"], v) for (g, s, v) in seg_list if g == (part, spk)
        ]
        if not items:
            continue
        centroid, keep_idx, _n = v31.robust_centroid(
            items, crowd_of_part.get(part), v31.KEEP_FRAC, v31.LAMBDA, v31.ITERS
        )
        centroids.append(
            {
                "part": part,
                "spk": spk,
                "emb": centroid,
                "items": items,
                "keep": keep_idx,
            }
        )
    labels = [f"p{c['part']}{c['spk']}" for c in centroids]
    log(f"centroids：{len(centroids)}")

    # ── 掃描 ──
    curve = []
    prev_pairs: set | None = None
    prev_tau = None
    for tau in TAU_GRID:
        clusters, merged_log = cluster_at_tau(centroids, tau, v31.DELTA)
        pairs = partition_pairs(clusters, labels)
        stab = None
        if prev_pairs is not None:
            stab = 1.0 - len(pairs ^ prev_pairs) / max(1, len(pairs | prev_pairs))
        curve.append(
            {
                "tau": tau,
                "n_clusters": len(clusters),
                "n_merges": len(merged_log),
                "stability_vs_prev": round(stab, 4) if stab is not None else None,
                "min_merge_margin": round(
                    min((m["margin"] for m in merged_log), default=float("nan")), 4
                ),
                "clusters": [sorted(c) for c in clusters],
            }
        )
        log(
            f"τ={tau:.2f} → {len(clusters)} 叢集（合併 {len(merged_log)}，穩定度 {stab}）"
        )
        prev_pairs, prev_tau = pairs, tau

    # ── 最寬完全穩定平台期 → 中心即 auto_tau ──
    runs: list[tuple[int, int]] = []  # (start_idx, end_idx) 內含，相鄰穩定度皆 1.0
    i = 0
    while i < len(curve):
        j = i
        while j + 1 < len(curve) and curve[j + 1]["stability_vs_prev"] == 1.0:
            j += 1
        if j > i:
            runs.append((i, j))
        i = j + 1 if j > i else i + 1
    auto = None
    if runs:
        best_run = max(runs, key=lambda r: r[1] - r[0])
        lo, hi = best_run
        auto = round((curve[lo]["tau"] + curve[hi]["tau"]) / 2, 3)
        log(f"最寬平台期：τ∈[{curve[lo]['tau']},{curve[hi]['tau']}] → auto_tau={auto}")
    else:
        log("無完全穩定平台期（每步分區都變動）")

    report = {
        "version": "tau-sweep-v1",
        "base": str(base),
        "n_centroids": len(centroids),
        "labels": labels,
        "grid": TAU_GRID,
        "curve": curve,
        "plateaus": [
            {
                "tau_lo": curve[lo]["tau"],
                "tau_hi": curve[hi]["tau"],
                "n_clusters": curve[lo]["n_clusters"],
            }
            for lo, hi in runs
        ],
        "auto_tau": auto,
    }
    (out_dir / "tau_sweep_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(f"報告 → {out_dir / 'tau_sweep_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
