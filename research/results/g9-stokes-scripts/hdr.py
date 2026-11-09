"""hdr.py FITS... : BMAJ, BMIN (arcsec), BPA, WSCIMGWG and CRVAL4 of each file."""

import sys

from astropy.io import fits

for f in sys.argv[1:]:
    h = fits.getheader(f)
    print(
        f"{f}: BMAJ {h.get('BMAJ', 0) * 3600:.4f} BMIN {h.get('BMIN', 0) * 3600:.4f} "
        f"BPA {h.get('BPA', 0):.3f} WSCIMGWG {h.get('WSCIMGWG', 0):.9e} CRVAL4 {h['CRVAL4']}"
    )
