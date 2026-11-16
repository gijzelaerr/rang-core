"""TS-P1 13.3, reported (not gated): where rang's w-stacking snapshot differs
from the exact wgridder on tsp1-held2 interval 0 (2000^2 at 2 arcsec).

    python diag_wstack.py D:/rang/outputs/ts-p1-20261116/tsp1-held2.ms
"""

import sys

import numpy as np
from rang import core_model, core_ms
from rang import lightcurve as lc

ms = sys.argv[1]
size, scale = 2000, 2.0
rows = core_model.selected_rows(ms, 3)
freq, _, _ = core_model.band(ms, 3)
column, model, weights = lc._columns(ms, None, "MODEL_DATA")
with core_ms.open_table(ms) as t:
    times = t.getcol_rows("TIME", rows)
    sel = np.sort(rows[times == np.unique(times)[0]])
    uvw, vis, w = lc._residual(t, sel, column, model, weights, len(freq))
exact = lc.snapshot(uvw, freq, vis, w, size, scale)
stack = lc.snapshot(uvw, freq, vis, w, size, scale, 1e-6, "wstack", "cpu")
d = np.abs(stack - exact)
peak = np.max(np.abs(exact))
c = size // 2
for name, box in (("full", slice(None)), ("inner half", slice(c - c // 2, c + c // 2)),
                  ("inner quarter", slice(c - c // 4, c + c // 4))):  # fmt: skip
    print(name, float(np.max(d[box, box]) / peak))
print("ratio of rms", float(np.std(stack) / np.std(exact)))
k = np.unravel_index(np.argmax(d), d.shape)
print("worst pixel", k, float(exact[k]), float(stack[k]))
