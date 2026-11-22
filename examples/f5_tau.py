"""F5 Stage 4: tau, then kappa and the method, on validation only
(research/f5-flagger.md, sections 3 and 9), on nash. Writes method.json for
Stage 5.

Usage: python examples/f5_tau.py OUT_DIR --class calibrator|target --weights W.npz
       --level L --degree D --flags-from DIR [--data-root R]

Rebuilds every validation realisation as Stage 3 did (same seeds) and picks
the tau with the largest pooled recall of positive cells such that N5's
added cells on the real validation scan's uninjected DATA do not exceed T's;
then kappa, the smallest of 3, 4, 5, 6, 8 with N5 OR W4's added cells there
<= 1.2 x T's (the method is N5W4 at that kappa if P holds, else N5).
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
spec = importlib.util.spec_from_file_location("f5_shards", HERE / "f5_shards.py")
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)

GRID = np.arange(-6.0, 2.0001, 0.5)
P_KINDS_N5W4 = 5  # W3's 2 + weights file + tau + kappa (section 3)
P_KINDS_T = 21


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--weights", required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--degree", type=int, required=True)
    p.add_argument("--flags-from", type=Path, required=True)
    p.add_argument("--data-root")
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    w = np.asarray(np.load(a.weights)["flat"], np.float32)
    hits = np.zeros(len(GRID), np.int64)
    npos = 0
    per = []
    nreal = sh.REALISATIONS["validation"]
    (spec_,) = f5.real_sets(a.klass, "validation")
    scan = f5.load(spec_)
    name = spec_.replace(":", "-")
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    t_flag = np.load(a.flags_from / a.klass / "flags" / f"{name}-T.npy")
    a_flag = np.load(a.flags_from / a.klass / "flags" / f"{name}-A.npy")
    logit, anom = f5.rust_logits_anomaly(scan, w3, w, a.level, a.degree)
    added = np.array([int(((logit > t) & eligible).sum()) for t in GRID])
    t_added = int((t_flag & eligible).sum())
    sigma = f3.baseline_sigma(scan, eligible)
    for k in range(nreal):
        seed = sh.SEEDS[(a.klass, "validation", "real")] + k
        data, flags, lab, _, _ = f5.realise(
            scan, w3, sigma, seed, k % 3 == 2, t_flag, a_flag
        )
        lg = f5.rust_logits(scan, flags, w, a.level, a.degree, data)
        pos = lab == 1
        h = np.array([int((lg[pos] > t).sum()) for t in GRID])
        hits += h
        npos += int(pos.sum())
        per.append({"set": spec_, "seed": seed, "positives": int(pos.sum())})
        print(json.dumps(per[-1]), flush=True)
    for j, s in enumerate(sh.sim_scans(a.klass, "validation")):
        sc = f3.load_fsim(s)
        w3s = f3.w3_flags(sc)
        sig = f3.baseline_sigma(sc, ~w3s)
        seed = sh.SEEDS[(a.klass, "validation", "sim")] + j
        data, flags, lab, _, _ = f5.realise(sc, w3s, sig, seed, j % 3 == 2)
        lg = f5.rust_logits(sc, flags, w, a.level, a.degree, data)
        pos = lab == 1
        hits += np.array([int((lg[pos] > t).sum()) for t in GRID])
        npos += int(pos.sum())
        per.append({"scan": str(s.path), "seed": seed, "positives": int(pos.sum())})
        print(json.dumps(per[-1]), flush=True)
    recall = hits / max(npos, 1)
    ok = added <= t_added
    if ok.any():
        g = int(np.flatnonzero(ok)[np.argmax(recall[ok])])
        rule = "largest recall with added <= T"
    else:
        g = int(np.argmin(added))
        rule = "none qualifies: fewest added"
    tau = float(GRID[g])
    n5 = (logit > tau) & eligible
    kap = {}
    with np.errstate(invalid="ignore"):
        for k in f5.KAPPAS:
            kap[k] = int((n5 | ((anom > k) & eligible)).sum())
    good = [k for k in f5.KAPPAS if kap[k] <= 1.2 * t_added]
    p_holds = P_KINDS_N5W4 < P_KINDS_T / 2
    kappa = min(good) if good and p_holds else None
    res = {
        "class": a.klass,
        "weights": a.weights,
        "weights_sha256": hashlib.sha256(Path(a.weights).read_bytes()).hexdigest(),
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
        "parts": per,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "tau.json").write_text(json.dumps(res, indent=1))
    method = {
        k: res[k]
        for k in (
            "class",
            "weights",
            "weights_sha256",
            "level",
            "degree",
            "tau",
            "kappa",
            "method",
        )
    }
    (a.out / "method.json").write_text(json.dumps(method, indent=1))
    print(
        json.dumps(
            method
            | {"recall": float(recall[g]), "added": int(added[g]), "T_added": t_added}
        )
    )


if __name__ == "__main__":
    main()
