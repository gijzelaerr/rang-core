"""TS-P1 protocol 2, post hoc diagnostic (research/ts-p1.md 14.3): does
WSClean 3.7 ignore FLAG_ROW? Its source has no reference to FLAG_ROW
(grep of the 3.6 tree in ~/Build/tmp/20261109-g4-wsclean-src), and
tsp1-held2 sets FLAG_ROW on 2 % of rows with their cells unflagged. This
images three intervals with rang's own reader, with FLAG_ROW applied (the
product) and ignored, against WSClean's images.

    python diag_flagrow.py D:/rang/outputs/ts-p1-20261116/tsp1-held2.ms WSC_DIR
"""

import sys

import numpy as np
from astropy.io import fits
from rang import core_model, core_ms, core_weights
from rang import lightcurve as lc

ms, wsc = sys.argv[1], sys.argv[2]
rows = core_model.selected_rows(ms, 3)
freq, _, _ = core_model.band(ms, 3)
with core_ms.open_table(ms) as t:
    times = t.getcol_rows("TIME", rows)
    unique = np.unique(times)
    for k in (0, 225, 309):
        sel = np.sort(rows[times == unique[k]])
        data = t.getcol_rows("CORRECTED_DATA", sel) - t.getcol_rows("MODEL_DATA", sel)
        vis, w = core_weights.stokes_i(
            data, t.getcol_rows("WEIGHT_SPECTRUM", sel), t.getcol_rows("FLAG", sel)
        )
        uvw = np.asarray(t.getcol_rows("UVW", sel), np.float64)
        row_flag = t.getcol_rows("FLAG_ROW", sel).astype(bool)
        w_applied = w.copy()
        w_applied[row_flag] = 0.0
        with fits.open(f"{wsc}/w-t{k:04d}-dirty.fits") as h:
            ref = np.asarray(h[0].data[0, 0], np.float64)
        peak = np.max(np.abs(ref))
        a = lc.snapshot(uvw, freq, vis, w_applied, 2048, 2.0)
        b = lc.snapshot(uvw, freq, vis, w, 2048, 2.0)
        print(
            k,
            "flag_rows",
            int(row_flag.sum()),
            "applied",
            np.max(np.abs(a - ref)) / peak,
            "ignored",
            np.max(np.abs(b - ref)) / peak,
        )
