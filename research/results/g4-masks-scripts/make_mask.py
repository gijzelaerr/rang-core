"""make_mask.py TRUTH.json TEMPLATE.fits OUT.fits: the truth mask of research/g4-masks.md.

Discs of radius 6 pixels around every point of S >= 30 mJy and of radius 2 FWHM around every
Gaussian of the simulator's catalogue; float32, the template's header (WSClean's T0 dirty
image), data[y, x] as WSClean writes images. Points below 30 mJy (ten in S2,
10-28 mJy) are left out on purpose: they must stay in the residual.
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

R_POINT = 6.0
S_MIN = 0.03


def main():
    truth = json.loads(Path(sys.argv[1]).read_text())
    with fits.open(sys.argv[2]) as h:
        header = h[0].header.copy()
        shape = h[0].data.shape
    n = shape[-1]
    scale = float(truth["image"]["scale_arcsec"])
    yy, xx = np.mgrid[0:n, 0:n]
    m = np.zeros((n, n), bool)
    for c in truth["components"]:
        if c["kind"] == "point":
            if c["flux"] < S_MIN:
                continue
            r = R_POINT
        else:
            r = 2.0 * c["fwhm_arcsec"] / scale
        m |= (xx - c["x"]) ** 2 + (yy - c["y"]) ** 2 <= r * r
    data = np.zeros(shape, np.float32)
    data[..., :, :] = m.astype(np.float32)
    fits.PrimaryHDU(data, header).writeto(sys.argv[3], overwrite=True)
    print(f"{sys.argv[3]}: {int(m.sum())} pixels")


if __name__ == "__main__":
    main()
