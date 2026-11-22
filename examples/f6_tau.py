"""F6 Stage 4: the seed, tau and kappa on validation only (research/f6-flagger.md 2d,
Amendment 2d-1; F5's rule, examples/f5_tau.py), on nash. Writes method.json.

Usage: python examples/f6_tau.py OUT_DIR --class calibrator|target --train-dir D
       --shards S --level 20 --degree 1 --flags-from DIR --data-root R --sarao-root C

Seed: the median of seeds 1, 2, 3 by validation loss (each seed's weights.npz header).
Recall: positive cells of every validation shard (F6's realisations: dropout, hybrid
positives, SARAO scans), logits of the network on the shard's per-baseline planes
(exact: the network is per baseline in time and frequency). tau: the largest pooled
recall such that the network's added cells, summed over the real validation scans'
uninjected DATA (LUNO MAIN_7 or ESO137 chunk 10, and 1573212012's scored scans cut as
in training), do not exceed T's; kappa as F5 (smallest of f5.KAPPAS with N5 OR W4 <=
1.2 x T's added cells there, if P holds).
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from rang import f5flag as f5

HERE = Path(__file__).resolve().parent


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


f5s = _module("f5_shards", HERE / "f5_shards.py")
f5t = _module("f5_tau", HERE / "f5_tau.py")
f6h = _module("f6_heldout", HERE / "f6_heldout.py")
f5net = _module("f5net", HERE.parent / "python/rang/f5net.py")

GRID = f5t.GRID
SARAO_VALIDATION = {"calibrator": (1, 3, 5), "target": (111, 113, 115)}
VALIDATION_BLOCK = "1573212012"


def median_seed(train_dir):
    vl = {}
    for d in sorted(Path(train_dir).glob("seed-*")):
        z = np.load(d / "weights.npz")
        vl[d.name] = float(json.loads(str(z["header"]))["validation_loss"])
    order = sorted(vl, key=lambda k: (vl[k], k))
    return order[len(order) // 2], vl


def shard_hits(weights, nplanes, shards_dir):
    import torch

    z = np.load(weights)
    arrays = f5net.arrays_from_flat(np.asarray(z["flat"], np.float32), nplanes, True)
    net = f5net.build(nplanes, True, arrays).eval()
    hits = np.zeros(len(GRID), np.int64)
    npos = 0
    parts = []
    with torch.no_grad():
        for p in sorted(Path(shards_dir).glob("*.npz")):
            s = np.load(p)
            x, y = s["x"], s["y"]
            h = np.zeros(len(GRID), np.int64)
            n = 0
            for i in range(0, len(x), 16):
                lg = net(torch.from_numpy(np.asarray(x[i : i + 16], np.float32)))
                lg = lg.numpy()
                pos = y[i : i + 16] == 1
                v = lg[pos]
                h += np.array([int((v > t).sum()) for t in GRID])
                n += int(pos.sum())
            hits += h
            npos += n
            parts.append({"shard": p.name, "positives": n})
    return hits, npos, parts


def real_scans(klass, sarao_root, flags_from):
    """(name, scan, T added-cell flags) of the real validation scans."""
    (spec_,) = f5.real_sets(klass, "validation")
    scan = f5.load(spec_)
    name = spec_.replace(":", "-")
    t_flag = np.load(flags_from / klass / "flags" / f"{name}-T.npy")
    yield spec_, scan, t_flag
    f6h.SARAO_ROOT = sarao_root
    for s in SARAO_VALIDATION[klass]:
        spec_ = f"sarao:{VALIDATION_BLOCK}:{s}"
        sc = f6h.load_sarao_set(spec_, heldout=False)
        yield spec_, sc, f3.t_flags(sc)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--train-dir", type=Path, required=True)
    p.add_argument("--shards", type=Path, required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--degree", type=int, required=True)
    p.add_argument("--flags-from", type=Path, required=True)
    p.add_argument("--data-root")
    p.add_argument("--sarao-root", required=True)
    p.add_argument("--seed", help="a seed directory (seed-k) instead of the median")
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    seed, vl = median_seed(a.train_dir)
    median = seed
    if a.seed:
        seed = a.seed
    weights = a.train_dir / seed / "weights.npz"
    nplanes = f5.LEVEL_INPUTS[a.level]
    w = np.asarray(np.load(weights)["flat"], np.float32)
    hits, npos, parts = shard_hits(weights, nplanes, a.shards / a.klass / "validation")
    added = np.zeros(len(GRID), np.int64)
    t_added = 0
    logits = []
    for spec_, scan, t_flag in real_scans(a.klass, a.sarao_root, a.flags_from):
        w3 = f3.w3_flags(scan)
        el = ~w3
        logit, anom = f5.rust_logits_anomaly(scan, w3, w, a.level, a.degree)
        added += np.array([int(((logit > t) & el).sum()) for t in GRID])
        ta = int((t_flag & el).sum())
        t_added += ta
        logits.append((spec_, logit, anom, el))
        parts.append({"set": spec_, "T_added": ta})
        print(json.dumps(parts[-1]), flush=True)
    recall = hits / max(npos, 1)
    ok = added <= t_added
    if ok.any():
        g = int(np.flatnonzero(ok)[np.argmax(recall[ok])])
        rule = "largest recall with added <= T"
    else:
        g = int(np.argmin(added))
        rule = "none qualifies: fewest added"
    tau = float(GRID[g])
    kap = {}
    with np.errstate(invalid="ignore"):
        for k in f5.KAPPAS:
            kap[k] = sum(
                int((((lg > tau) | (an > k)) & el).sum()) for _, lg, an, el in logits
            )
    good = [k for k in f5.KAPPAS if kap[k] <= 1.2 * t_added]
    p_holds = f5t.P_KINDS_N5W4 < f5t.P_KINDS_T / 2
    kappa = min(good) if good and p_holds else None
    res = {
        "class": a.klass,
        "seed": seed,
        "median_seed": median,
        "validation_loss": vl,
        "weights": str(weights),
        "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "level": a.level,
        "degree": a.degree,
        "grid": GRID.tolist(),
        "recall": recall.tolist(),
        "added": added.tolist(),
        "T_added": t_added,
        "positives": npos,
        "tau": tau,
        "tau_rule": rule,
        "kappa_added": {str(k): v for k, v in kap.items()},
        "kappa": kappa,
        "method": "N5W4" if kappa is not None else "N5",
        "parts": parts,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "tau.json").write_text(json.dumps(res, indent=1))
    keys = ("class", "weights", "weights_sha256", "level", "degree", "tau", "kappa")
    method = {k: res[k] for k in keys} | {"method": res["method"], "seed": seed}
    (a.out / "method.json").write_text(json.dumps(method, indent=1))
    print(json.dumps(method | {"recall": float(recall[g]), "added": int(added[g])}))


if __name__ == "__main__":
    main()
