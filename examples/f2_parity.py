"""F2: Rust kernel against NumPy features + JAX network on an F-SIM observation
(research/f2-flagger.md, section 3: |dlogit| p99.9 <= 1e-4, max <= 1e-3, flag
disagreement <= 1e-5 of cells).

Usage: python examples/f2_parity.py OUT.json OBS_DIR LABEL=W.npz [LABEL=W.npz ...]
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs

sys.path.insert(0, str(Path(__file__).parent))
from f2_measure import load_scan


def main():
    out, obs, *items = sys.argv[1:]
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    result = {}
    for item in items:
        label, path = item.split("=", 1)
        klass = "target" if label.endswith("target") else "calibrator"
        path, _, tau = path.partition("@")
        tau = float(tau) if tau else 0.0
        params = ff.load_params(path)
        w = ff.flat_weights(params)
        diffs, disagree, cells = [], 0, 0
        for s in fs.scans_of(obs, klass):
            scan = load_scan(s)
            shared, _ = ff.run_strategy(scan, ff.shared_strategy(klass))
            rust = ff.rust_logits(
                scan["data"],
                shared,
                scan["antenna1"],
                scan["antenna2"],
                scan["times"],
                w,
            )
            planes = scan["planes"]
            vis = planes.to_planes(scan["data"], 0)
            fl = planes.to_planes(shared, True)
            ref = np.empty(fl.shape, np.float32)
            for b in range(0, planes.nbl, 32):
                x, _ = ff.features(vis[b : b + 32], fl[b : b + 32])
                ref[b : b + 32] = ff.logits_numpy(params, x)
            ref = planes.from_planes(ref)
            keep = ~shared
            d = np.abs(rust - ref)[keep]
            diffs.append(d)
            disagree += int(np.count_nonzero((rust > tau)[keep] != (ref > tau)[keep]))
            cells += int(keep.sum())
        d = np.concatenate(diffs)
        result[label] = {
            "class": klass,
            "tau": tau,
            "cells": cells,
            "p999": float(np.quantile(d, 0.999)),
            "max": float(d.max()),
            "flag_disagreement": disagree / cells,
            "pass": bool(
                np.quantile(d, 0.999) <= 1e-4
                and d.max() <= 1e-3
                and disagree / cells <= 1e-5
            ),
        }
        print(json.dumps({label: result[label]}), flush=True)
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
