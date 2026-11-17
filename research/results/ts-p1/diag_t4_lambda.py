"""TS-P1 T4, post hoc diagnostic (research/ts-p1.md 14.2): how the Euler
characteristic expectation depends on how Lambda is taken from the PSF.
Run after T4 failed at 5 sigma; it does not change T4's verdict.

    python diag_t4_lambda.py D:/rang/outputs/ts-p1-20261116/tsp1-noise.ms
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "examples"))
import ts_p1_measure as measure
import ts_p1_t4t5 as g
from rang import core_model, core_ms
from rang import lightcurve as lc

ms = sys.argv[1]
size, scale = 2048, 2.0
rows, times, unique = g.interval_rows(ms, 3)
freq, _, _ = core_model.band(ms, 3)
with core_ms.open_table(ms) as t:
    uvw, _, weight = measure.read_interval(t, np.sort(rows[times == unique[0]]))
psf = lc.snapshot(uvw, freq, np.ones(weight.shape, np.complex64), weight, size, scale)
psf /= psf[size // 2, size // 2]
c = size // 2
# Finite-difference curvature at the peak (second order, one pixel).
dxx = -(psf[c, c + 1] + psf[c, c - 1] - 2)
dyy = -(psf[c + 1, c] + psf[c - 1, c] - 2)
dxy = -(psf[c + 1, c + 1] - psf[c + 1, c - 1] - psf[c - 1, c + 1] + psf[c - 1, c - 1]) / 4
fd = np.array([[dxx, dxy], [dxy, dyy]])
area, per = float(size * size), float(4 * size)
for name, lam in (("lobe fit rho>0.5 (frozen)", g.fit_lambda(psf, size)[0]), ("finite difference at peak", fd)):
    e5 = 450 * g.expected_ec(5.0, area, per, lam)
    print(f"{name}: det {np.linalg.det(lam):.5g}  E5 {e5:.1f}  3sqrtE {3 * math.sqrt(e5):.1f}")
