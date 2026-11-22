"""F6 Amendment 2d-3: threshold calibrations K1-K3 (research/f6-flagger.md), on validation.

Usage: python examples/f6_calib.py OUT_DIR --class calibrator|target --method M.json
       --shards S --data-root R --sarao-root C --val-run V

For each candidate: the shards' positive-cell recall on its grid, the added cells on each
real validation set (full scan, eligible cells), and tau' by the amendment's rule (largest
pooled recall with added <= T on each set). Per set it reports R3 = added / T against the
bars (lower bound 0.5 min(T, A) / T, upper 1.5, margins 1.1 x lower and 1.35); A is the
scorer's A for the set (V/<set>/A.npy). Writes OUT_DIR/<K>.json and the method files
OUT_DIR/<K>-method.json for the complete scorer. Shard medians run over the labelled cells
(y >= 0), an approximation of the eligible cells recorded in the output.
"""

import argparse
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


f6h = _module("f6_heldout", HERE / "f6_heldout.py")
f6t = _module("f6_tau", HERE / "f6_tau.py")
f5net = _module("f5net", HERE.parent / "python/rang/f5net.py")

GRIDS = {
    "K1": np.arange(-2.0, 12.0001, 0.5),
    "K2": np.arange(0.0, 12.0001, 0.25),
    "K3": np.arange(-2.0, 12.0001, 0.5),
}


def shard_recall(kind, net, shards_dir, grid):
    import torch

    hits = np.zeros(len(grid), np.int64)
    npos = 0
    with torch.no_grad():
        for p in sorted(Path(shards_dir).glob("*.npz")):
            s = np.load(p)
            x, y = s["x"], s["y"]
            scores = []
            for i in range(0, len(x), 16):
                lg = net(torch.from_numpy(np.asarray(x[i : i + 16], np.float32)))
                scores.append(lg.numpy())
            lg = np.concatenate(scores)  # (nsel, nt, nc)
            lab = y >= 0
            nsel = lg.shape[0]
            flat = lg.reshape(nsel * lg.shape[1], -1)
            el = lab.reshape(flat.shape)
            if kind == "K3":
                groups = np.zeros(len(flat), np.int64)
            else:
                groups = np.repeat(np.arange(nsel), lg.shape[1])
            cal = f6h.calibrate(kind, flat, el, groups)
            pos = (y == 1).reshape(flat.shape)
            v = cal[pos]
            hits += np.array([int((v > t).sum()) for t in grid])
            npos += int(pos.sum())
    return hits, npos


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--method", type=Path, required=True)
    p.add_argument("--shards", type=Path, required=True)
    p.add_argument("--data-root", required=True)
    p.add_argument("--sarao-root", required=True)
    p.add_argument("--val-run", type=Path, required=True)
    p.add_argument("--candidates", default="K1,K2,K3")
    a = p.parse_args()
    f5.use_data_root(a.data_root)
    m = json.loads(a.method.read_text())
    w = np.asarray(np.load(m["weights"])["flat"], np.float32)
    nplanes = f5.LEVEL_INPUTS[m["level"]]
    arrays = f5net.arrays_from_flat(w, nplanes, True)
    net = f5net.build(nplanes, True, arrays).eval()
    sets = []
    diags = []
    # T on every set is F5's T on the scan (the scorer's T)
    f6h.SARAO_ROOT = a.sarao_root
    (f4set,) = f5.real_sets(a.klass, "validation")
    specs = [f4set] + [
        f"sarao:{f6t.VALIDATION_BLOCK}:{s}" for s in f6t.SARAO_VALIDATION[a.klass]
    ]
    for spec_ in specs:
        scan = (
            f6h.load_sarao_set(spec_, heldout=False)
            if spec_.startswith("sarao:")
            else f5.load(spec_)
        )
        w3 = f3.w3_flags(scan)
        el = ~w3
        logit = f5.rust_logits(scan, w3, w, m["level"], m["degree"])
        t_add = int((f3.t_flags(scan) & el).sum())
        a_flag = np.load(a.val_run / spec_.replace(":", "-") / "A.npy")
        a_add = int((a_flag & el).sum())
        bl = f3.index(scan)["bl"].astype(np.int64)
        sets.append((spec_, logit, el, bl, t_add, a_add))
        n5 = (logit > m["tau"]) & el  # diagnostic: the frozen method's N5 part, raw tau
        tf = f3.t_flags(scan)
        diag = {
            "set": spec_,
            "T_added": t_add,
            "A_added": a_add,
            "N5_raw_added": int(n5.sum()),
            "N5_raw_also_A": int((n5 & a_flag).sum()),
            "N5_raw_also_T": int((n5 & tf).sum()),
        }
        diags.append(diag)
        print(json.dumps(diag), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "diagnostic.json").write_text(json.dumps(diags, indent=1))
    for kind in a.candidates.split(","):
        grid = GRIDS[kind]
        hits, npos = shard_recall(kind, net, a.shards / a.klass / "validation", grid)
        recall = hits / max(npos, 1)
        per = {}
        for spec_, logit, el, bl, t_add, a_add in sets:
            groups = np.zeros(len(bl), np.int64) if kind == "K3" else bl
            cal = f6h.calibrate(kind, logit, el, groups)
            added = np.array([int(((cal > t) & el).sum()) for t in grid])
            per[spec_] = {"added": added.tolist(), "T": t_add, "A": a_add}
        ok = np.all([np.array(v["added"]) <= v["T"] for v in per.values()], axis=0)
        if ok.any():
            g = int(np.flatnonzero(ok)[np.argmax(recall[ok])])
            rule = "largest recall with added <= T on each set"
        else:
            g = int(
                np.argmin(
                    np.max(
                        [np.array(v["added"]) / max(v["T"], 1) for v in per.values()],
                        axis=0,
                    )
                )
            )
            rule = "none qualifies: smallest worst ratio"
        r3 = {}
        for spec_, v in per.items():
            ratio = v["added"][g] / max(v["T"], 1)
            lower = 0.5 * min(v["T"], v["A"]) / max(v["T"], 1)
            r3[spec_] = {
                "ratio": ratio,
                "lower": lower,
                "pass": lower <= ratio <= 1.5,
                "margin": 1.1 * lower <= ratio <= 1.35,
            }
        res = {
            "candidate": kind,
            "class": a.klass,
            "tau_prime": float(grid[g]),
            "rule": rule,
            "recall": float(recall[g]),
            "positives": npos,
            "grid": grid.tolist(),
            "recall_curve": recall.tolist(),
            "per_set": per,
            "R3": r3,
            "R3_margin_all": all(x["margin"] for x in r3.values()),
            "shard_median": "over labelled cells (y >= 0)",
        }
        (a.out / f"{kind}.json").write_text(json.dumps(res, indent=1))
        meth = {
            k: m[k] for k in ("class", "weights", "weights_sha256", "level", "degree")
        }
        meth |= {
            "tau": float(grid[g]),
            "kappa": None,
            "method": "N5",
            "calibration": kind,
        }
        (a.out / f"{kind}-method.json").write_text(json.dumps(meth, indent=1))
        print(
            json.dumps(
                {
                    "candidate": kind,
                    "tau_prime": float(grid[g]),
                    "recall": float(recall[g]),
                    "R3": {k: round(x["ratio"], 3) for k, x in r3.items()},
                    "margin_all": res["R3_margin_all"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
