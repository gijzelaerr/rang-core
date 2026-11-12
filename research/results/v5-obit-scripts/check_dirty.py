"""check_dirty.py: conversion checks (b) and (c) of research/v5-obit.md, section 1.

    check_dirty.py OBIT_CUBE.fits SOURCES_JSON > check-bc.json

(b) For each S1 source of SOURCES_JSON, the flux-weighted centroid of the 5x5 pixels around
the brightest pixel within 3 px of its true position in plane 1, and its offset from the
true position in pixels (a sign or conjugation error in the conversion mirrors the field).
(c) The cube's axes, planes and the FREQnnnn header cards.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


def main() -> None:
    cube, srcf = sys.argv[1], sys.argv[2]
    h = fits.open(cube)[0]
    hdr = h.header
    data = h.data
    while data.ndim > 3:
        data = data[0]
    img = data[0].astype(np.float64)
    w = WCS(hdr).celestial
    out = {"shape": list(data.shape), "naxis": {k: hdr.get(f"NAXIS{k}") for k in range(1, 5)},
           "ctype": [hdr.get(f"CTYPE{k}") for k in range(1, 5)],
           "crval3": hdr.get("CRVAL3"), "bmaj_arcsec": hdr.get("BMAJ", 0) * 3600,
           "bmin_arcsec": hdr.get("BMIN", 0) * 3600, "bpa_deg": hdr.get("BPA"),
           "nterm": hdr.get("NTERM"), "nspec": hdr.get("NSPEC"),
           "freq_cards": {k: hdr[k] for k in hdr if k.startswith("FREQ")},
           "sources": []}  # fmt: skip
    for s in json.loads(open(srcf).read())["S1"]["sources"]:
        x, y = w.all_world2pix([[s["ra_deg"], s["dec_deg"]]], 0)[0]
        xi, yi = int(round(x)), int(round(y))
        sub = img[yi - 3 : yi + 4, xi - 3 : xi + 4]
        dy, dx = np.unravel_index(np.argmax(sub), sub.shape)
        py, px = yi - 3 + dy, xi - 3 + dx
        win = img[py - 2 : py + 3, px - 2 : px + 3]
        yy, xx = np.mgrid[py - 2 : py + 3, px - 2 : px + 3]
        wt = np.clip(win, 0, None)
        cx, cy = (wt * xx).sum() / wt.sum(), (wt * yy).sum() / wt.sum()
        out["sources"].append({"flux_true": s.get("flux_jy", s.get("flux")), "peak": float(img[py, px]),
                               "dx_px": float(cx - x), "dy_px": float(cy - y),
                               "offset_px": float(np.hypot(cx - x, cy - y))})  # fmt: skip
    off = [e["offset_px"] for e in out["sources"]]
    out["offset_max_px"], out["offset_median_px"] = float(max(off)), float(np.median(off))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
