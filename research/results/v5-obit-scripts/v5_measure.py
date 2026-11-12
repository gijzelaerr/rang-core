"""v5_measure.py: section 4 measures of research/v5-obit.md on one run directory.

    v5_measure.py RUN_DIR SOURCES_JSON SELECT_DIR > measures.json

Reads the run's restored images: GeMClean (g-000k-image.fits, g-MFS-image.fits), WSClean
(w-...), MFImage (one cube: plane 1 flux, plane 2 spectral index, planes 3.. the coarse
frequency images, centre frequencies in the FREQ00nn header cards). Positions come from
SOURCES_JSON in world coordinates; noise masks (SELECT_DIR) are placed by world coordinates
onto each image grid (nearest pixel of the mask grid).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

NU0 = {"S1": 1.4e9, "P": 1.043e9}


def beam_px(h):
    cell = abs(h["CDELT2"]) * 3600.0
    return h["BMAJ"] * 3600.0 / cell, h["BMIN"] * 3600.0 / cell, h.get("BPA", 0.0)


def aperture(img, w, h, ra, dec):
    bmaj, bmin, _ = beam_px(h)
    area = np.pi * bmaj * bmin / (4 * np.log(2))
    x, y = w.all_world2pix([[ra, dec]], 0)[0]
    r = 2.0 * bmaj
    y0, y1 = int(np.floor(y - r)), int(np.ceil(y + r)) + 1
    x0, x1 = int(np.floor(x - r)), int(np.ceil(x + r)) + 1
    sub = img[y0:y1, x0:x1]
    yy, xx = np.mgrid[y0:y1, x0:x1]
    ap = (yy - y) ** 2 + (xx - x) ** 2 <= r**2
    return float(np.nansum(sub[ap]) / area), float(np.nanmax(sub[ap]))


def noise(img, w, mask, mw):
    ny, nx = img.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra, dec = w.all_pix2world(xx.ravel(), yy.ravel(), 0)
    mx, my = mw.all_world2pix(ra, dec, 0)
    mx = np.rint(mx).astype(int)
    my = np.rint(my).astype(int)
    ok = (mx >= 0) & (my >= 0) & (mx < mask.shape[1]) & (my < mask.shape[0])
    sel = np.zeros(ok.shape, bool)
    sel[ok] = mask[my[ok], mx[ok]] > 0
    v = img.ravel()[sel]
    v = v[np.isfinite(v)]
    return {"mad_jy": float(1.4826 * np.median(np.abs(v - np.median(v)))),
            "std_jy": float(np.std(v)), "pixels": int(v.size)}


def planes(run: Path):
    """[(label, image2d, header, freq_hz)] for the sub-bands, plus the MFS (label 'MFS')."""
    out = []
    for prefix in ("g", "w"):
        mfs = run / f"{prefix}-MFS-image.fits"
        if mfs.exists():
            for k in range(64):
                f = run / f"{prefix}-{k:04d}-image.fits"
                if not f.exists():
                    break
                h = fits.open(f)[0]
                out.append((f"{k}", h.data[0, 0].astype(np.float64), h.header, float(h.header["CRVAL3"])))
            h = fits.open(mfs)[0]
            out.append(("MFS", h.data[0, 0].astype(np.float64), h.header, float(h.header["CRVAL3"])))
            return out, None
    cubes = [f for f in run.glob("*.fits") if f.name.upper().endswith("I.FITS")]
    if len(cubes) != 1:
        raise SystemExit(f"no image found in {run}")
    h = fits.open(cubes[0])[0]
    data = h.data.astype(np.float64)
    while data.ndim > 3:
        data = data[0]
    hdr = h.header
    nterm = 2  # norder 1: flux, spectral index
    for k in range(data.shape[0] - nterm):
        key = f"FREQ{k + 1:04d}"
        freq = float(hdr[key]) if key in hdr else float("nan")
        out.append((f"{k}", data[nterm + k], hdr, freq))
    out.append(("MFS", data[0], hdr, float(hdr["CRVAL3"])))
    return out, data[1]


def main() -> None:
    run, srcf, sel = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    ds = "S1" if "-S1-" in run.name else "P"
    key = "S1" if ds == "S1" else "pilot-512"
    srcs = json.loads(srcf.read_text())[key]
    mh = fits.open(sel / srcs["noise_mask"])[0]
    mask = mh.data
    mw = WCS(mh.header).celestial
    pl, alpha_plane = planes(run)
    rec = {"run": run.name, "ds": ds, "planes": [], "sources": []}
    for label, img, h, freq in pl:
        w = WCS(h).celestial
        bmaj, bmin, bpa = beam_px(h)
        cell = abs(h["CDELT2"]) * 3600.0
        rec["planes"].append({"label": label, "freq_hz": freq, "bmaj_arcsec": bmaj * cell,
                              "bmin_arcsec": bmin * cell, "bpa_deg": float(bpa),
                              "noise": noise(img, w, mask, mw)})  # fmt: skip
    subs = [p for p in pl if p[0] != "MFS"]
    nu = np.array([p[3] for p in subs])
    for s in srcs["sources"]:
        fl = []
        for label, img, h, freq in subs:
            fl.append(aperture(img, WCS(h).celestial, h, s["ra_deg"], s["dec_deg"])[0])
        fl = np.array(fl)
        ok = fl > 0
        a, b = np.polyfit(np.log(nu[ok] / NU0[ds]), np.log(fl[ok]), 1) if ok.sum() >= 2 else (np.nan, np.nan)
        mfs = [p for p in pl if p[0] == "MFS"][0]
        s_mfs, peak = aperture(mfs[1], WCS(mfs[2]).celestial, mfs[2], s["ra_deg"], s["dec_deg"])
        entry = {**s, "subband_jy": fl.tolist(), "alpha": float(a), "s_nu0_jy": float(np.exp(b)),
                 "mfs_aperture_jy": s_mfs, "mfs_peak_jy": peak}  # fmt: skip
        if alpha_plane is not None:
            w = WCS(mfs[2]).celestial
            x, y = w.all_world2pix([[s["ra_deg"], s["dec_deg"]]], 0)[0]
            entry["obit_alpha_plane"] = float(alpha_plane[int(round(y)), int(round(x))])
        rec["sources"].append(entry)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
