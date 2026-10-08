"""speaker_unify v3 — 段內污染穩健去除版（2026-09-17）。

對 v2 的根本修改（依使用者抽聽結論：top 相似對多為同人，但段內混入他人人聲、
甚至合唱段——污染源是 diarization 段內的交疊人聲，時間修剪無法可視）：

1. 不做時間軸重疊修剪：所有段（含 overlap）全數納入候選池，逐段 embed。
2. crowd 參考向量：每個 part 取「其他所有組段向量」的平均（leave-one-out），
   即「段內所有人聲音的平均」——污染方向估計。僅當該 part 語者組數 ≥2 時可用；
   單人 part 退回只用自身一致性（λ 不適用）。
3. 每組迭代 robust centroid：
   medoid（組內互相相似度總和最大者）→ 純度分數
   score(v) = cos(v, centroid) − λ·cos(v, crowd) → 保留 top keep_frac
   → 截尾平均成新 centroid，迭代 iters 輪。
   小組（<5 個可用段）不過濾、全數保留。
4. constrained union-find（每叢集每 part 至多一組）＋低邊界事後審查，沿 v1/v2。
5. 逐段投票驗證層：僅「保留段」投票，統計一致率與衝突組，不推翻指派。
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

SR = 16000
MIN_SEG_S = 1.0  # 可 embed 的段最短長度
MIN_EMB_S = 0.2
SEG_CAP_S = 10.0  # 單段 embed 音訊上限
GAP_S = 0.15
MIN_VOTE_S = 0.5  # 投票段最短長度
KEEP_FRAC = 0.5  # 每組保留比例（純度分數 top-N%）
LAMBDA = 1.0  # crowd 對比項權重
ITERS = 2  # robust centroid 迭代數
MIN_GROUP_FOR_FILTER = 5  # 可用段少於此數的組不過濾
DEFAULT_TAU = {"campplus": 0.55, "resemblyzer": 0.90}
DELTA = 0.05


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class CampplusEncoder:
    def __init__(self, model_path: Path):
        config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(str(model_path))
        config.provider = "cpu"
        self.ex = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        self.dim = self.ex.dim

    def embed(self, wav: np.ndarray) -> np.ndarray:
        if wav.size < int(MIN_EMB_S * SR):
            raise ValueError("audio too short")
        stream = self.ex.create_stream()
        stream.accept_waveform(SR, wav)
        stream.input_finished()
        v = self.ex.compute(stream)
        v = np.asarray(v, dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v


class ResemblyzerEncoder:
    def __init__(self):
        from resemblyzer import VoiceEncoder, preprocess_wav

        self.enc = VoiceEncoder()
        self.preprocess_wav = preprocess_wav
        self.dim = 256

    def embed(self, wav: np.ndarray) -> np.ndarray:
        v = self.enc.embed_utterance(self.preprocess_wav(wav, source_sr=SR))
        n = np.linalg.norm(v)
        return v / n if n > 0 else v


def load_full(path: Path) -> np.ndarray:
    data, sr = sf.read(path, dtype="float32")
    assert sr == SR, f"取樣率 {sr} != {SR}"
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data


def embed_segment(enc, full: np.ndarray, start: float, end: float) -> np.ndarray | None:
    take = min(end - start, SEG_CAP_S)
    if take < MIN_SEG_S:
        return None
    wav = full[int(start * SR) : int((start + take) * SR)]
    if wav.size < int(MIN_EMB_S * SR):
        return None
    try:
        return enc.embed(wav)
    except Exception:
        return None


def robust_centroid(
    vecs: list[tuple[float, np.ndarray]],
    crowd: np.ndarray | None,
    keep_frac: float,
    lam: float,
    iters: int,
):
    """回傳 (centroid, kept_indices, n_total)。vecs: [(dur, vec)]。"""
    n = len(vecs)
    idx_all = list(range(n))
    keep = list(idx_all)
    centroid = None
    for it in range(iters + 1):
        cur = keep if it > 0 or len(keep) >= MIN_GROUP_FOR_FILTER else idx_all
        V = np.array([vecs[i][1] for i in cur])
        sims = V @ V.T
        medoid_i = int(np.argmax(sims.sum(axis=1)))
        centroid = V[medoid_i]
        if it == iters:
            keep = cur
            break
        k = max(3, int(round(keep_frac * len(cur))))
        if crowd is not None:
            scores = V @ centroid - lam * (V @ crowd)
        else:
            scores = V @ centroid
        order = np.argsort(-scores)
        keep = [cur[i] for i in order[:k]]
    kept = [vecs[i] for i in keep]
    c = np.mean([v for _, v in kept], axis=0)
    nn = np.linalg.norm(c)
    return (c / nn if nn > 0 else c), keep, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_dir", nargs="?", default=None)
    ap.add_argument("out_dir", nargs="?", default=None)
    ap.add_argument(
        "--backend", choices=["campplus", "resemblyzer"], default="campplus"
    )
    ap.add_argument("--model", default=None)
    ap.add_argument("--tau", type=float, default=None)
    ap.add_argument("--delta", type=float, default=DELTA)
    ap.add_argument("--sym", choices=["min", "mean", "max"], default="min")
    ap.add_argument("--keep-frac", type=float, default=KEEP_FRAC)
    ap.add_argument("--lam", type=float, default=LAMBDA)
    ap.add_argument("--iters", type=int, default=ITERS)
    args = ap.parse_args()

    base = (
        Path(args.base_dir) if args.base_dir else Path(__file__).resolve().parent.parent
    )
    out_dir = Path(args.out_dir) if args.out_dir else base
    out_dir.mkdir(parents=True, exist_ok=True)
    tau = args.tau if args.tau is not None else DEFAULT_TAU[args.backend]

    combined = json.loads(
        (base / "transcript_combined.json").read_text(encoding="utf-8")
    )
    segments = combined["segments"]
    log(f"載入 {len(segments)} segments（{base.name}）")

    groups: dict[tuple[int, str], list[dict]] = {}
    for seg in segments:
        groups.setdefault((seg["part"], seg["speaker"]), []).append(seg)
    log(f"語者組數：{len(groups)}（parts {sorted({p for p, _ in groups})}）")

    if args.backend == "campplus":
        model_path = (
            Path(args.model)
            if args.model
            else Path(__file__).resolve().parent.parent
            / "models"
            / "speech_campplus_sv_zh_en_16k-common_advanced.onnx"
        )
        encoder = CampplusEncoder(model_path)
        model_name = model_path.name
    else:
        encoder = ResemblyzerEncoder()
        model_name = "resemblyzer"
    log(f"{args.backend} 後端就緒：{model_name}（dim={encoder.dim}）")

    full = load_full(base / "audio_full.wav")

    # ── 全段 embed（不修剪 overlap）──
    seg_vec: dict[int, np.ndarray] = {}  # id(seg) → vec（以 index 對應）
    seg_list: list[tuple[tuple[int, str], dict, np.ndarray]] = []
    n_fail = 0
    for (part, spk), segs in sorted(groups.items()):
        for s in sorted(segs, key=lambda x: x["start"]):
            v = embed_segment(encoder, full, s["start"], s["end"])
            if v is None:
                n_fail += 1
                continue
            seg_list.append(((part, spk), s, v))
    log(f"逐段 embed 完成：{len(seg_list)} 段成功／{n_fail} 段失敗或過短")

    # ── per-part leave-one-out crowd 參考 ──
    by_part: dict[int, list[int]] = {}
    for gi, ((part, _spk), _s, _v) in enumerate(seg_list):
        by_part.setdefault(part, []).append(gi)
    crowd_of_part: dict[int, np.ndarray] = {}
    for part, idxs in by_part.items():
        n_groups_in_part = len({seg_list[i][0][1] for i in idxs})
        if n_groups_in_part < 2:
            continue  # 單人 part：無 crowd 參考
        V = np.array([seg_list[i][2] for i in idxs])
        crowd_of_part[part] = V.mean(axis=0) / max(np.linalg.norm(V.mean(axis=0)), 1e-9)

    # ── 每組 robust centroid ──
    centroids: list[dict] = []
    no_centroid: list[dict] = []
    group_kept: dict[tuple[int, str], list[int]] = {}
    for (part, spk), segs in sorted(groups.items()):
        total_s = sum(s["end"] - s["start"] for s in segs)
        info = {
            "part": part,
            "spk": spk,
            "n_segments": len(segs),
            "total_speech_s": round(total_s, 2),
        }
        items = [
            (s["end"] - s["start"], v)
            for (p2, s2, v) in [(g, s, v) for (g, s, v) in seg_list]
            if (p2, s2["start"]) == (part, segs[0]["start"]) and False
        ]
        # 直接掃 seg_list 對應此組
        items = [
            (s["end"] - s["start"], v) for (g, s, v) in seg_list if g == (part, spk)
        ]
        if not items:
            no_centroid.append({**info, "reason": "無可 embed 段"})
            continue
        crowd = crowd_of_part.get(part)
        centroid, keep_idx, n_total = robust_centroid(
            items, crowd, args.keep_frac, args.lam, args.iters
        )
        group_kept[(part, spk)] = keep_idx
        info.update(
            {
                "n_emb": n_total,
                "n_kept": len(keep_idx),
                "n_crowd_ref": crowd is not None,
            }
        )
        centroids.append(
            {
                **info,
                "idx": len(centroids),
                "emb": centroid,
                "items": items,
                "keep": keep_idx,
            }
        )
        log(
            f"  p{part} {spk}: {len(segs)} 段，embed {n_total}，保留 {len(keep_idx)}"
            f"（{'有' if crowd is not None else '無'} crowd 參考）"
        )

    labels = [f"p{c['part']}{c['spk']}" for c in centroids]
    M = len(centroids)

    # ── 相似度矩陣（robust centroid）──
    E = np.array([c["emb"] for c in centroids])
    sim = E @ E.T
    print("相似度矩陣（robust centroid）：")
    print("      " + " ".join(f"{l:>6}" for l in labels))
    for i in range(M):
        print(f"{labels[i]:>5} " + " ".join(f"{sim[i, j]:6.3f}" for j in range(M)))

    # ── 投票親和度（v3.1：合併主訊號；保留段對跨 part 其他組 centroid 投票）──
    aff = np.zeros((M, M))
    for i in range(M):
        c = centroids[i]
        cands = [j for j in range(M) if centroids[j]["part"] != c["part"]]
        if not cands or not c.get("keep"):
            continue
        tally: dict[int, int] = {}
        nv = 0
        for ki in c["keep"]:
            dur, v = c["items"][ki]
            if dur < MIN_VOTE_S:
                continue
            sims = [float(np.dot(v, centroids[j]["emb"])) for j in cands]
            best = cands[int(np.argmax(sims))]
            tally[best] = tally.get(best, 0) + 1
            nv += 1
        if nv:
            for j, n in tally.items():
                aff[i, j] = n / nv
    aff_sym = np.minimum(aff, aff.T)
    print("投票親和度矩陣（雙向取 min）：")
    print("      " + " ".join(f"{l:>6}" for l in labels))
    for i in range(M):
        print(f"{labels[i]:>5} " + " ".join(f"{aff_sym[i, j]:6.2f}" for j in range(M)))

    # ── 投票親和度（v3.1：合併主訊號；保留段對跨 part 其他組 centroid 投票）──
    aff = np.zeros((M, M))
    for i in range(M):
        c = centroids[i]
        cands = [j for j in range(M) if centroids[j]["part"] != c["part"]]
        if not cands or not c.get("keep"):
            continue
        tally: dict[int, int] = {}
        nv = 0
        for ki in c["keep"]:
            dur, v = c["items"][ki]
            if dur < MIN_VOTE_S:
                continue
            sims = [float(np.dot(v, centroids[j]["emb"])) for j in cands]
            best = cands[int(np.argmax(sims))]
            tally[best] = tally.get(best, 0) + 1
            nv += 1
        if nv:
            for j, n in tally.items():
                aff[i, j] = n / nv
    aff_sym = np.minimum(aff, aff.T)
    print("投票親和度矩陣（雙向取 min）：")
    print("      " + " ".join(f"{l:>6}" for l in labels))
    for i in range(M):
        print(f"{labels[i]:>5} " + " ".join(f"{aff_sym[i, j]:6.2f}" for j in range(M)))

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
    # ── v3.1：叢集級投票親和度凝聚合併（迭代重投票）──
    clusters: list[set[int]] = [{i} for i in range(M)]
    merged_log: list[dict] = []
    low_margin_merges: list[dict] = []
    rejected: list[dict] = []

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
                    if dur >= MIN_VOTE_S:
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

    while True:
        affm = vote_affinities(clusters)
        if args.sym == "min":
            aff_sym = np.minimum(affm, affm.T)
        elif args.sym == "mean":
            aff_sym = (affm + affm.T) / 2
        else:
            aff_sym = np.maximum(affm, affm.T)
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
        entry = {
            "pair": [la, lb],
            "aff": round(v, 4),
            "alt_aff": round(alt, 4),
            "margin": round(margin, 4),
        }
        merged_log.append(entry)
        if margin < args.delta:
            low_margin_merges.append(entry)
            log(
                f"⚠ 低邊界合併：{la} ↔ {lb}（aff {v:.2f}，次優 {alt:.2f}，margin {margin:.2f} < δ）→ 列入複查"
            )
        else:
            log(f"合併：{la} ↔ {lb}（aff {v:.2f}）")
    members = {next(iter(c)): c for c in clusters}

    # ── 全域標籤頒布 ──
    resolved = list(members.values())

    def first_app(ms: set[int]) -> float:
        return min(
            seg_list[ci][1]["start"]
            for ci in ms
            for ci2 in [centroids[ci]["keep"][0]]
            if centroids[ci]["keep"]
        )

    def first_app2(ms: set[int]) -> float:
        best = None
        for ci in ms:
            c = centroids[ci]
            gkey = (c["part"], c["spk"])
            starts = [s["start"] for (g, s, _v) in seg_list if g == gkey]
            if starts:
                m = min(starts)
                best = m if best is None else min(best, m)
        return best if best is not None else 1e18

    resolved.sort(key=first_app2)
    group_to_global: dict[tuple[int, str], str] = {}
    for n, ms in enumerate(resolved, 1):
        gid = f"G{n:02d}"
        for i in ms:
            group_to_global[(centroids[i]["part"], centroids[i]["spk"])] = gid
    unresolved_map: dict[tuple[int, str], str] = {}
    for g in no_centroid:
        unresolved_map[(g["part"], g["spk"])] = f"U_p{g['part']}_{g['spk']}"
    group_to_global.update(unresolved_map)

    # ── 逐段投票（僅保留段）──
    vote_conflicts: list[dict] = []
    vote_total = 0
    vote_agree_total = 0
    per_group_vote: dict[str, dict] = {}
    for c in centroids:
        gkey = (c["part"], c["spk"])
        own_gid = group_to_global[gkey]
        cands = [j for j in range(M) if centroids[j]["part"] != c["part"]]
        if not cands or not c["keep"]:
            continue
        votes: list[int] = []
        for ki in c["keep"]:
            dur, v = c["items"][ki]
            if dur < MIN_VOTE_S:
                continue
            sims = [
                float(sim[c["idx"], j]) for j in cands
            ]  # 以組向量相似度近似逐段投票目標
            # 逐段向量對跨組 centroid 投票（較精確）
            sims = [float(np.dot(v, centroids[j]["emb"])) for j in cands]
            best = cands[int(np.argmax(sims))]
            votes.append(
                group_to_global[(centroids[best]["part"], centroids[best]["spk"])]
            )
        if not votes:
            continue
        tally: dict[str, int] = {}
        for g in votes:
            tally[g] = tally.get(g, 0) + 1
        majority, mcount = max(tally.items(), key=lambda kv: kv[1])
        agree = tally.get(own_gid, 0)
        vote_total += len(votes)
        vote_agree_total += agree
        agreement = round(agree / len(votes), 4)
        per_group_vote[f"p{c['part']}{c['spk']}"] = {
            "n_votes": len(votes),
            "tally": tally,
            "majority": majority,
            "agreement": agreement,
        }
        if majority != own_gid:
            vote_conflicts.append(
                {
                    "group": f"p{c['part']}{c['spk']}",
                    "own": own_gid,
                    "vote_majority": majority,
                    "tally": tally,
                }
            )
            log(
                f"⚠ 投票衝突：p{c['part']} {c['spk']} 屬 {own_gid}，但投票多數指向 {majority}（{tally}）→ 列入複查"
            )

    if vote_total:
        log(
            f"投票總覽：{vote_total} 票，整體一致率 {vote_agree_total / vote_total:.3f}，衝突組 {len(vote_conflicts)}"
        )
    else:
        log("投票總覽：0 票")

    # ── 統計與輸出 ──
    global_speakers: dict[str, dict] = {}
    for (part, spk), gid in group_to_global.items():
        g = global_speakers.setdefault(
            gid, {"n_segments": 0, "total_speech_s": 0.0, "parts": []}
        )
        gsegs = groups.get((part, spk), [])
        g["n_segments"] += len(gsegs)
        g["total_speech_s"] += sum(s["end"] - s["start"] for s in gsegs)
        if part not in g["parts"]:
            g["parts"].append(part)
    for gid, g in global_speakers.items():
        starts = [
            s["start"]
            for (p2, s2) in groups.items()
            if (p2[0], p2[1]) and group_to_global.get(p2) == gid
            for s in s2
        ]
        ends = [
            s["end"]
            for (p2, s2) in groups.items()
            if group_to_global.get(p2) == gid
            for s in s2
        ]
        g["total_speech_s"] = round(g["total_speech_s"], 2)
        g["parts"] = sorted(g["parts"])
        g["first"] = round(min(starts), 2) if starts else None
        g["last"] = round(max(ends), 2) if ends else None
    for gid in sorted(global_speakers):
        g = global_speakers[gid]
        log(
            f"  {gid}: {g['n_segments']} 段／{g['total_speech_s']}s／parts {g['parts']}／{g['first']}~{g['last']}s"
        )

    # 更新逐字稿 speaker_global
    for s in combined["segments"]:
        s["speaker_global"] = group_to_global.get(
            (s["part"], s["speaker"]), f"U_p{s['part']}_{s['speaker']}"
        )
    combined_path = out_dir / "transcript_combined.json"
    combined_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    report = {
        "version": "v3.1-vote-affinity",
        "backend": args.backend,
        "model": model_name,
        "tau": tau,
        "delta": args.delta,
        "keep_frac": args.keep_frac,
        "lambda": args.lam,
        "iters": args.iters,
        "min_seg_s": MIN_SEG_S,
        "n_groups": len(groups),
        "n_centroids": M,
        "n_embed_fail": n_fail,
        "labels": labels,
        "similarity_matrix": sim.tolist(),
        "vote_affinity_matrix": aff_sym.tolist(),
        "groups_detail": [
            {k: v for k, v in c.items() if k not in ("emb", "items", "keep")}
            for c in centroids
        ],
        "low_margin_merges": low_margin_merges,
        "merges": merged_log,
        "rejected": rejected,
        "no_centroid": no_centroid,
        "global_speakers": global_speakers,
        "group_to_global": {f"p{p}_{s}": g for (p, s), g in group_to_global.items()},
        "voting": {
            "min_vote_s": MIN_VOTE_S,
            "n_voted_segments": vote_total,
            "overall_agreement": round(vote_agree_total / vote_total, 4)
            if vote_total
            else None,
            "n_conflict_groups": len(vote_conflicts),
            "conflicts": vote_conflicts,
            "groups": per_group_vote,
        },
    }
    (out_dir / "speaker_unify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(f"報告 → {out_dir / 'speaker_unify_report.json'}")
    log(f"更新逐字稿 → {combined_path}")
    log(
        f"全域語者數：{sum(1 for g in global_speakers if g.startswith('G'))}＋未定案 {sum(1 for g in global_speakers if g.startswith('U_'))}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
