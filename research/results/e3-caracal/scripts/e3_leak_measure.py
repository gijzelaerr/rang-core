"""Peak |Q|, |U|, |V| of the MFS images over peak I (E3-B leakage, research/e3-caracal.md 5):
    python e3_leak_measure.py OUTDIR OUT.json
Reads OUTDIR/leak-MFS-{I,Q,U,V}-image.fits (WSClean's names for -pol IQUV with
-join-channels). Peaks inside the inner quarter of the image (the calibrator
sits at the phase centre)."""
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

d = Path(sys.argv[1])
img = {s: np.squeeze(fits.getdata(d / f"leak-MFS-{s}-image.fits")) for s in "IQUV"}
n = img["I"].shape[-1]
c = slice(3 * n // 8, 5 * n // 8)
pi = float(np.nanmax(img["I"][c, c]))
res = {"peak_I": pi}
for s in "QUV":
    res[f"peak_abs_{s}"] = float(np.nanmax(np.abs(img[s][c, c])))
    res[f"{s}_over_I"] = res[f"peak_abs_{s}"] / pi
res["max_over_I"] = max(res[f"{s}_over_I"] for s in "QUV")
Path(sys.argv[2]).write_text(json.dumps(res, indent=1))
print(json.dumps(res))
