# SPDX-License-Identifier: MIT
"""score.py RUN: criteria M1, C and O of research/gemclean-ms-mask.md (section 4), mechanically.

GeMClean from $O/runs/g/RUN/g-*, WSClean from $O/runs/wsclean/RUN/w-*; the run's mask from
$O/masks. Prints the verdicts and writes $O/runs/score-RUN.json.
"""

import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

O = Path(os.environ.get("MSM_OUT", "D:/rang/outputs/gemclean-ms-mask-20261117"))
MASK = {
    "RM": "h4-points.fits",
    "RH": "h4-points.fits",
    "PM": "source-mask.fits",
    "RM1": "h4-points.fits",
    "PM1": "source-mask.fits",
}
MULTI = {"RM": True, "RH": False, "PM": True, "RM1": True, "PM1": True}


def img(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, dtype=np.float64).squeeze(), h[0].header


def regions(model, mask):
    peak = np.abs(model).max()
    out = ~mask
    return {
        "total": float(model.sum()),
        "F_in": float(model[mask].sum()),
        "F_out": float(model[out].sum()),
        "N_out": float(model[out & (model < 0)].sum()),
        "abs_out": float(np.abs(model[out]).sum()),
        "negative": float(model[model < 0].sum()),
        "nonzero": int(np.count_nonzero(model)),
        "nonzero_out": int(np.count_nonzero(model[out])),
        "big_out": int((np.abs(model[out]) > 1e-6 * peak).sum()),
    }


def scales_wsclean(log):
    """WSClean's per-scale components and flux (the last 'Scale info' style lines)."""
    rows = {}
    for m in re.finditer(
        r"Scale\s+([\d.]+)[^\n]*?(\d+) components?[^\n]*?([-\d.e+]+) Jy", log
    ):
        rows[m.group(1)] = (int(m.group(2)), float(m.group(3)))
    return rows


def main():
    run = sys.argv[1]
    gdir, wdir = O / "runs" / "g" / run, O / "runs" / "wsclean" / run
    mask = img(O / "masks" / MASK[run])[0] != 0
    mg, _ = img(gdir / "g-model.fits")
    mw, hw = img(wdir / "w-model.fits")
    rw, _ = img(wdir / "w-residual.fits")
    n = rw.shape[0]
    c = rw[n // 6 : 5 * n // 6, n // 6 : 5 * n // 6]
    sigma = 1.4826 * float(np.median(np.abs(c - np.median(c))))
    wlog = (wdir / "log.txt").read_text(errors="replace")
    unit = {"Jy": 1.0, "mJy": 1e-3, "µJy": 1e-6}
    level = None
    if run.endswith("1"):
        # Post hoc (section 7): sigma fixed in advance, and the two first-loop levels.
        if run == "RM1":
            sigma = 0.000539304861787241  # RH's WSClean sigma
        else:
            m = re.search(
                r"Estimated standard deviation of background noise: ([\d.]+) (\S+)",
                wlog,
            )
            sigma = float(m.group(1)) * unit[m.group(2)]
        m = re.search(r"major iteration threshold=([\d.]+) (\S+)", wlog)
        lw = float(m.group(1)) * unit[m.group(2)]
        rep = json.loads((gdir / "g-report.json").read_text())
        lg = (1 - rep["settings"]["mgain"]) * rep["run"]["cycles"][0]["peak_start"]
        level = {
            "w": lw,
            "g": lg,
            "rel": abs(lg - lw) / max(lg, lw),
            "ok": abs(lg - lw) <= 0.02 * max(lg, lw),
            "g_majors": len(rep["run"]["cycles"]),
        }
    delta = abs(hw["CDELT1"])
    omega = math.pi / (4 * math.log(2)) * hw["BMAJ"] * hw["BMIN"] / delta**2
    eps = {
        "in": 3 * sigma * math.sqrt(mask.sum() / omega),
        "out": 3 * sigma * math.sqrt((~mask).sum() / omega),
    }
    G, W = regions(mg, mask), regions(mw, mask)
    picks = json.loads((gdir / "g-mask.json").read_text())
    m1 = picks.get("fits_outside_picks") == 0
    res = {
        "run": run,
        "sigma": sigma,
        "omega_px": omega,
        "eps": eps,
        "g": G,
        "w": W,
        "g_mask_json": picks,
        "M1": m1,
        "level": level,
    }
    if not MULTI[run]:
        res["C"] = G["nonzero_out"] == 0 and W["nonzero_out"] == 0
    else:
        o = {}
        for key, reg in (("F_in", "in"), ("F_out", "out"), ("N_out", "out")):
            bound = 0.02 * abs(W[key]) + math.sqrt(2) * eps[reg]
            o[key] = {
                "g": G[key],
                "w": W[key],
                "diff": G[key] - W[key],
                "bound": bound,
                "pass": abs(G[key] - W[key]) <= bound,
            }
        res["O"] = o
        res["O_pass"] = all(v["pass"] for v in o.values())
    glog = (gdir / "log.txt").read_text(errors="replace")
    res["g_scales"] = re.findall(
        r"multiscale: scale ([\d.]+) px.*?(\d+) components, ([-\d.]+) Jy", glog
    )
    res["g_summary"] = [
        l for l in glog.splitlines() if "components," in l and "major" in l
    ]
    res["w_diverged"] = "diverged" in wlog
    res["g_end"] = re.findall(r"end (\w+)", glog)[:1]
    res["w_majors"] = len(re.findall(r"== Deconvolving \(", wlog)) or wlog.count(
        "Major iteration"
    )
    res["w_tail"] = [l for l in wlog.splitlines() if "Iteration" in l and "Jy" in l][
        -2:
    ]
    (O / "runs" / f"score-{run}.json").write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {
                k: res[k]
                for k in res
                if k
                in (
                    "run",
                    "sigma",
                    "M1",
                    "C",
                    "O",
                    "O_pass",
                    "level",
                    "w_diverged",
                    "g_end",
                )
            },
            indent=1,
        )
    )
    for side in ("g", "w"):
        print(
            side,
            {
                k: (round(v, 5) if isinstance(v, float) else v)
                for k, v in res[side].items()
            },
        )


if __name__ == "__main__":
    main()
