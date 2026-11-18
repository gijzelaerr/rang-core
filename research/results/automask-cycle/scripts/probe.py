# SPDX-License-Identifier: MIT
"""automask-cycle (research/automask-cycle.md, Measured result): post hoc pixel probes.

probe.py OUT.json SMALL_DIR

SMALL_DIR holds the -name prefixes <who>-<group>-n<k>[-tag]/image of small.sh.
For each scan-4 / scan-14 pair it reports the MFS residual and the 7x7 model
sum (channel mean) at the four sources where the imagers differ most, the
count of MFS residual pixels above fixed levels, and the largest |W - G|.
Read-only on the images; post hoc (not in section 4).
"""

import json
import os
import sys

import numpy as np
from astropy.io import fits

# (x, y) as WSClean logs them; arrays index [y, x].
SOURCES = [(1970, 2046), (2109, 1980), (2159, 1973), (1969, 2033)]
LEVELS_MJY = [5.0, 7.62, 10.0, 15.0]


def img(path):
    return np.asarray(fits.getdata(path), dtype=np.float64).squeeze()


def prefix(small, name):
    p = os.path.join(small, name, "image")
    return p if os.path.exists(p + "-MFS-residual.fits") else None


def mean_model(p, nch=8):
    if not os.path.exists(f"{p}-0000-model.fits"):
        return None  # only the MFS residual was copied
    return sum(img(f"{p}-{k:04d}-model.fits") for k in range(nch)) / nch


def at_sources(res, mod):
    out = []
    for x, y in SOURCES:
        s = np.s_[y - 3 : y + 4, x - 3 : x + 4]
        out.append(
            {
                "x": x,
                "y": y,
                "res_mJy": float(res[y, x] * 1e3),
                "res7_max_mJy": float(res[s].max() * 1e3),
                "model7_sum_mJy": None if mod is None else float(mod[s].sum() * 1e3),
            }
        )
    return out


def radler_sigma(x):
    v = x[np.isfinite(x)].astype(np.float32)
    m = np.median(v)
    return float(np.float32(1.4826022) * np.median(np.abs(v - m)))


def counts(res):
    return {f"{v:g}": int((np.abs(res) > v * 1e-3).sum()) for v in LEVELS_MJY}


def main():
    out, small = sys.argv[1:3]
    names = [
        "G-MAIN_1-n1",
        "W-MAIN_1-n1",
        "G-MAIN_1-n2",
        "W-MAIN_1-n2",
        "W-MAIN_1-n2-nofs",
        "G-MAIN_6-n2",
        "W-MAIN_6-n2",
    ]
    res = {}
    for n in names:
        p = prefix(small, n)
        if p is None:
            continue
        r = img(p + "-MFS-residual.fits")
        m = mean_model(p)
        i = int(np.argmax(np.abs(r)))
        y, x = np.unravel_index(i, r.shape)
        res[n] = {
            "peak": {"value_mJy": float(r.flat[i] * 1e3), "y": int(y), "x": int(x)},
            "above_mJy": counts(r),
            "sigma_uJy": radler_sigma(r) * 1e6,
            "sources": at_sources(r, m) if "MAIN_1" in n else None,
        }
        print(n, res[n]["peak"], res[n]["above_mJy"])
        if res[n]["sources"]:
            for s in res[n]["sources"]:
                print(
                    f"  x,y {s['x']},{s['y']} res {s['res_mJy']:.2f} "
                    f"max7 {s['res7_max_mJy']:.2f} model7 {s['model7_sum_mJy']} mJy"
                )
    gp = prefix(small, "G-MAIN_1-n2")
    for n in ("W-MAIN_1-n2", "W-MAIN_1-n2-nofs"):
        wp = prefix(small, n)
        if gp and wp:
            d = img(gp + "-MFS-residual.fits") - img(wp + "-MFS-residual.fits")
            res[n]["rms_G_minus_W_uJy"] = float(np.sqrt(np.nanmean(d * d)) * 1e6)
            print(
                n,
                "sigma",
                res[n]["sigma_uJy"],
                "rms G-W uJy",
                res[n]["rms_G_minus_W_uJy"],
            )
    with open(out, "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
