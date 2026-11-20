"""F5 Stage 1 (research/f5-flagger.md, section 2f): the PyTorch port of F4's
network (`rang.f5net`, stem=False) with F4's trained seed-2 weights against
`rang._core.f4flag_logits` on a validation scan. Validation only.

Usage: python examples/f5_port_parity.py OUT.json [--set luno:MAIN_7]
       [--weights D:/rang/outputs/f4-20261111-08-train-calibrator/seed-2/weights.npz]
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from rang import f3flag as f3
from rang import f3net, f5net
from rang import f4flag as f4

F4_W = "D:/rang/outputs/f4-20261111-08-train-calibrator/seed-2/weights.npz"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--set", default="luno:MAIN_7")
    ap.add_argument("--weights", default=F4_W)
    a = ap.parse_args()
    t0 = time.perf_counter()
    scan = f4.load(a.set)
    w3 = f3.w3_flags(scan)
    arrays = f3net.load_params(a.weights)
    flat = f3net.flat_weights(arrays)
    zr = f4.rust_logits(scan, w3, flat)
    ix = f3.index(scan)
    net = f5net.build(23, False, arrays).eval()
    zt = np.full_like(zr, np.nan)
    nbl = len(ix["ubl"])
    for s in range(0, nbl, 64):
        sel = np.arange(s, min(s + 64, nbl))
        x = f4.rust_features(scan, w3, sel)
        with torch.no_grad():
            z = net(torch.from_numpy(x)).numpy()
        rows = np.flatnonzero((ix["bl"] >= s) & (ix["bl"] < s + len(sel)))
        zt[rows] = z[ix["bl"][rows] - s, ix["t"][rows]]
    el = ~w3
    d = np.abs(zr - zt)[el]
    rec = {
        "set": a.set,
        "weights": a.weights,
        "weights_sha256": hashlib.sha256(Path(a.weights).read_bytes()).hexdigest(),
        "eligible": int(el.sum()),
        "logit_p999": float(np.quantile(d, 0.999)),
        "logit_max": float(d.max()),
        "flag_disagreement_tau-1": float(np.mean((zr > -1.0)[el] != (zt > -1.0)[el])),
        "torch": torch.__version__,
        "wall_s": time.perf_counter() - t0,
    }
    rec["pass"] = (
        rec["logit_p999"] <= 1e-4
        and rec["logit_max"] <= 1e-3
        and rec["flag_disagreement_tau-1"] <= 1e-5
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
