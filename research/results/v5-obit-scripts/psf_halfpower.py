"""psf_halfpower.py: one beam estimator for every imager's PSF (research/v5-obit.md, section 9).

    psf_halfpower.py PSF.fits [PSF.fits ...]

For each image (first plane), a 2-D Gaussian with peak 1 at the PSF's peak pixel is fitted by
least squares to the connected main-lobe pixels at or above 35 % of the peak, the same way for
every imager, so that the imagers' own beam fitters drop out of the comparison. Reports FWHM
major and minor axes (arcsec) and the position angle from north through east (degrees).
"""

from __future__ import annotations

import json
import sys

import numpy as np
from astropy.io import fits
from scipy import ndimage, optimize

LEVEL = 0.35


def fit(path: str) -> dict:
    h = fits.open(path)[0]
    img = h.data
    while img.ndim > 2:
        img = img[0]
    img = img.astype(np.float64)
    cell = abs(h.header["CDELT2"]) * 3600.0
    py, px = np.unravel_index(np.nanargmax(img), img.shape)
    img = img / img[py, px]
    lab, _ = ndimage.label(img >= LEVEL)
    yy, xx = np.nonzero(lab == lab[py, px])
    e = -(xx - px) * cell  # east (RA increases towards -x)
    n = (yy - py) * cell
    v = img[yy, xx]

    def model(p):
        sa, sb, th = p  # sigma along the major axis (PA th from north to east), minor axis
        u = e * np.sin(th) + n * np.cos(th)
        w = e * np.cos(th) - n * np.sin(th)
        return np.exp(-0.5 * ((u / sa) ** 2 + (w / sb) ** 2)) - v

    r = optimize.least_squares(model, [5.0, 4.0, 0.0])
    sa, sb, th = r.x
    k = 2 * np.sqrt(2 * np.log(2))
    bmaj, bmin, pa = abs(sa) * k, abs(sb) * k, np.degrees(th)
    if bmin > bmaj:
        bmaj, bmin, pa = bmin, bmaj, pa + 90.0
    pa = (pa + 90.0) % 180.0 - 90.0
    return {"file": path, "bmaj_arcsec": float(bmaj), "bmin_arcsec": float(bmin),
            "bpa_deg": float(pa), "pixels": int(v.size), "cell_arcsec": cell,
            "rms_misfit": float(np.sqrt(np.mean(r.fun**2)))}  # fmt: skip


if __name__ == "__main__":
    print(json.dumps([fit(p) for p in sys.argv[1:]], indent=1))
