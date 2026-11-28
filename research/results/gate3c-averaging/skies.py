# SPDX-License-Identifier: MIT
"""Sky lists for research/gate3c-averaging.md P2, P2b (amendment A2) and P3,
as examples/gemclean_bench_simulate.py --sky-override takes them (pixel
offsets dx, dy from the centre pixel; l = -dx * scale, m = dy * scale).

    python skies.py OUTDIR
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

SCALE = 2.0  # arcsec per pixel
RINGS = (0.25, 0.5, 0.75)
AZ = 16
P3_SEED = 20261281
SIGMA_REF = 17e-6  # Jy, E2-N's WSClean MFS residual MAD (A2)


def rings(size):
    hw = size / 2 * SCALE  # arcsec
    radii = [f * hw for f in RINGS] + [hw - 4.0]
    out = []
    for r in radii:
        for k in range(AZ):
            phi = 2 * math.pi * k / AZ
            l, m = r * math.cos(phi), r * math.sin(phi)
            dx, dy = round(-l / SCALE), round(m / SCALE)
            out.append({"dx": dx, "dy": dy, "flux": 1.0, "kind": "point",
                        "ring_arcsec": r, "azimuth": k})  # fmt: skip
    return out


def p3_sky(size=3072, n=760):
    rng = np.random.default_rng(P3_SEED)
    lo, hi, g = 8 * SIGMA_REF, 1000 * SIGMA_REF, -1.7
    u = rng.uniform(size=n)
    # inverse CDF of dN/dS ~ S^g on [lo, hi]
    a = g + 1
    flux = (lo**a + u * (hi**a - lo**a)) ** (1 / a)
    half = size // 2 - 20
    dx = rng.integers(-half, half, n)
    dy = rng.integers(-half, half, n)
    off = rng.uniform(-0.5, 0.5, (n, 2))  # continuous positions, off pixel centres
    comps = [{"dx": float(dx[i] + off[i, 0]), "dy": float(dy[i] + off[i, 1]),
              "flux": float(flux[i]), "kind": "point"} for i in range(n)]  # fmt: skip
    for j in range(4):
        fwhm = float(rng.uniform(30, 120))
        peak = float(rng.uniform(20, 50)) * SIGMA_REF
        # Gaussian total flux for that peak in a ~10" beam: peak * (fwhm^2 + b^2) / b^2
        b = 10.0
        comps.append({"dx": float(rng.integers(-half, half)), "dy": float(rng.integers(-half, half)),
                      "flux": peak * (fwhm**2 + b**2) / b**2, "kind": "gaussian",
                      "fwhm_arcsec": fwhm})  # fmt: skip
    return comps


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, comps in (("p2-6144", rings(6144)), ("p2b-3072", rings(3072)), ("p3-3072", p3_sky())):
        (out / f"sky-{name}.json").write_text(json.dumps(comps, indent=0), encoding="utf-8")
        print(name, len(comps))
