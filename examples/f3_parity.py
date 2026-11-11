"""F3 Stage 2 parity (research/f3-flagger.md, section 3): Rust features
against the NumPy reference, and Rust logits against the JAX network on the
same features, on one validation scan.

Usage: python examples/f3_parity.py OUT.json --set eso:10|luno:MAIN_7|fsim [--n3 W.npz]
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f3net


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--set", required=True)
    parser.add_argument("--n3")
    args = parser.parse_args()
    out = (
        Path(os.environ["RUN_DIR"]) / args.out[4:]
        if args.out.startswith("RUN/")
        else Path(args.out)
    )
    if args.set == "fsim":
        scan = f3.load_fsim(fs.scans_of(f3.F2_VAL, "calibrator")[0])
    else:
        kind, _, name = args.set.partition(":")
        scan = f3.load_luno(name) if kind == "luno" else f3.load_eso(int(name))
    params = f3net.load_params(args.n3) if args.n3 else f3net.init_params(0)
    weights = f3net.flat_weights(params)
    w3 = f3.w3_flags(scan)
    ix = f3.index(scan)
    nbl = len(ix["ubl"])
    allb = np.arange(nbl)
    t = time.perf_counter()
    xr = f3.rust_features(scan, w3, allb)
    tr = time.perf_counter() - t
    t = time.perf_counter()
    xn = f3.features_numpy(scan, w3, allb)
    tn = time.perf_counter() - t
    dfeat = float(np.abs(xr - xn).max())
    import jax

    fwd = jax.jit(f3net.forward)
    zj = np.empty(xr.shape[:3], np.float32)
    for s in range(0, nbl, 32):
        zj[s : s + 32] = np.asarray(fwd(params, xr[s : s + 32]))
    zr_rows = f3.rust_logits(scan, w3, weights)
    zj_rows = zj[ix["bl"], ix["t"]]
    keep = ~w3
    d = np.abs(zr_rows - zj_rows)[keep]
    res = {
        "set": args.set,
        "weights": args.n3 or "U3 (init seed 0)",
        "cells": int(keep.sum()),
        "feature_max_abs": dfeat,
        "feature_bound": 1e-4,
        "logit_p999": float(np.quantile(d, 0.999)),
        "logit_max": float(d.max()),
        "flag_disagreement": float(((zr_rows > 0) != (zj_rows > 0))[keep].mean()),
        "rust_features_s": tr,
        "numpy_features_s": tn,
    }
    res["pass"] = (
        res["feature_max_abs"] <= 1e-4
        and res["logit_p999"] <= 1e-4
        and res["logit_max"] <= 1e-3
        and res["flag_disagreement"] <= 1e-5
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
