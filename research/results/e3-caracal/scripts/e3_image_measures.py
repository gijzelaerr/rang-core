"""E3-A single-arm image measures (research/e3-caracal.md section 5), provisional
until the joint scorer runs on both arms:

    python e3_image_measures.py IMAGE.fits RESIDUAL.fits OUT.json

- Off-source rms: MAD x 1.4826 of the MFS residual inside 0.7 deg of the image
  centre, outside the region where the MFS image is above 5 sigma, dilated by
  2 beams (sigma: the residual's MAD x 1.4826 inside the same radius, first pass).
- Dynamic range: the MFS image peak over that rms.
Beam from BMAJ/BMIN in the header, pixel size from CDELT2.
"""

import json
import sys

import numpy as np
from astropy.io import fits
from scipy import ndimage


def plane(path):
    with fits.open(path) as h:
        d = np.squeeze(np.asarray(h[0].data, dtype=np.float64))
        return d, h[0].header


def main(img_p, res_p, out):
    img, hdr = plane(img_p)
    res, _ = plane(res_p)
    pix = abs(hdr["CDELT2"])
    ny, nx = img.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    r = np.hypot(yy - ny / 2, xx - nx / 2) * pix
    inner = r <= 0.7
    s0 = 1.4826 * np.nanmedian(np.abs(res[inner] - np.nanmedian(res[inner])))
    bmaj_px = hdr.get("BMAJ", 0) / pix
    src = img > 5 * s0
    it = max(1, int(round(2 * bmaj_px)))
    srcd = ndimage.binary_dilation(src, iterations=it)
    sel = inner & ~srcd & np.isfinite(res)
    v = res[sel]
    rms = 1.4826 * np.median(np.abs(v - np.median(v)))
    peak = float(np.nanmax(img))
    rec = {"image": img_p, "residual": res_p, "pixel_deg": pix, "bmaj_deg": hdr.get("BMAJ"),
           "bmin_deg": hdr.get("BMIN"), "first_pass_sigma": float(s0),
           "mask_pixels_dilated": int(srcd.sum()), "pixels_used": int(sel.sum()),
           "offsource_rms": float(rms), "peak": peak, "dynamic_range": peak / float(rms)}
    with open(out, "w") as f:
        json.dump(rec, f, indent=1)
    print(json.dumps(rec))


if __name__ == "__main__":
    main(*sys.argv[1:4])
