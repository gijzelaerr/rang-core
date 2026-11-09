"""Post hoc: why the control image's compact-source ratios sit at 1.03 (scorer
not validated, 4.3). Per source in the control MFS image: the model's summed
components within 2 pixels, the residual at the position, and the restored fit."""

import json
import sys

import e1_score as S
import numpy as np

ctx = S.Ctx(sys.argv[1], "full")
d = ctx.run / "control" / "image"
comps = ctx.tj["target_components"]
img, h, w = S._open(d / "image-MFS-image.fits")
mod, _, _ = S._open(d / "image-MFS-model.fits")
res, _, _ = S._open(d / "image-MFS-residual.fits")
psf, hp, _ = S._open(d / "image-MFS-psf.fits")
out = {
    "bmaj_bmin_arcsec": [h["BMAJ"] * 3600, h["BMIN"] * 3600],
    "psf_peak": float(psf.max()),
    "rows": [],
}
for k in S.ISOLATED[:20]:
    c = comps[k]
    x, y = w.celestial.world_to_pixel_values(c["ra_deg"], c["dec_deg"])
    ix, iy = round(float(x)), round(float(y))
    s_mfs = float(np.mean(c["flux"] * (ctx.freq / c["ref_freq_hz"]) ** c["alpha"]))
    out["rows"].append(
        {
            "index": k,
            "truth_mfs": s_mfs,
            "model_sum": float(mod[iy - 2 : iy + 3, ix - 2 : ix + 3].sum() / s_mfs),
            "residual": float(res[iy, ix] / s_mfs),
            "restored_peak": float(img[iy - 1 : iy + 2, ix - 1 : ix + 2].max() / s_mfs),
            "fit": S.fit_point(img, h, w, c["ra_deg"], c["dec_deg"])[0] / s_mfs,
        }
    )
print(json.dumps(out, indent=1))
