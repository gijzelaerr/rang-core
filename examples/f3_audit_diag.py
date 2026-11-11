"""F3 label-audit diagnosis (research/f3-flagger.md, Amendment 1): are the weak
consensus cells (T and A both flag, max(u) < 3) neighbours of strong ones
(flag extension), or isolated (RFI the features cannot see)?

Usage: python examples/f3_audit_diag.py OUT.json --shards SHARDS_RUN --set eso:2 [--set ...]
Uninjected DATA of training scans only; 256 baselines per set (seed 7).
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from rang import f3flag as f3
from scipy.ndimage import binary_dilation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--set", action="append", required=True)
    args = parser.parse_args()
    out = (
        Path(os.environ["RUN_DIR"]) / args.out[4:]
        if args.out.startswith("RUN/")
        else Path(args.out)
    )
    res = {}
    for spec in args.set:
        kind, _, name = spec.partition(":")
        scan = f3.load_luno(name) if kind == "luno" else f3.load_eso(int(name))
        klass = scan["klass"]
        tag = spec.replace(":", "-")
        t = np.load(args.shards / klass / "flags" / f"{tag}-T.npy")
        a = np.load(args.shards / klass / "flags" / f"{tag}-A.npy")
        w3 = f3.w3_flags(scan)
        ix = f3.index(scan)
        rng = np.random.default_rng(7)
        live = np.unique(ix["bl"][(~w3).any(1)])
        sel = np.sort(rng.choice(live, min(256, len(live)), replace=False))
        x = f3.rust_features(scan, w3, sel)
        u = np.sinh(x[..., :8].max(-1))
        pos = np.full(len(ix["ubl"]), -1)
        pos[sel] = np.arange(len(sel))
        rows = np.flatnonzero(pos[ix["bl"]] >= 0)
        cons = np.zeros(u.shape, bool)
        cons[pos[ix["bl"][rows]], ix["t"][rows]] = (t & a & ~w3)[rows]
        strong = cons & (u >= 3)
        weak = cons & (u < 3)
        s = np.zeros((1, 7, 7), bool)
        s[0] = True
        near = binary_dilation(strong, s)
        nc = u.shape[-1]
        weak_far = weak & ~near
        by_ch = weak_far.sum((0, 1))
        res[spec] = {
            "consensus": int(cons.sum()),
            "strong": int(strong.sum()),
            "weak": int(weak.sum()),
            "weak_within_3": int((weak & near).sum()),
            "weak_within_3_fraction": float((weak & near).sum() / max(weak.sum(), 1)),
            "median_u_consensus": float(np.median(u[cons])) if cons.any() else None,
            "weak_isolated_by_64ch": [
                int(by_ch[i : i + 64].sum()) for i in range(0, nc, 64)
            ],
            "frequency_mhz_edges": [
                float(scan["chan_freq"][i] / 1e6) for i in range(0, nc, 64)
            ],
        }
        print(json.dumps(res[spec]), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
