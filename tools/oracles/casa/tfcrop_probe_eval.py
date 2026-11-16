# SPDX-License-Identifier: GPL-3.0-or-later
"""Evaluate tfcrop probe batches against models (research/v8-tfcrop.md,
section 7; labelled probe). Reads `tfcrop_probe.py` designs and the CASA
flags `tfcrop_probe_casa.py` wrote.

Usage:
  tfcrop_probe_eval.py d1 BATCH_DIR DESIGN ARM CUTOFF
      the per-row rule D1 with the fit taken as the time mean (designs whose
      band any fit reproduces: S1, S2)
  tfcrop_probe_eval.py model BATCH_DIR DESIGN ARM CUTOFF FREQFIT MAXNPIECES
      rang.tfcrop's current frequency-direction model, plane by plane

Prints planes equal / planes, and cells different / cells.
"""

import json
import sys
from pathlib import Path

import numpy as np


def load_flags(path):
    z = np.load(path)
    s = tuple(int(v) for v in z["shape"])
    return np.unpackbits(z["flag"])[: int(np.prod(s))].astype(bool).reshape(s)


def planes(batch, design):
    meta = json.loads((Path(batch) / f"{design}.json").read_text(encoding="utf-8"))
    z = np.load(Path(batch) / f"{design}.npz")
    data = z["data"]
    nbl = meta["nbl"]
    for b, c, name in meta["planes"]:
        yield b, c, name, np.abs(data[b::nbl, :, c]).astype(np.float64), nbl


def d1_rows(u, live, cut, tol=0.1, passes=5):
    """D1: per row, sd = sqrt(mean u^2) over live cells; flag |u| > cut * sd;
    a row stops when its sd changes by less than `tol` (absolute) from the
    previous pass, the previous value starting at 0."""
    new = np.zeros(u.shape, bool)
    done = np.zeros((u.shape[0], 1), bool)
    prev = np.zeros((u.shape[0], 1))
    for _ in range(passes):
        ok = live & ~new
        cnt = np.maximum(ok.sum(1, keepdims=True), 1)
        sd = np.sqrt(np.where(ok, u * u, 0.0).sum(1, keepdims=True) / cnt)
        new |= ok & (np.abs(u) > cut * sd) & ~done
        done |= np.abs(sd - prev) < tol
        prev = sd
    return new


def compare(batch, design, arm, model):
    casa = load_flags(Path(batch) / "out" / f"{design}.{arm}.npz")
    eq = n = cells = diff = 0
    for b, c, _name, a, nbl in planes(batch, design):
        ref = casa[b::nbl, :, c]
        got = model(a)
        eq += bool(np.array_equal(got, ref))
        n += 1
        diff += int((got != ref).sum())
        cells += ref.size
    return eq, n, diff, cells


def main(argv):
    cmd = argv[0]
    if cmd == "d1":
        batch, design, arm, cut = argv[1], argv[2], argv[3], float(argv[4])

        def model(a):
            u = a / a.mean(0)[None, :] - 1.0
            return d1_rows(u, np.ones(u.shape, bool), cut)

    elif cmd == "model":
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
        from rang import tfcrop

        batch, design, arm, cut = argv[1], argv[2], argv[3], float(argv[4])
        params = {"flagdimension": "freq", "freqcutoff": cut, "freqfit": argv[5],
                  "maxnpieces": int(argv[6])}  # fmt: skip

        def model(a):
            return tfcrop.plane(a, np.zeros(a.shape, bool), params)

    elif cmd == "job":
        # every arm of DESIGN in BATCH/job.json through rang.tfcrop.plane,
        # with the gate's cell measures (precision, recall of added flags)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
        from rang import tfcrop

        batch, design = argv[1], argv[2]
        job = json.loads((Path(batch) / "job.json").read_text(encoding="utf-8"))
        for case in job:
            if not case["name"].startswith(design + "."):
                continue
            params = dict(case["calls"][0])
            casa = load_flags(Path(batch) / "out" / f"{case['name']}.npz")
            got = np.zeros_like(casa)
            eq = n = 0
            for b, c, _name, a, nbl in planes(batch, design):
                g = tfcrop.plane(a, np.zeros(a.shape, bool), params)
                got[b::nbl, :, c] = g
                eq += bool(np.array_equal(g, casa[b::nbl, :, c]))
                n += 1
            tp = int((got & casa).sum())
            print(f"{case['name']}: planes equal {eq}/{n}, agreement "
                  f"{float((got == casa).mean()):.6f}, CASA {int(casa.sum())}, rang "
                  f"{int(got.sum())}, precision {tp / max(int(got.sum()), 1):.4f}, "
                  f"recall {tp / max(int(casa.sum()), 1):.4f}", flush=True)  # fmt: skip
        return
    else:
        raise SystemExit(f"unknown command {cmd}")
    eq, n, diff, cells = compare(batch, design, arm, model)
    print(f"{design}.{arm}: planes equal {eq}/{n}, cells different {diff}/{cells}")


if __name__ == "__main__":
    main(sys.argv[1:])
