"""F6 proposal probe (research/f5-flagger.md, "F6 proposal"): validation only.

Which plane groups move when antennas are dropped, and how much of N5-ph's
G-drop change each group explains. On a validation scan: features of the
full array against the same baselines after dropping k antennas (G-drop's
draws); per group, the share of eligible cells whose plane moves by more
than 0.1 (asinh units), and N5's flag change with that group frozen at its
full-array values.

Usage: python examples/f5_f6_probe.py OUT.json --weights W.npz --tau T [--set luno:MAIN_7]
       [--data-root R] [--k 1] [--seed 20265301]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from rang import f3flag as f3
from rang import f5flag as f5
from rang import f5net

GROUPS = {
    "F3 residuals": range(8),
    "F3 antenna/array medians": range(8, 14),
    "F4 spectral": range(14, 22),
    "2c amplitude blocks": range(22, 28),
    "2d variance blocks": range(28, 32),
    "2c and 2d blocks": range(22, 32),
    # F7 D8 (validation only): the 2c z and Q planes apart, and every plane
    # that pools over baselines at once.
    "2c z": (22, 23, 25, 26),
    "2c Q": (24, 27),
    "all pooled (medians, spectral, blocks)": range(8, 32),
    "all planes": range(32),
}
TAUS = (-5.0, -4.5, -4.0, -3.5, -3.0, -2.5, -2.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--weights", required=True)
    p.add_argument("--tau", type=float, required=True)
    p.add_argument("--set", default="luno:MAIN_7")
    p.add_argument("--data-root")
    p.add_argument("--k", type=int, default=1)
    p.add_argument("--seed", type=int, default=20265301)
    p.add_argument("--nsel", type=int, default=128)
    p.add_argument("--level", type=int, default=0, help="10: F6's per-antenna scale")
    p.add_argument(
        "--sarao-root", help="F7 D2: sets sarao:<cbid>:<scan> (validation only)"
    )
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    if a.set.startswith("sarao:"):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "f6_heldout", Path(__file__).resolve().parent / "f6_heldout.py"
        )
        f6h = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(f6h)
        f6h.SARAO_ROOT = a.sarao_root
        full = f6h.load_sarao_set(a.set, heldout=False)
    else:
        full = f5.load(a.set)
    keep = f5.drop_draw(full, a.k, a.seed)
    sub, _ = f5.subarray(full, keep)
    w3f = f3.w3_flags(full)
    w3s = f3.w3_flags(sub)
    ixf, ixs = f3.index(full), f3.index(sub)
    # The same baselines in both scans, by antenna pair.
    pairs_s = [tuple(x) for x in ixs["ubl"]]
    pos_f = {tuple(x): i for i, x in enumerate(ixf["ubl"])}
    rng = np.random.default_rng(1)
    sel_s = np.sort(rng.choice(len(pairs_s), min(a.nsel, len(pairs_s)), replace=False))
    sel_f = np.array([pos_f[pairs_s[i]] for i in sel_s])
    xf = f5.rust_features(full, w3f, sel_f, a.level, 1)
    xs = f5.rust_features(sub, w3s, sel_s, a.level, 1)
    el = (xf[..., -1] == 0) & (xs[..., -1] == 0)
    flat = np.asarray(np.load(a.weights)["flat"], np.float32)
    net = f5net.build(33, True, f5net.arrays_from_flat(flat, 33, True)).eval()

    def logits(x):
        with torch.no_grad():
            return net(torch.from_numpy(np.ascontiguousarray(x))).numpy()

    def flags(x):
        return logits(x) > a.tau

    lf, ls = logits(xf), logits(xs)
    ff, fs = lf > a.tau, ls > a.tau
    base = int((ff ^ fs)[el].sum())
    nf = int(ff[el].sum())
    rec = {
        "set": a.set,
        "k": a.k,
        "seed": a.seed,
        "baselines": len(sel_s),
        "eligible": int(el.sum()),
        "N5_full_flags": nf,
        "N5_change": base,
        "N5_change_frac": base / max(nf, 1),
        "groups": {},
    }
    # F7 D8: how far from τ the flipped cells sit, how far logits move, and the
    # change fraction at other thresholds on the same logits.
    flip = (ff ^ fs) & el
    dl = np.abs(ls - lf)[el]
    near = np.abs(lf - a.tau)[el] < 1.0
    rec["flipped_margin_quantiles"] = {
        q: float(np.quantile(np.abs(lf - a.tau)[flip], q)) if flip.any() else None
        for q in (0.5, 0.9, 0.99)
    }
    rec["logit_move_median"] = float(np.median(dl))
    rec["logit_move_median_near_tau"] = (
        float(np.median(dl[near])) if near.any() else None
    )
    rec["density_near_tau_per_flag"] = float(near.sum() / max(int(ff[el].sum()), 1))
    rec["tau_sweep"] = {
        str(t): int(((lf > t) ^ (ls > t))[el].sum()) / max(int((lf > t)[el].sum()), 1)
        for t in TAUS
    }
    print(json.dumps({k: rec[k] for k in rec if k not in ("groups",)}), flush=True)
    for name, idx in GROUPS.items():
        idx = list(idx)
        if max(idx) >= xf.shape[-1] - 1:
            continue
        dmax = np.abs(xs[..., idx] - xf[..., idx]).max(-1)
        moved = dmax > 0.1
        x2 = xs.copy()
        x2[..., idx] = xf[..., idx]  # this group frozen at its full-array values
        ch = int((ff ^ flags(x2))[el].sum())
        rec["groups"][name] = {
            "moved_frac": float(moved[el].mean()),
            "moved_frac_05": float((dmax > 0.5)[el].mean()),
            "median_abs_move": float(np.median(dmax[el])),
            "N5_change_if_frozen": ch,
            "N5_change_frac_if_frozen": ch / max(nf, 1),
        }
        print(json.dumps({name: rec["groups"][name]}), flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rec, indent=1))
    print(
        json.dumps(
            {k: rec[k] for k in ("N5_change", "N5_change_frac", "N5_full_flags")}
        )
    )


if __name__ == "__main__":
    main()
