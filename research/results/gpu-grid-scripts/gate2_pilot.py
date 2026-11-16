"""Gate 2 on the pilot-512 (research/gpu-grid.md section 4): no truth, so the restored image's
inner difference against sigma (the CPU residual's inner rms), its largest difference against
100 µJy, and the total model flux to 1e-3 relative. Usage: gate2_pilot.py OUT_JSON"""
import json
import sys
from pathlib import Path

import numpy as np
from rang.core_imaging import read_fits

O = Path("D:/rang/outputs/20261116-gpu-grid")


def inner(a):
    n = a.shape[-1]
    lo, hi = n // 6, n - n // 6
    return a[..., lo:hi, lo:hi]


get = lambda p: np.asarray(read_fits(p)[0], dtype=float)
ci, gi = get(O / "base/pilot-coarse-image.fits"), get(O / "gate2/gpu/pilot-coarse-image.fits")
cr, gr = get(O / "base/pilot-coarse-residual.fits"), get(O / "gate2/gpu/pilot-coarse-residual.fits")
cm, gm = get(O / "base/pilot-coarse-model.fits"), get(O / "gate2/gpu/pilot-coarse-model.fits")
sigma = float(np.sqrt(np.mean(inner(cr) ** 2)))
d = inner(gi - ci)
out = {
    "sigma_jy": sigma,
    "image_rms_over_sigma": float(np.sqrt(np.mean(d**2))) / sigma,
    "image_linf_jy": float(np.abs(d).max()),
    "model_flux_cpu": float(cm.sum()),
    "model_flux_gpu": float(gm.sum()),
    "model_flux_rel": float(abs(gm.sum() - cm.sum()) / abs(cm.sum())),
    "residual_rms_cpu": sigma,
    "residual_rms_gpu": float(np.sqrt(np.mean(inner(gr) ** 2))),
}
out["passes"] = out["image_rms_over_sigma"] <= 0.1 and out["image_linf_jy"] <= 1e-4 and out["model_flux_rel"] <= 1e-3
print(json.dumps(out, indent=1))
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
