# SPDX-License-Identifier: MIT
"""P3 of research/gate3c-averaging.md: each imager against a noise-matched
truth on the simulated sky.

    python p3_score.py SKY.json NOISE_DIRTY_PREFIX OUT.json NAME=PREFIX ...

Each PREFIX names an arm's WSClean-style images (PREFIX-0000-image.fits ...,
PREFIX-MFS-residual.fits). The first arm named W1 sets sigma (1.4826 MAD of
its MFS residual over the inner two-thirds, as e2_score3c_a) and the beam for
isolation. Points: truth positions, isolated when no other component lies
within 5 beams (the scorer's rule, on the truth list), kept at >= 10 sigma.
Flux per arm: e2_score3c_a.flux_at per channel, summed. Truth per channel:
S + the same fit on the noise twin's dirty image (model zero), summed.
"""

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))
from e1b_score import _open, fit_psf_beam  # noqa: E402
from e2_score3c_a import channel_set, flux_at, inner, mad  # noqa: E402

NCH, SCALE_AS, RADIUS = 8, 2.0, 0.7
SNR_BINS = (10, 15, 25, 50, 200, math.inf)


def stats(v):
    v = np.asarray(v)
    return {"n": len(v), "median": float(np.median(v)), "robust_scatter": float(mad(v))} if len(v) else {"n": 0}


def main(sky, noise, out, arms):
    comps = json.loads(Path(sky).read_text(encoding="utf-8"))
    names = [a.split("=", 1)[0] for a in arms]
    prefixes = dict(a.split("=", 1) for a in arms)
    w1res, h = _open(Path(f"{prefixes['W1']}-MFS-residual.fits"))[:2]
    n = w1res.shape[0]
    sigma = mad(w1res[inner(w1res.shape)])
    bmaj = h["BMAJ"] / abs(h["CDELT2"])
    xy = np.array([[n // 2 + c["dx"], n // 2 + c["dy"]] for c in comps])
    pts = []
    for i, c in enumerate(comps):
        if c["kind"] != "point":
            continue
        d = np.hypot(*(xy - xy[i]).T)
        d[i] = np.inf
        if d.min() < 5 * bmaj:
            continue
        snr = c["flux"] / sigma
        rad = math.hypot(c["dx"], c["dy"]) * SCALE_AS / 3600
        if snr >= 10 and rad <= RADIUS:
            pts.append((i, float(xy[i, 0]), float(xy[i, 1]), snr, rad))
    chans = {k: channel_set(lambda s, p=prefixes[k]: f"{p}-{s}", NCH) for k in names}
    noise_ch = []
    for k in range(NCH):
        d = _open(Path(f"{noise}-{k:04d}-dirty.fits"))[0]
        beam = fit_psf_beam(_open(Path(f"{noise}-{k:04d}-psf.fits"))[0])
        noise_ch.append({"model": np.zeros_like(d), "resid": d, "beam": beam})
    rows = []
    for i, x, y, snr, rad in pts:
        r = {"i": i, "x": x, "y": y, "snr": snr, "radius_deg": rad, "flux": comps[i]["flux"]}
        r["truth"] = sum(comps[i]["flux"] + flux_at(ch, x, y) for ch in noise_ch)
        for k in names:
            r[k] = sum(flux_at(ch, x, y) for ch in chans[k])
        rows.append(r)
    pairs = [(a, "truth") for a in names] + list(itertools.combinations(names, 2))
    res = {"sigma_jy": sigma, "beam_major_pix": bmaj, "n_points": len(rows), "pairs": {}}
    for a, b in pairs:
        key = f"{a}/{b}"
        v = [r[a] / r[b] for r in rows]
        rec = {"all": stats(v)}
        for lo, hi in itertools.pairwise(SNR_BINS):
            vv = [q for q, r in zip(v, rows, strict=True) if lo <= r["snr"] < hi]
            rec[f"snr_{lo}_{hi}"] = stats(vv)
        res["pairs"][key] = rec
    s = {k: v["all"].get("robust_scatter") for k, v in res["pairs"].items()}
    if "G/truth" in s and "W1/truth" in s:
        g, w = s["G/truth"], s["W1/truth"]
        if g <= 1.2 * w and g >= w / 1.2:
            reading = "HB holds, equal imagers: null, additive deconvolution disagreement, not a rang defect"
        elif g > 1.2 * w:
            reading = "GeMClean worse"
            if "Gdeep/truth" in s and "Wdeep/truth" in s and s["Gdeep/truth"] <= 1.2 * s["Wdeep/truth"]:
                reading += "; cause named as depth (G-deep within 1.2x of W-deep)"
        else:
            reading = "GeMClean better: the excess is WSClean's"
        res["reading"] = reading
    res["rows"] = rows
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res["pairs"].items():
        print(f"{k:16s} n {v['all']['n']} median {v['all']['median']:.4f} scatter {100 * v['all']['robust_scatter']:.2f} %")
    print("sigma", sigma, "reading:", res.get("reading"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
