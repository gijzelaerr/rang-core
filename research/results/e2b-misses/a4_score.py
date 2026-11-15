"""Arm A4's scorer and rule (research/e2b-misses.md 9.9).

    python a4_score.py c6 OUT_JSON
    python a4_score.py score OUT_JSON

Measures as gate 3c's `dirty_linf` (`e2_score3c.py`, branch
fp-e2-acceptance): per channel 0000-0007 and MFS, per Stokes, max |a - b|
over the peak |I| of WSClean's dirty image of that channel; also with a 5 %
border excluded and over the inner two-thirds.
"""

import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

R = Path("D:/rang/outputs/e2-20261111-20-e2b")
P = Path("D:/rang/outputs/e2b-pastro-20261114/a4")
STOKES = ("I", "Q", "U", "V")
CHANS = [f"{i:04d}" for i in range(8)] + ["MFS"]
FIELDS = (("J1331+3030", "J1331p3030"), ("J1939-6342", "J1939m6342"), ("J1833-2103", "J1833m2103"))
EPS = ("1e-05", "1e-06", "1e-07")
TOL = 1e-6
HEADER_KEYS = ("CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "CRPIX1", "CRPIX2")


def _open(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, float).squeeze(), dict(h[0].header)


def linf(rang_file, wsc_file, peak_file):
    """{max, border5, inner, median_max} over channels and Stokes."""
    out = {"max": 0.0, "border5": 0.0, "inner": 0.0, "median_max": 0.0, "per_image": {}}
    for c in CHANS:
        peak = float(np.max(np.abs(_open(peak_file(c))[0])))
        for p in STOKES:
            a, ha = _open(rang_file(c, p))
            b, hb = _open(wsc_file(c, p))
            if a.shape != b.shape:
                raise SystemExit(f"shape differs: {c} {p}")
            for k in HEADER_KEYS:
                if not np.isclose(ha[k], hb[k], rtol=1e-9, atol=1e-12):
                    raise SystemExit(f"header {k} differs: {c} {p}")
            d = np.abs(a - b) / peak
            n = d.shape[0]
            out["per_image"][f"{c}-{p}"] = float(d.max())
            out["max"] = max(out["max"], float(d.max()))
            for key, m in (("border5", n // 20), ("inner", n // 6)):
                out[key] = max(out[key], float(d[m : n - m, m : n - m].max()))
            out["median_max"] = max(out["median_max"], float(np.median(d)))
    return out


def c6(out_json):
    name, tag = FIELDS[2]
    new_w = P / "wsclean" / f"{tag}-eps0.0001"
    new_r = P / "rang" / f"{tag}-eps0.0001"
    old_w = R / "wsclean3c-unit"
    old_r = R / "rang-run-moved" / "image" / name

    def wpeak(d, stem):
        return lambda c: d / f"{stem}-{c}-I-dirty.fits"

    res = {
        "tolerance": TOL,
        "wsclean_new_vs_archived": linf(
            lambda c, p: new_w / f"{tag}-dirty-{c}-{p}-dirty.fits",
            lambda c, p: old_w / f"{tag}-dirty-{c}-{p}-dirty.fits",
            wpeak(old_w, f"{tag}-dirty"),
        ),
        "rang_new_vs_archived": linf(
            lambda c, p: new_r / f"image-{c}-{p}-dirty.fits",
            lambda c, p: old_r / f"image-{c}-{p}-dirty.fits",
            wpeak(old_w, f"{tag}-dirty"),
        ),
    }
    for k in ("wsclean_new_vs_archived", "rang_new_vs_archived"):
        res[k].pop("per_image")
    res["met"] = all(res[k]["max"] <= TOL for k in ("wsclean_new_vs_archived", "rang_new_vs_archived"))
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


def score(out_json):
    res = {"tolerance": TOL, "fields": {}}
    for name, tag in FIELDS:
        f = {}
        for eps in EPS:
            w = P / "wsclean" / f"{tag}-eps{eps}"
            r = P / "rang" / f"{tag}-eps{eps}"
            f[eps] = linf(
                lambda c, p, r=r: r / f"image-{c}-{p}-dirty.fits",
                lambda c, p, w=w: w / f"{tag}-dirty-{c}-{p}-dirty.fits",
                lambda c, w=w: w / f"{tag}-dirty-{c}-I-dirty.fits",
            )
        f["r_1e-7_over_1e-5"] = f["1e-07"]["max"] / f["1e-05"]["max"]
        res["fields"][name] = f
    met_at = [e for e in EPS if all(res["fields"][n][e]["max"] <= TOL for n, _ in FIELDS)]
    rs = [res["fields"][n]["r_1e-7_over_1e-5"] for n, _ in FIELDS]
    if met_at:
        outcome = f"met at eps {met_at[0]} on all three fields: the dirty miss was the protocol's eps"
    elif all(x <= 0.1 for x in rs):
        outcome = "falls with eps, bound not reached at 1e-7: owner (finer eps or tolerance)"
    elif any(x > 0.5 for x in rs):
        outcome = "does not fall with eps on at least one field: edge difference, open a G task"
    else:
        outcome = "partial: reported, no conclusion"
    res["met_at"] = met_at
    res["outcome"] = outcome
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({n: {e: {k: v[e][k] for k in ("max", "border5", "inner")} for e in EPS}
                      for n, v in res["fields"].items()}, indent=1))  # fmt: skip
    print(outcome, rs)


def nosi(out_json):
    """A4b (9.11): WSClean -no-small-inversion against A4's GeMClean, J1833-2103, eps 1e-6."""
    tag, eps = "J1833m2103", "1e-06"
    r = P / "rang" / f"{tag}-eps{eps}"
    w = P / "wsclean" / f"{tag}-eps{eps}"
    n = P / "wsclean-nosi" / f"{tag}-eps{eps}"

    def rang_img(c, p):
        return r / f"image-{c}-{p}-dirty.fits"

    def wsc(d):
        return lambda c, p: d / f"{tag}-dirty-{c}-{p}-dirty.fits"

    def peak(d):
        return lambda c: d / f"{tag}-dirty-{c}-I-dirty.fits"

    res = {"tolerance": TOL}
    res["rang_vs_nosi"] = linf(rang_img, wsc(n), peak(n))
    res["rang_vs_si"] = linf(rang_img, wsc(w), peak(w))
    res["si_vs_nosi"] = linf(wsc(w), wsc(n), peak(n))
    for k in ("rang_vs_nosi", "rang_vs_si", "si_vs_nosi"):
        res[k].pop("per_image")
    f_nosi, f_si = res["rang_vs_nosi"]["max"], res["rang_vs_si"]["max"]
    if f_nosi <= TOL:
        outcome = "met: the edge difference is WSClean's small inversion"
    elif f_nosi <= 0.1 * f_si:
        outcome = "small inversion carries most of the edge excess; rest not attributed"
    else:
        outcome = "small inversion is not the cause; edge difference open"
    res["outcome"] = outcome
    Path(out_json).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"c6": c6, "score": score, "nosi": nosi}[sys.argv[1]](sys.argv[2])
