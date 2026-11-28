# SPDX-License-Identifier: MIT
"""P1 of research/gate3c-averaging.md: E2-N's averaging loss predicted per
source from E2-N's own UVW, FLAG after apply and GeMClean's Briggs 0.5 MF
weights, against the archived arm A / arm U fluxes (section 7.1 of
gate3c-rerun.md).

    python p1_predict.py GEOM.npz G3C_A.json G3C_U.json OUT.json

GEOM.npz is e2n_geom.py's extraction (field 3, cross-correlations). For
n = 2 every non-empty group's factor has real part cos(pi x), x = tau dnu / c,
whether one or both channels are unflagged (the group is labelled with the
plain mean frequency), so p_c = sum_r W_rc cos(pi x_r) / sum_r W_rc exactly,
W_rc the row's gridding weight (data x imaging) in output channel c.
"""

import itertools
import json
import math
import sys
import time

import numpy as np
from rang import core_weights as cw

C = 299_792_458.0
N, SCALE_AS, NAVG, NOUT = 6144, 2.0, 2, 8
BINS = (0.0, 0.35, 0.7, 1.0, 1.4, 2.5)
TOL = 0.005


def mad(x):
    x = np.asarray(x)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def load_sources(path):
    d = json.load(open(path, encoding="utf-8"))
    c = d["compact"] if "compact" in d else d
    return {(s["x"], s["y"]): s for s in c["sources"]}


def main(geom, ga, gu, out):
    t0 = time.perf_counter()
    g = np.load(geom)
    uvw, frow = g["uvw"], g["flag_row"]
    nchan = int(g["nchan"])
    dnu = float(np.abs(g["width"]).mean())
    freq = g["freq"]
    flag = np.unpackbits(g["flag_xx"], axis=1)[:, :nchan].astype(bool)
    flag |= np.unpackbits(g["flag_yy"], axis=1)[:, :nchan].astype(bool)
    flag |= frow[:, None]
    good = (~flag).astype(np.float32)  # Stokes I unit weight per native sample (scale-free)
    del flag
    nrow = len(uvw)
    # arm A's averaged data weights and frequencies (spectral::average_channels)
    wa = good.reshape(nrow, nchan // NAVG, NAVG).sum(axis=2)
    fa = freq.reshape(-1, NAVG).mean(axis=1)
    scale = cw.pixel_scale_radians(SCALE_AS)
    pad = cw.padded_size(N)
    res = cw.imaging_weights(uvw, cw.wsclean_wavelengths(fa), wa, ~frow, "briggs", 0.5,
                             pad, pad, scale, return_grid=False)  # fmt: skip
    grid_w = wa * res["weights"]  # gridding weight: data x imaging
    nav = nchan // NAVG
    groups = [range(i * nav // NOUT, (i + 1) * nav // NOUT) for i in range(NOUT)]
    W = np.stack([grid_w[:, list(gr)].sum(axis=1) for gr in groups], axis=1).astype(np.float64)
    Wn = np.stack([wa[:, list(gr)].sum(axis=1) for gr in groups], axis=1).astype(np.float64)
    t_w = time.perf_counter() - t0
    sa, su = load_sources(ga), load_sources(gu)
    keys = [k for k in su if k in sa]
    u, v, w = uvw[:, 0], uvw[:, 1], uvw[:, 2]
    recs = []
    for k in keys:
        x, y = k
        l, m = -(x - N / 2) * scale, (y - N / 2) * scale
        tau = u * l + v * m + w * (math.sqrt(1 - l * l - m * m) - 1)
        f = np.cos(math.pi * tau * dnu / C)
        pc = (W * f[:, None]).sum(0) / W.sum(0)
        pn = (Wn * f[:, None]).sum(0) / Wn.sum(0)
        U = np.array(su[k]["rang_jy"])
        A = np.array(sa[k]["rang_jy"])
        recs.append({
            "x": x, "y": y, "radius_deg": su[k]["radius_deg"], "snr": su[k]["snr"],
            "measured": float(A.sum() / U.sum()),
            "predicted": float((pc * U).sum() / U.sum()),
            "predicted_natural": float((pn * U).sum() / U.sum()),
            "predicted_per_channel": pc.tolist(),
        })  # fmt: skip
    bins = []
    for lo, hi in itertools.pairwise(BINS):
        s = [r for r in recs if lo <= r["radius_deg"] < hi]
        mm = float(np.median([r["measured"] for r in s]))
        mp = float(np.median([r["predicted"] for r in s]))
        mn = float(np.median([r["predicted_natural"] for r in s]))
        bins.append({"deg": [lo, hi], "n": len(s), "median_measured": mm,
                     "median_predicted": mp, "median_predicted_natural": mn,
                     "diff": mm - mp, "met": abs(mm - mp) <= TOL})  # fmt: skip
    hi_snr = [r["measured"] - r["predicted"] for r in recs if r["snr"] >= 50]
    last = bins[-1]
    if all(b["met"] for b in bins):
        reading = "explained"
    elif 1 - last["median_predicted"] >= 0.5 * (1 - last["median_measured"]):
        reading = "partly explained"
    else:
        reading = "not explained"
    # BDA bound (section 3): visibility share that could be averaged at <= 1 % loss
    # at the 1.7 deg half-width in the worst direction (w-term left out).
    bl = np.hypot(u, v)
    r_hw = 0.5 * N * scale
    nvis = good.sum(axis=1)
    bda = {}
    for name, n, width in (("e2n_n2", 2, dnu), ("4096ch_n8", 8, dnu / 4)):
        xx = bl * r_hw * width / C
        s = np.sin(math.pi * xx)
        dn = np.where(np.abs(s) < 1e-12, 1.0, np.sin(n * math.pi * xx) / (n * np.where(s == 0, 1, s)))
        ok = (1 - dn) <= 0.01
        share = float(nvis[ok].sum() / nvis.sum())
        bda[name] = {"factor": n, "native_width_hz": width, "share_averageable": share,
                     "visibility_memory_saved": share * (1 - 1 / n)}  # fmt: skip
    rec = {
        "tolerance": TOL, "reading": reading, "bins": bins,
        "ge50sigma": {"n": len(hi_snr), "median": float(np.median(hi_snr)), "robust_scatter": mad(hi_snr)},
        "native_width_hz": dnu, "rows": nrow, "unflagged_fraction": float(good.mean()),
        "bda_bound": bda, "seconds": {"weights": t_w, "total": time.perf_counter() - t0},
        "sources": recs,
    }  # fmt: skip
    json.dump(rec, open(out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: rec[k] for k in ("reading", "bins", "ge50sigma", "bda_bound", "seconds")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
