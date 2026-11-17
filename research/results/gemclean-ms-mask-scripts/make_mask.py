# SPDX-License-Identifier: MIT
"""make_mask.py TRUTH.json TEMPLATE.fits OUT.fits: H4's point mask of research/gemclean-ms-mask.md.

Discs of radius 6 pixels around every point of the simulator's catalogue; the Gaussians are left
outside on purpose (extended emission outside the mask, as in floor-5's Dms03). float32, the
template's header (a WSClean H4 image at 2048^2, 1.5"), data[y, x] as WSClean writes images.
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

R_POINT = 6.0


def main():
    truth = json.loads(Path(sys.argv[1]).read_text())
    with fits.open(sys.argv[2]) as h:
        header = h[0].header.copy()
        shape = h[0].data.shape
    n = shape[-1]
    yy, xx = np.mgrid[0:n, 0:n]
    m = np.zeros((n, n), bool)
    for c in truth["components"]:
        if c["kind"] == "point":
            m |= (xx - c["x"]) ** 2 + (yy - c["y"]) ** 2 <= R_POINT * R_POINT
    data = np.zeros(shape, np.float32)
    data[..., :, :] = m.astype(np.float32)
    fits.PrimaryHDU(data, header).writeto(sys.argv[3], overwrite=True)
    print(f"{sys.argv[3]}: {int(m.sum())} pixels")


if __name__ == "__main__":
    main()
