"""beam_diag.py PSF.fits ESTIMATE_ASEC [--scale ASEC]: WSClean 3.7's restoring-beam fit in numpy.

A diagnostic of research/g7-defaults.md, section 2 (development PSFs only): schaapcommon's
Fit2DGaussianCentred with WSClean's defaults (box 10 beams, negatives included, regrowth up to 5
times), solved with scipy's Levenberg-Marquardt, against the beam the FITS header carries.
"""

import argparse
import math

import numpy as np
from astropy.io import fits
from scipy.optimize import least_squares

S2B = 2.0 * math.sqrt(2.0 * math.log(2.0))


def fwhm(sx, sy, beta):
    f = 1.0 - beta * beta
    cov = np.array([[sx * sx / f, beta * sx * sy / f], [beta * sx * sy / f, sy * sy / f]])
    e, v = np.linalg.eigh(cov)
    major, minor = math.sqrt(abs(e[1])) * S2B, math.sqrt(abs(e[0])) * S2B
    vec = v[:, 1]
    return major, minor, -math.atan2(vec[0], vec[1])


def single(img, est):
    h, w = img.shape
    sf = (w + h) // 2
    ys, xs = np.mgrid[0:h, 0:w]
    x = (xs - w // 2) / sf
    y = (ys - h // 2) / sf
    d = img.astype(np.float64)

    def res(p):
        sx, sy, b = p
        return (np.exp(-x * x / (2 * sx * sx) + b * x * y / (sx * sy) - y * y / (2 * sy * sy)) - d).ravel()

    p0 = [est / (sf * S2B), est / (sf * S2B), 0.0]
    r = least_squares(res, p0, method="lm", xtol=1e-12, ftol=1e-12)
    major, minor, pa = fwhm(*r.x)
    return major * sf, minor * sf, pa


def fit(image, est, box=10.0):
    h, w = image.shape
    pref = max(math.ceil(box), math.ceil(est * box))
    pref += pref % 2
    for _ in range(5):
        bw, bh = min(pref, w), min(pref, h)
        x0, y0 = (w - bw) // 2, (h - bh) // 2
        sub = image[y0 : (h + bh) // 2, x0 : x0 + bw]
        major, minor, pa = single(sub, est)
        ok = (major * box * 0.8 < bw or bw >= w) and (major * box * 0.8 < bh or bh >= h)
        if ok:
            break
        pref = max(math.ceil(box), math.ceil(major * box))
        pref += pref % 2
        est = max(major, est)
    return major, minor, pa


def main():
    p = argparse.ArgumentParser()
    p.add_argument("psf")
    p.add_argument("estimate_asec", type=float)
    a = p.parse_args()
    with fits.open(a.psf) as f:
        h = f[0].header
        img = np.squeeze(f[0].data)
    scale = abs(h["CDELT1"]) * 3600.0
    img = img / img[img.shape[0] // 2, img.shape[1] // 2]
    major, minor, pa = fit(img, max(a.estimate_asec, scale) / scale)
    print(f"fit: {major * scale:.4f} x {minor * scale:.4f} asec, PA {math.degrees(pa):.3f} deg")
    if "BMAJ" in h:
        print(f"header: {h['BMAJ'] * 3600:.4f} x {h['BMIN'] * 3600:.4f} asec, PA {h['BPA']:.3f} deg")


if __name__ == "__main__":
    main()
