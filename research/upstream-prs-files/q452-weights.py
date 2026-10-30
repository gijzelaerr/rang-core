"""Copy-in-place helper: set WEIGHT_SPECTRUM/WEIGHT to w * scale per correlation.

usage: python weights.py <ms> <sXX> <sXY> <sYX> <sYY>
Keeps the MS's own per-sample weights (or 1 if absent) and multiplies by scale.
"""

import sys

import numpy as np
from casacore.tables import table

ms, scale = sys.argv[1], np.array([float(x) for x in sys.argv[2:6]])
t = table(ms, readonly=False, ack=False)
for col in ("WEIGHT_SPECTRUM", "WEIGHT"):
    if col in t.colnames():
        w = t.getcol(col)
        print(col, w.shape, "before: per-corr mean", w.reshape(-1, 4).mean(0))
        t.putcol(col, (w * scale).astype(w.dtype))
t.close()
