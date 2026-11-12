# SPDX-License-Identifier: GPL-3.0-or-later
"""W6 case edits (research/w6-imaging-inputs.md), python-casacore 3.8.1.

python prep.py MS --random-ws SEED      # WEIGHT_SPECTRUM uniform in [0.2, 5], WEIGHT its channel mean
python prep.py MS --unit                # WEIGHT_SPECTRUM = 1 and WEIGHT = 1
python prep.py MS --random-weight SEED  # WEIGHT uniform in [0.2, 5] per row and correlation
python prep.py MS --drop-ws             # WEIGHT_SPECTRUM removed
python prep.py MS --undefine-ws         # removed, then declared again with no cell written (W4)
python prep.py MS --sentinel COL        # COL (StandardStMan) = 7+7j everywhere
"""

import argparse

import numpy as np
import casacore.tables as ct

STEP = 2048


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("--random-ws", type=int)
    p.add_argument("--unit", action="store_true")
    p.add_argument("--random-weight", type=int)
    p.add_argument("--drop-ws", action="store_true")
    p.add_argument("--undefine-ws", action="store_true")
    p.add_argument("--sentinel")
    a = p.parse_args()
    t = ct.table(a.ms, readonly=False, ack=False)
    n = t.nrows()
    shape = t.getcell("DATA", 0).shape
    if a.random_ws is not None:
        rng = np.random.default_rng(a.random_ws)
        for s in range(0, n, STEP):
            k = min(STEP, n - s)
            ws = rng.uniform(0.2, 5.0, (k, *shape)).astype(np.float32)
            t.putcol("WEIGHT_SPECTRUM", ws, s, k)
            t.putcol("WEIGHT", ws.mean(axis=1).astype(np.float32), s, k)
        print("random WEIGHT_SPECTRUM, seed", a.random_ws)
    if a.unit:
        for s in range(0, n, STEP):
            k = min(STEP, n - s)
            t.putcol("WEIGHT_SPECTRUM", np.ones((k, *shape), np.float32), s, k)
            t.putcol("WEIGHT", np.ones((k, shape[1]), np.float32), s, k)
        print("unit weights")
    if a.random_weight is not None:
        rng = np.random.default_rng(a.random_weight)
        t.putcol("WEIGHT", rng.uniform(0.2, 5.0, (n, shape[1])).astype(np.float32))
        print("random WEIGHT, seed", a.random_weight)
    if a.drop_ws or a.undefine_ws:
        t.removecols("WEIGHT_SPECTRUM")
        print("WEIGHT_SPECTRUM removed")
    if a.undefine_ws:
        t.addcols(ct.makearrcoldesc("WEIGHT_SPECTRUM", 0.0, ndim=2, valuetype="float"))
        print("WEIGHT_SPECTRUM declared, no cells")
    if a.sentinel:
        if a.sentinel not in t.colnames():
            t.addcols(ct.makearrcoldesc(a.sentinel, 0j, ndim=2, valuetype="complex"))
        for s in range(0, n, STEP):
            k = min(STEP, n - s)
            t.putcol(a.sentinel, np.full((k, *shape), 7 + 7j, np.complex64), s, k)
        print("sentinel", a.sentinel)
    t.close()


if __name__ == "__main__":
    main()
