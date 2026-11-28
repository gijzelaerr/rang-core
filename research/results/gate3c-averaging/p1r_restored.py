# SPDX-License-Identifier: MIT
"""P1' of research/gate3c-averaging.md (amendment A1, post hoc): the
restored-peak predictor p' = exp(-c^T Sigma^-1 c / (8 pi^2)), c = pi (dnu/nu)
(l, m), Sigma the restoring beam's image-plane covariance per output channel
(WSClean's fitted beams from the archived ws-n-clean.out), against the
archived A/U fluxes already paired in P1's output.

    python p1r_restored.py GEOM.npz P1.json WS_CLEAN.out OUT.json
"""

import itertools
import json
import math
import re
import sys

import numpy as np

N, SCALE_AS, NOUT = 6144, 2.0, 8
BINS = (0.0, 0.35, 0.7, 1.0, 1.4, 2.5)
TOL = 0.005
AS = math.pi / (180 * 3600)


def beams(path):
    pat = re.compile(r"Fitting beam\.\.\. major=([\d.]+)'', minor=([\d.]+)'', PA=([-\d.]+) deg")
    got = [tuple(map(float, m.groups())) for m in pat.finditer(open(path, encoding="utf-8").read())]
    return got[:NOUT]  # the 8 channel beams; the 9th is the MFS image's


def inv_cov(major, minor, pa_deg):
    s = 1 / (2 * math.sqrt(2 * math.log(2)))
    smaj, smin = major * AS * s, minor * AS * s
    pa = math.radians(pa_deg)
    e1 = np.array([math.sin(pa), math.cos(pa)])  # major axis in (l east, m north)
    e2 = np.array([math.cos(pa), -math.sin(pa)])
    return np.outer(e1, e1) / smaj**2 + np.outer(e2, e2) / smin**2


def main(geom, p1, wsout, out):
    g = np.load(geom)
    freq, width = g["freq"], np.abs(g["width"])
    dnu = float(width.mean())
    nchan = len(freq)
    centres = []
    for i in range(NOUT):
        k = range(i * nchan // NOUT, (i + 1) * nchan // NOUT)
        lo = min(freq[j] - width[j] / 2 for j in k)
        hi = max(freq[j] + width[j] / 2 for j in k)
        centres.append(0.5 * (lo + hi))
    b = beams(wsout)
    inv = [inv_cov(*x) for x in b]
    rec = json.load(open(p1, encoding="utf-8"))
    scale = SCALE_AS * AS
    for s in rec["sources"]:
        l, m = -(s["x"] - N / 2) * scale, (s["y"] - N / 2) * scale
        # P1's per-channel weights for U's fluxes: recover U_c from P1 inputs is not stored,
        # so weight channels by P1's own convention: p = sum p_c U_c / sum U_c. P1 stored
        # predicted_per_channel and predicted; U_c are re-read below from the score file.
        pc = []
        for c, nu in enumerate(centres):
            v = math.pi * dnu / nu * np.array([l, m])
            pc.append(math.exp(-float(v @ inv[c] @ v) / (8 * math.pi**2)))
        s["restored_per_channel"] = pc
    return rec, centres, b


if __name__ == "__main__":
    geom, p1, wsout, gu, out = sys.argv[1:6]
    rec, centres, b = main(geom, p1, wsout, out)
    du = json.load(open(gu, encoding="utf-8"))
    cu = du["compact"] if "compact" in du else du
    su = {(s["x"], s["y"]): s for s in cu["sources"]}
    for s in rec["sources"]:
        U = np.array(su[(s["x"], s["y"])]["rang_jy"])
        s["predicted_restored"] = float((np.array(s["restored_per_channel"]) * U).sum() / U.sum())
    bins = []
    for lo, hi in itertools.pairwise(BINS):
        ss = [s for s in rec["sources"] if lo <= s["radius_deg"] < hi]
        mm = float(np.median([s["measured"] for s in ss]))
        mp = float(np.median([s["predicted_restored"] for s in ss]))
        bins.append({"deg": [lo, hi], "n": len(ss), "median_measured": mm,
                     "median_predicted_restored": mp, "diff": mm - mp,
                     "met": abs(mm - mp) <= TOL})  # fmt: skip
    hi_snr = [s["measured"] - s["predicted_restored"] for s in rec["sources"] if s["snr"] >= 50]
    last = bins[-1]
    if all(x["met"] for x in bins):
        reading = "explained"
    elif 1 - last["median_predicted_restored"] >= 0.5 * (1 - last["median_measured"]):
        reading = "partly explained"
    else:
        reading = "not explained"
    res = {"label": "post hoc (A1), measurement seen", "tolerance": TOL, "reading": reading,
           "bins": bins, "channel_centres_hz": centres, "beams_wsclean": b,
           "ge50sigma": {"n": len(hi_snr), "median": float(np.median(hi_snr)),
                         "robust_scatter": float(1.4826 * np.median(np.abs(np.array(hi_snr) - np.median(hi_snr))))},
           "sources": [{k: s[k] for k in ("x", "y", "radius_deg", "snr", "measured", "predicted",
                                          "predicted_restored")} for s in rec["sources"]]}  # fmt: skip
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: res[k] for k in ("reading", "bins", "ge50sigma")}, indent=1))
