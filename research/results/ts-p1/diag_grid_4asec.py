"""TS-P1 amendment 9.1's proof, as run on 2026-11-16 (research/ts-p1.md 9.1):
does WSClean drop the samples beyond the uv grid at 4 arcsec?

    python diag_grid_4asec.py D:/rang/outputs/ts-p1-20261116/tsp1-dev.ms WSC_DIR

WSC_DIR holds WSClean's dirty images of the dev set at the frozen grid, made
by `bash tools/oracles/ts-p1/wsclean_intervals.sh SRC_MS OUT 4 450 1024 4asec`
(deleted after the run; regenerate them that way). Output as run, on commit
ec6bef5's extension (interval, samples beyond 1/(2 x 4"), max |rang - WSClean|
/ peak with all samples, the same with those samples removed):

    0 outside 530 all 0.036928058971533326 cut 2.743894985435241e-07
    225 outside 587 all 0.04037314233692028 cut 1.9511738611578936e-07
    430 outside 646 all 0.0823191763383308 cut 7.459847209037812e-08
"""

import sys

import numpy as np
from astropy.io import fits
from rang import core_ms
from rang import lightcurve as lc

ms, wsc = sys.argv[1], sys.argv[2]
pix = 4.0 * lc.ARCSEC
umax = 1.0 / (2.0 * pix)
with core_ms.open_table(ms + "/SPECTRAL_WINDOW") as sw:
    freq = np.asarray(sw.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
with core_ms.open_table(ms) as t:
    times = t.getcol("TIME")
    tu = np.unique(times)
    for k in (0, 225, 430):
        rows = np.flatnonzero(times == tu[k])
        uvw, vis, weight = lc._residual(t, rows, "DATA", "MODEL_DATA", "WEIGHT", 64)
        uw = uvw[:, :2, None] * freq[None, None, :] / 299792458.0
        out = (np.abs(uw[:, 0]) >= umax) | (np.abs(uw[:, 1]) >= umax)
        img_all = lc.snapshot(uvw, freq, vis, weight, 1024, 4.0)
        w2 = weight.copy()
        w2[out] = 0.0
        img_cut = lc.snapshot(uvw, freq, vis, w2, 1024, 4.0)
        with fits.open(f"{wsc}/w-t{k:04d}-dirty.fits") as h:
            w = np.asarray(h[0].data[0, 0], np.float64)
        peak = np.max(np.abs(w))
        print(
            k,
            "outside",
            int(out.sum()),
            "all",
            np.max(np.abs(img_all - w)) / peak,
            "cut",
            np.max(np.abs(img_cut - w)) / peak,
        )
