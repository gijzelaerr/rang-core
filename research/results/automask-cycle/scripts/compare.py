# SPDX-License-Identifier: MIT
"""automask-cycle (research/automask-cycle.md section 4): M1-M3 on two imagers' outputs.

compare.py OUT.json G_PREFIX W_PREFIX [NCHAN]
G_PREFIX and W_PREFIX are -name prefixes (GeMClean and WSClean), each with
<prefix>-MFS-residual.fits and <prefix>-000k-model.fits.
"""

import json
import sys

import numpy as np
from astropy.io import fits


def img(path):
    return np.asarray(fits.getdata(path), dtype=np.float64).squeeze()


def radler_sigma(x):
    v = x[np.isfinite(x)].astype(np.float32)
    m = np.median(v)
    return float(np.float32(1.4826022) * np.median(np.abs(v - m)))


def peak(x):
    i = int(np.nanargmax(np.abs(x)))
    y, xx = np.unravel_index(i, x.shape)
    return {
        "value": float(x.flat[i]),
        "abs": float(abs(x.flat[i])),
        "y": int(y),
        "x": int(xx),
    }


def main():
    out, gp, wp = sys.argv[1:4]
    nch = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    res = {}
    rg, rw = img(f"{gp}-MFS-residual.fits"), img(f"{wp}-MFS-residual.fits")
    pg, pw = peak(rg), peak(rw)
    pg["other"] = float(rw[pg["y"], pg["x"]])
    pw["other"] = float(rg[pw["y"], pw["x"]])
    d = rg - rw
    res["M1"] = {
        "gem_peak": pg,
        "wsc_peak": pw,
        "gem_sigma": radler_sigma(rg),
        "wsc_sigma": radler_sigma(rw),
        "diff_rms": float(np.sqrt(np.nanmean(d * d))),
        "diff_peak": peak(d),
    }
    mods = {}
    supp = {}
    for tag, p in (("gem", gp), ("wsc", wp)):
        ms = [img(f"{p}-{k:04d}-model.fits") for k in range(nch)]
        mods[tag] = ms
        nz = np.zeros(ms[0].shape, bool)
        for m in ms:
            nz |= np.isfinite(m) & (m != 0.0)
        supp[tag] = nz
    res["M2"] = {
        "flux_per_channel": {t: [float(np.nansum(m)) for m in mods[t]] for t in mods},
    }
    top = []
    mg = np.mean(mods["gem"], axis=0)
    for i in np.argsort(-np.abs(mg), axis=None)[:20]:
        y, x = np.unravel_index(int(i), mg.shape)
        top.append(
            {
                "y": int(y),
                "x": int(x),
                "gem": [float(m[y, x]) for m in mods["gem"]],
                "wsc": [float(m[y, x]) for m in mods["wsc"]],
            }
        )
    res["M2"]["top20_by_gem_mean"] = top
    res["M3"] = {
        "gem_support": int(supp["gem"].sum()),
        "wsc_support": int(supp["wsc"].sum()),
        "both": int((supp["gem"] & supp["wsc"]).sum()),
    }
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    m1 = res["M1"]
    print(
        f"M1 gem peak {pg['value']:.4e} at ({pg['y']},{pg['x']}) wsc there {pg['other']:.4e}; "
        f"wsc peak {pw['value']:.4e} at ({pw['y']},{pw['x']}) gem there {pw['other']:.4e}; "
        f"sigma gem {m1['gem_sigma']:.4e} wsc {m1['wsc_sigma']:.4e}; diff rms {m1['diff_rms']:.4e}"
    )
    print(
        f"M3 support gem {res['M3']['gem_support']} wsc {res['M3']['wsc_support']} both {res['M3']['both']}"
    )
    fl = res["M2"]["flux_per_channel"]
    print(
        "M2 flux gem",
        [round(v, 4) for v in fl["gem"]],
        "wsc",
        [round(v, 4) for v in fl["wsc"]],
    )


if __name__ == "__main__":
    main()
