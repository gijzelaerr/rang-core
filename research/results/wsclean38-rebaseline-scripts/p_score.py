# SPDX-License-Identifier: MIT
"""p_score.py DIR: arm P of research/wsclean38-rebaseline.md, section 4.

Compares DIR/w3.7 with DIR/w3.8 (S1 dirty images and PSFs, minres and nominres) and writes
DIR/p-score.json: max |diff| / peak per image, the frozen verdict, and the beam keywords each
version wrote.
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

TOL = {"minres": 1e-3, "nominres": 1e-5}
STOP = 1e-2


def main():
    d = Path(sys.argv[1])
    res = {}
    for grid, tol in TOL.items():
        for kind in ("dirty", "psf"):
            name = f"s1-dirty-{grid}-fast-j16-{kind}.fits"
            a, b = (fits.open(d / f"w{v}" / name) for v in ("3.7", "3.8"))
            x, y = a[0].data.astype(np.float64), b[0].data.astype(np.float64)
            r = float(np.max(np.abs(x - y)) / np.max(np.abs(x)))
            verdict = "pass" if r <= tol else ("record" if r <= STOP else "stop")
            beams = {
                v: {k: h[0].header.get(k) for k in ("BMAJ", "BMIN", "BPA")}
                for v, h in (("3.7", a), ("3.8", b))
            }
            res[f"{grid}-{kind}"] = {
                "max_abs_diff_over_peak": r,
                "tol": tol,
                "verdict": verdict,
                "beams": beams,
            }
            print(f"{grid:9s} {kind:5s} {r:.3e} (tol {tol:g}) {verdict}")
    (d / "p-score.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
