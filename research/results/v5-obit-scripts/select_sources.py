"""Freeze V5's measurement sources and noise regions before any MFImage output exists.

S1: the 10 brightest truth points (bench/data/s1.json) with no other truth source
within 60 arcsec (about 4 beams of 13.9 x 8.3 arcsec). Noise region: inner field
(central 2N/3) farther than 72 px (108 arcsec, 10 beams) from every truth source.

pilot-512: from G7's WSClean 3.7 `minres` run (runs/WM-j16-r1, made 2026-11-10, no
Obit involved): sigma = 1.4826 MAD of the inner residual; candidates are local maxima
of the restored image above 20 sigma in the inner field; kept if compact (peak over
aperture flux, aperture radius 2 BMAJ, between 0.8 and 1.25) and isolated (no other candidate
above 10 % of its peak within 6 BMAJ); the 10 brightest by peak. Noise region: inner
field where the restored image stays below 5 sigma after dilating the >= 5 sigma mask
by 5 BMAJ.

Everything is written in world coordinates (RA, Dec in degrees) so each imager's own
WCS places it. Output: research/results/v5-obit-sources.json (and the two masks as
FITS, on the WSClean grids, under the run directory).

    python select_sources.py OUTDIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage

S1_JSON = Path(r"D:\rang\outputs\20261102-gemclean\bench\data\s1.json")
S1_IMG = Path(r"D:\rang\outputs\20261102-gemclean\bench\wsclean\s1-abs-minres-fast-j16-image.fits")
P_RUN = Path(r"D:\rang\outputs\g7-20261109-01\runs\WM-j16-r1")


def plane(path: Path):
    h = fits.open(path)[0]
    return np.asarray(h.data[0, 0], dtype=np.float64), h.header


def inner(n: int) -> slice:
    a = n // 6
    return slice(a, n - a)


def s1(outdir: Path) -> dict:
    d = json.loads(S1_JSON.read_text())
    comps = [c for c in d["components"] if c["kind"] == "point"]
    ra = np.degrees([c["ra_rad"] for c in comps])
    dec = np.degrees([c["dec_rad"] for c in comps])
    flux = np.array([c["flux"] for c in comps])
    cosd = np.cos(np.radians(dec.mean()))
    sep = np.hypot((ra[:, None] - ra[None]) * cosd, dec[:, None] - dec[None]) * 3600.0
    np.fill_diagonal(sep, np.inf)
    iso = sep.min(axis=1) > 60.0
    order = [i for i in np.argsort(-flux) if iso[i]][:10]
    img, hdr = plane(S1_IMG)
    w = WCS(hdr).celestial
    n = img.shape[0]
    x, y = w.all_world2pix(ra, dec, 0)
    yy, xx = np.mgrid[0:n, 0:n]
    mask = np.zeros((n, n), bool)
    sl = inner(n)
    mask[sl, sl] = True
    for xi, yi in zip(x, y):
        mask &= (xx - xi) ** 2 + (yy - yi) ** 2 > 72.0 ** 2
    fits.writeto(outdir / "s1-noise-mask.fits", mask.astype(np.uint8), hdr, overwrite=True)
    return {
        "sources": [{"ra_deg": float(ra[i]), "dec_deg": float(dec[i]), "truth_jy": float(flux[i]),
                     "truth_alpha": 0.0, "nearest_arcsec": float(sep[i].min())} for i in order],
        "noise_mask": "s1-noise-mask.fits", "noise_mask_pixels": int(mask.sum()),
        "grid": str(S1_IMG),
    }


def pilot(outdir: Path) -> dict:
    img, hdr = plane(P_RUN / "w-image.fits")
    res, _ = plane(P_RUN / "w-residual.fits")
    n = img.shape[0]
    sl = inner(n)
    r = res[sl, sl]
    sigma = 1.4826 * np.median(np.abs(r - np.median(r)))
    cell = abs(hdr["CDELT2"]) * 3600.0
    bmaj_px = hdr["BMAJ"] * 3600.0 / cell
    bmin_px = hdr["BMIN"] * 3600.0 / cell
    beam_area = np.pi * bmaj_px * bmin_px / (4 * np.log(2))
    peaks = (img == ndimage.maximum_filter(img, size=5)) & (img > 20 * sigma)
    inmask = np.zeros_like(peaks)
    inmask[sl, sl] = True
    py, px = np.nonzero(peaks & inmask)
    pv = img[py, px]
    rad = 2.0 * bmaj_px
    cand = []
    for yi, xi, v in zip(py, px, pv):
        y0, y1, x0, x1 = int(yi - rad - 1), int(yi + rad + 2), int(xi - rad - 1), int(xi + rad + 2)
        sub = img[y0:y1, x0:x1]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        ap = (yy - yi) ** 2 + (xx - xi) ** 2 <= rad ** 2
        sflux = sub[ap].sum() / beam_area
        cand.append((float(v), int(yi), int(xi), float(sflux)))
    keep = []
    for v, yi, xi, sflux in sorted(cand, reverse=True):
        if sflux <= 0 or not 0.8 <= v / sflux <= 1.25:
            continue
        near = [c for c in cand if c[0] > 0.1 * v and (c[1], c[2]) != (yi, xi)
                and np.hypot(c[1] - yi, c[2] - xi) < 6 * bmaj_px]
        if near:
            continue
        keep.append((v, yi, xi, sflux))
        if len(keep) == 10:
            break
    w = WCS(hdr).celestial
    src = []
    for v, yi, xi, sflux in keep:
        ra, dec = w.all_pix2world([[xi, yi]], 0)[0]
        src.append({"ra_deg": float(ra) % 360.0, "dec_deg": float(dec), "wsclean_peak_jy": v,
                    "wsclean_aperture_jy": sflux})
    strong = img >= 5 * sigma
    strong = ndimage.binary_dilation(strong, iterations=int(round(5 * bmaj_px)))
    mask = (~strong) & inmask
    fits.writeto(outdir / "pilot-noise-mask.fits", mask.astype(np.uint8), hdr, overwrite=True)
    return {"sources": src, "sigma_jy": float(sigma), "candidates_20sigma": len(cand),
            "noise_mask": "pilot-noise-mask.fits", "noise_mask_pixels": int(mask.sum()),
            "grid": str(P_RUN / "w-image.fits"), "bmaj_px": float(bmaj_px)}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rec = {"S1": s1(out), "pilot-512": pilot(out)}
    (out / "v5-obit-sources.json").write_text(json.dumps(rec, indent=1))
    for k, v in rec.items():
        print(k, len(v["sources"]), "sources; noise pixels", v["noise_mask_pixels"])
        for s in v["sources"]:
            print("  ", {a: round(b, 5) for a, b in s.items()})


if __name__ == "__main__":
    main()
