"""F3 Stage 4: the threshold tau on validation (research/f3-flagger.md, section 5),
and the validation numbers of a weights file.

Usage: python examples/f3_tau.py OUT.json --class calibrator|target --shards SHARDS_RUN --n3 W.npz

Rebuilds every validation realisation exactly as Stage 3 did (same seeds),
runs the Rust kernel on the whole scans, and picks the tau with the largest
pooled recall of positive cells such that N3's added cells on the real
validation scans' uninjected DATA do not exceed T's.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from rang import f3net

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f3_shards", HERE / "f3_shards.py")
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)

GRID = np.arange(-4.0, 2.0001, 0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--class", dest="klass", required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--n3", required=True)
    parser.add_argument("--labels", choices=("frozen", "amend1"), default="amend1")
    args = parser.parse_args()
    out = (
        Path(os.environ["RUN_DIR"]) / args.out[4:]
        if args.out.startswith("RUN/")
        else Path(args.out)
    )
    weights = f3net.flat_weights(f3net.load_params(args.n3))
    hits = np.zeros(len(GRID), np.int64)
    npos = 0
    added = np.zeros(len(GRID), np.int64)
    t_added = 0
    per = []
    nreal = sh.REALISATIONS["validation"]
    for i, spec_ in enumerate(sh.real_sets(args.klass, "validation")):
        scan = sh.load(spec_)
        name = spec_.replace(":", "-")
        w3 = f3.w3_flags(scan)
        eligible = ~w3
        t_flag = np.load(args.shards / args.klass / "flags" / f"{name}-T.npy")
        a_flag = np.load(args.shards / args.klass / "flags" / f"{name}-A.npy")
        logit = f3.rust_logits(scan, w3, weights)
        for g, tau in enumerate(GRID):
            added[g] += int(((logit > tau) & eligible).sum())
        t_added += int((t_flag & eligible).sum())
        sigma = f3.baseline_sigma(scan, eligible)
        strong = f3.u_rows(scan, w3) >= 3 if args.labels == "amend1" else None
        for k in range(nreal):
            seed = sh.SEEDS[(args.klass, "validation", "real")] + nreal * i + k
            data, flags, lab, _, _ = f3.realise(
                scan, w3, sigma, seed, k % 3 == 2, t_flag, a_flag, strong
            )
            lg = f3.rust_logits(scan, flags, weights, data)
            pos = lab == 1
            h = np.array([int((lg[pos] > tau).sum()) for tau in GRID])
            hits += h
            npos += int(pos.sum())
            per.append(
                {
                    "set": spec_,
                    "seed": seed,
                    "positives": int(pos.sum()),
                    "recall_at_0": float(h[GRID == 0][0] / max(pos.sum(), 1)),
                }
            )
            print(json.dumps(per[-1]), flush=True)
    for j, s in enumerate(sh.sim_scans(args.klass, "validation")):
        scan = f3.load_fsim(s)
        w3 = f3.w3_flags(scan)
        sigma = f3.baseline_sigma(scan, ~w3)
        seed = sh.SEEDS[(args.klass, "validation", "sim")] + j
        data, flags, lab, _, _ = f3.realise(scan, w3, sigma, seed, j % 3 == 2)
        lg = f3.rust_logits(scan, flags, weights, data)
        pos = lab == 1
        h = np.array([int((lg[pos] > tau).sum()) for tau in GRID])
        hits += h
        npos += int(pos.sum())
        per.append(
            {
                "scan": str(s.path),
                "seed": seed,
                "positives": int(pos.sum()),
                "recall_at_0": float(h[GRID == 0][0] / max(pos.sum(), 1)),
            }
        )
        print(json.dumps(per[-1]), flush=True)
    recall = hits / max(npos, 1)
    ok = added <= t_added
    if ok.any():
        g = int(np.flatnonzero(ok)[np.argmax(recall[ok])])
        rule = "largest recall with added <= T"
    else:
        g = int(np.argmin(added))
        rule = "none qualifies: fewest added"
    result = {
        "class": args.klass,
        "n3": args.n3,
        "grid": GRID.tolist(),
        "recall": recall.tolist(),
        "added": added.tolist(),
        "T_added": t_added,
        "positives": npos,
        "tau": float(GRID[g]),
        "rule": rule,
        "parts": per,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(
        json.dumps(
            {k: result[k] for k in ("tau", "rule", "T_added")}
            | {"recall": round(float(recall[g]), 4), "added": int(added[g])}
        )
    )


if __name__ == "__main__":
    main()
