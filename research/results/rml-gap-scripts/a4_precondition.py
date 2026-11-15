"""a4_precondition.py: amendment A4's secondary precondition (research/rml-gap.md) on N2.

For each pfb arm (U-a, U-up, U-up2):
1. The Pearson correlation of pfb's MFS dirty image with the core's exact dirty image, in each of
   the eight orientations, and the margin of the best over the next.
2. For N2's isolated point sources (nearest other component >= 40 px away): the median of the
   dirty image's peak in a 5 x 5 px box over the catalogue flux, in radius bins under 10', 10-20'
   and over 20' from the phase centre.
Writes $O/scores/N2-a4-precondition.json.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "examples"))
import rml_gap_score as rs
from rang.core_imaging import read_fits

O = Path("D:/rang/outputs/rml-gap-20261113")
BINS = ((0, 10), (10, 20), (20, 1e9))


def main():
    cat = json.loads((O / "data/n2.json").read_text(encoding="utf-8"))
    scale = cat["image"]["scale_arcsec"]
    core = np.load(O / "prep/N2/core-dirty-fits-order.npy").astype(float)
    comps = cat["components"]
    xy = np.array([[p["x"], p["y"]] for p in comps])
    out = {}
    for arm in ("U-a", "U-up", "U-up2"):
        d, _ = read_fits(O / f"runs/{arm}/N2/pfb_I_main_dirty_time0000_mfs.fits")
        cs = sorted(
            ((float(np.corrcoef(np.asarray(f(d), float).ravel(), core.ravel())[0, 1]), k)
             for k, f in rs.ORIENT.items()), reverse=True)  # fmt: skip
        img = np.asarray(rs.ORIENT[cs[0][1]](d), float)
        rows = []
        for p in comps:
            if p["kind"] != "point" or np.sort(np.hypot(*(xy - [p["x"], p["y"]]).T))[1] < 40:
                continue
            r, c = round(p["y"]), round(p["x"])
            rad = float(np.hypot(p["dx"], p["dy"]) * scale / 60)
            rows.append((rad, float(img[r - 2 : r + 3, c - 2 : c + 3].max() / p["flux"])))
        rows = np.array(rows)
        bins = []
        for lo, hi in BINS:
            m = (rows[:, 0] >= lo) & (rows[:, 0] < hi)
            bins.append({"arcmin": [lo, hi if hi < 1e9 else None], "n": int(m.sum()),
                         "median_peak_over_flux": float(np.median(rows[m, 1]))})  # fmt: skip
        ok1 = cs[0][0] - cs[1][0] >= 0.5
        ok2 = all(0.9 <= b["median_peak_over_flux"] <= 1.1 for b in bins)
        out[arm] = {"orientation": cs[0][1], "correlation": cs[0][0],
                    "correlation_margin": cs[0][0] - cs[1][0], "orientation_pass": ok1,
                    "isolated_points": len(rows), "bins": bins, "no_smearing_pass": ok2,
                    "secondary_pass": ok1 and ok2}  # fmt: skip
    (O / "scores/N2-a4-precondition.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
