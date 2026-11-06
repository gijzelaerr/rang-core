"""score.py TAG SKY... : criteria B, C, D and F of research/g3-spectral.md, mechanically.

GeMClean runs are read from runs/TAG/<sky>-<cfg>/g-*, WSClean's from runs/wsclean/<sky>-<cfg>/w-*,
the truth from data/<sky>.json (examples/g3_spectral_simulate.py). Prints one block per sky and
writes runs/TAG/score-<sky>.json.  `score.py avg TAG` scores criterion E.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

O = Path("/mnt/d/rang/outputs/20261106-g3-spectral")
NU0 = 1.2e9
R_POINT = 6.0


def img(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, dtype=np.float64).squeeze(), dict(h[0].header)


def gname(tag, sky, cfg, part, kind):
    return O / "runs" / tag / f"{sky}-{cfg}" / f"g-{part}{kind}.fits"


def wname(sky, cfg, part, kind):
    return O / "runs" / "wsclean" / f"{sky}-{cfg}" / f"w-{part}{kind}.fits"


def parts(n):
    return [f"{k:04d}-" for k in range(n)] + ["MFS-"]


def nout(cfg):
    return {"C1": 8, "C2": 8, "C3": 4, "C4": 3, "A4": 4, "P4": 4}.get(cfg, 1)


def inner(a):
    n = a.shape[0]
    lo, hi = n // 6, n - n // 6
    return a[lo:hi, lo:hi]


def mad_sigma(a):
    a = a.ravel()
    return 1.4826 * float(np.median(np.abs(a - np.median(a))))


# -- B: dirty images and PSFs ------------------------------------------------------------


def crit_b(tag, sky, cfg, g=None, w=None):
    g = g or (lambda part, kind: gname(tag, sky, cfg, part, kind))
    w = w or (lambda part, kind: wname(sky, cfg, part, kind))
    n = nout(cfg)
    rows, ok = [], True
    for part in parts(n) if n > 1 else [""]:
        row = {"part": part.rstrip("-") or "single"}
        for kind in ("psf", "dirty"):
            a, ha = img(g(part, kind))
            b, hb = img(w(part, kind))
            if kind == "psf":
                scale = float(np.abs(b).max())
            else:
                scale = float(np.abs(b).max())
            d = float(np.abs(a - b).max()) / scale
            row[f"{kind}_max_rel"] = d
            ok &= d <= 1e-5
            if kind == "dirty":
                for key in ("WSCIMGWG", "CRVAL3", "CDELT3"):
                    va, vb = float(ha[key]), float(hb[key])
                    rel = abs(va - vb) / abs(vb)
                    row[f"{key}_rel"] = rel
                    ok &= rel <= (1e-6 if key == "WSCIMGWG" else 1e-9)
        rows.append(row)
    # Every file WSClean wrote of the five kinds exists under GeMClean's name.
    wdir = wname(sky, cfg, "", "x").parent
    missing = []
    for f in sorted(wdir.glob("w-*.fits")):
        kind = f.stem.rsplit("-", 1)[-1]
        if kind in ("dirty", "psf", "model", "residual", "image"):
            if not (gname(tag, sky, cfg, "", "x").parent / ("g" + f.name[1:])).exists():
                missing.append(f.name)
    ok &= not missing
    return {"pass": bool(ok), "rows": rows, "missing": missing}


# -- C: truth ----------------------------------------------------------------------------


def channel_truth(comp, groups, freq):
    s = np.asarray(comp["flux_per_channel"])
    return np.array([s[g].mean() for g in groups])


def groups_of(nchan, n):
    return [list(range(i * nchan // n, (i + 1) * nchan // n)) for i in range(n)]


def fit_spectrum(f, nu, sigma):
    """ln F = a + alpha lnx + beta ln^2 x, weights 1/(sigma/F)^2; (S0, alpha, beta, se_alpha, se_beta)."""
    if np.any(f <= 0):
        return None
    x = np.log(nu / NU0)
    y = np.log(f)
    s = sigma / f
    a = np.stack([np.ones_like(x), x, x * x], axis=1) / s[:, None]
    coef, *_ = np.linalg.lstsq(a, y / s, rcond=None)
    cov = np.linalg.inv(a.T @ a)
    return {
        "S0": float(math.exp(coef[0])),
        "alpha": float(coef[1]),
        "beta": float(coef[2]),
        "se_alpha": float(math.sqrt(cov[1, 1])),
        "se_beta": float(math.sqrt(cov[2, 2])),
    }


def aperture(comp, size):
    yy, xx = np.mgrid[0:size, 0:size]
    r = R_POINT if comp["kind"] == "point" else 2.0 * comp["fwhm_px"]
    return (xx - comp["x"]) ** 2 + (yy - comp["y"]) ** 2 <= r * r


def crit_c(tag, sky, cat):
    cfg, n = "C1", 8
    size = cat["image"]["size"]
    groups = groups_of(cat["nchan"], n)
    nu = np.array([img(wname(sky, cfg, f"{k:04d}-", "psf"))[1]["CRVAL3"] for k in range(n)])
    wk = np.array([img(wname(sky, cfg, f"{k:04d}-", "dirty"))[1]["WSCIMGWG"] for k in range(n)])
    sigma_mfs = mad_sigma(inner(img(wname(sky, cfg, "MFS-", "residual"))[0]))
    sigma_k = sigma_mfs * np.sqrt(wk.sum() / wk)
    models = {
        "gemclean": [img(gname(tag, sky, cfg, f"{k:04d}-", "model"))[0] for k in range(n)],
        "wsclean": [img(wname(sky, cfg, f"{k:04d}-", "model"))[0] for k in range(n)],
    }
    out = {"sigma_mfs": sigma_mfs, "nu_hz": nu.tolist(), "weights": wk.tolist(), "sources": []}
    for i, comp in enumerate(cat["components"]):
        mask = aperture(comp, size)
        t = fit_spectrum(channel_truth(comp, groups, nu), nu, sigma_k)
        rec = {"index": i, "kind": comp["kind"], "truth": t, "snr": t["S0"] / sigma_mfs}
        for who, m in models.items():
            f = np.array([mk[mask].sum() for mk in m])
            e = fit_spectrum(f, nu, sigma_k)
            rec[who] = {"flux": f.tolist(), "fit": e}
            if e is None:
                rec[who]["pass"] = False
                continue
            ds = e["S0"] / t["S0"] - 1
            da = e["alpha"] - t["alpha"]
            db = e["beta"] - t["beta"]
            rec[who].update({"dS": ds, "dalpha": da, "dbeta": db})
            if comp["kind"] == "point":
                ok = abs(ds) <= 0.02 + 3 / rec["snr"] and abs(da) <= 0.03 + 3 * e["se_alpha"]
                if comp["beta"] != 0:
                    ok &= abs(db) <= 0.1 + 3 * e["se_beta"]
            else:
                ok = abs(ds) <= 0.05 and abs(da) <= 0.1
            rec[who]["pass"] = bool(ok)
        out["sources"].append(rec)
    verdict = {}
    pts = [r for r in out["sources"] if r["kind"] == "point" and r["snr"] >= 200]
    for who in ("gemclean", "wsclean"):
        passed = [r for r in pts if r[who]["pass"]]
        das = [abs(r[who]["dalpha"]) for r in pts if r[who]["fit"]]
        dss = [abs(r[who]["dS"]) for r in pts if r[who]["fit"]]
        verdict[who] = {
            "scored_points": len(pts),
            "passed": len(passed),
            "failed": len(pts) - len(passed),
            "fraction": len(passed) / len(pts) if pts else float("nan"),
            "median_abs_dalpha": float(np.median(das)) if das else float("nan"),
            "median_abs_dS": float(np.median(dss)) if dss else float("nan"),
        }
    g, w = verdict["gemclean"], verdict["wsclean"]
    points_ok = (
        g["fraction"] >= 0.9
        and g["median_abs_dalpha"] <= w["median_abs_dalpha"] + 0.01
        and g["median_abs_dS"] <= w["median_abs_dS"] + 0.005
        and g["failed"] <= w["failed"] + 1
    )
    gauss_ok = True
    for r in out["sources"]:
        if r["kind"] != "gaussian":
            continue
        gr, wr = r["gemclean"], r["wsclean"]
        ok = gr["pass"]
        if not ok and gr["fit"] and not wr["pass"] and wr["fit"]:
            ok = abs(gr["dS"]) <= abs(wr["dS"]) + 0.03 and abs(gr["dalpha"]) <= abs(wr["dalpha"]) + 0.05
        r["gaussian_pass"] = bool(ok)
        gauss_ok &= ok
    out["verdict"] = verdict
    out["pass"] = bool(points_ok and gauss_ok)
    out["points_pass"] = bool(points_ok)
    out["gaussians_pass"] = bool(gauss_ok)
    return out


# -- D: MFS images against WSClean, relative to C0 -------------------------------------


def gaussian_kernel(size, bmaj_deg, bmin_deg, bpa_deg, scale_deg):
    """Unit-peak elliptical Gaussian on a size x size grid centred on (size/2, size/2),
    FITS frame (x along axis 1, east is -x, PA from north towards east)."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    dx, dy = xx - size // 2, yy - size // 2
    pa = math.radians(bpa_deg)
    umaj = (-math.sin(pa), math.cos(pa))
    umin = (math.cos(pa), math.sin(pa))
    a = bmaj_deg / scale_deg
    b = bmin_deg / scale_deg
    pmaj = dx * umaj[0] + dy * umaj[1]
    pmin = dx * umin[0] + dy * umin[1]
    return np.exp(-4 * math.log(2) * ((pmaj / a) ** 2 + (pmin / b) ** 2))


def restore(model, kernel):
    n = model.shape[0]
    m = 2 * n
    fm = np.fft.rfft2(np.pad(model, ((0, n), (0, n))))
    k = np.zeros((m, m))
    k[:n, :n] = kernel
    k = np.roll(k, (-(n // 2), -(n // 2)), axis=(0, 1))
    return np.fft.irfft2(fm * np.fft.rfft2(k), s=(m, m))[:n, :n]


def false_flux(model, cat):
    size = model.shape[0]
    keep = np.zeros(model.shape, bool)
    for c in cat["components"]:
        keep |= aperture(c, size)
    return float(model[~keep].sum())


def mfs_gap(tag, sky, cfg, cat):
    part = "MFS-" if nout(cfg) > 1 else ""
    wres, wh = img(wname(sky, cfg, part, "residual"))
    gres, _ = img(gname(tag, sky, cfg, part, "residual"))
    wmod, _ = img(wname(sky, cfg, part, "model"))
    gmod, _ = img(gname(tag, sky, cfg, part, "model"))
    scale = abs(float(wh["CDELT2"]))
    kern = gaussian_kernel(wres.shape[0], float(wh["BMAJ"]), float(wh["BMIN"]), float(wh["BPA"]), scale)
    rg = restore(gmod, kern) + gres
    rw = restore(wmod, kern) + wres
    sigma = mad_sigma(inner(wres))
    d = inner(rg - rw)
    return {
        "d_rms": float(np.sqrt(np.mean(d * d)) / sigma),
        "d_max": float(np.abs(d).max()),
        "ff_g": false_flux(gmod, cat),
        "ff_w": false_flux(wmod, cat),
        "sigma": sigma,
    }


def crit_d(tag, sky, cat):
    base = mfs_gap(tag, sky, "C0", cat)
    base["dff"] = abs(base["ff_g"] - base["ff_w"])
    out = {"C0": base}
    ok = True
    for cfg in ("C1", "C2", "C3"):
        m = mfs_gap(tag, sky, cfg, cat)
        m["dff"] = abs(m["ff_g"] - m["ff_w"])
        m["bound_rms"] = max(1.5 * base["d_rms"], base["d_rms"] + 0.1)
        m["bound_max"] = max(1.5 * base["d_max"], base["d_max"] + 1e-4)
        m["bound_dff"] = base["dff"] + 1e-3
        m["pass"] = bool(
            m["d_rms"] <= m["bound_rms"] and m["d_max"] <= m["bound_max"] and m["dff"] <= m["bound_dff"]
        )
        ok &= m["pass"]
        out[cfg] = m
    out["pass"] = bool(ok)
    return out


# -- F: memory ---------------------------------------------------------------------------


def rss(path):
    for line in Path(path).read_text().splitlines():
        if "Maximum resident" in line:
            return int(line.split(":")[1]) * 1024
    return None


def crit_f(tag, sky):
    out = {}
    for cfg in ("C0", "C1", "C2", "C3", "C4"):
        g = O / "runs" / tag / f"{sky}-{cfg}" / "time.txt"
        w = O / "runs" / "wsclean" / f"{sky}-{cfg}" / "time.txt"
        out[cfg] = {"gemclean": rss(g) if g.exists() else None, "wsclean": rss(w) if w.exists() else None}
    out["pass"] = all(v["gemclean"] is None or v["gemclean"] <= 24e9 for v in out.values())
    return out


def score(tag, sky):
    cat = json.loads((O / "data" / f"{sky}.json").read_text())
    res = {"sky": sky, "tag": tag}
    res["B"] = {cfg: crit_b(tag, sky, cfg) for cfg in ("C1", "C3", "C4")}
    res["B"]["pass"] = all(v["pass"] for v in res["B"].values() if isinstance(v, dict))
    res["C"] = crit_c(tag, sky, cat)
    res["D"] = crit_d(tag, sky, cat)
    res["F"] = crit_f(tag, sky)
    (O / "runs" / tag / f"score-{sky}.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


def show(res):
    s = res["sky"]
    print(f"== {s}")
    for cfg in ("C1", "C3", "C4"):
        b = res["B"][cfg]
        worst = {k: max(r.get(k, 0) for r in b["rows"]) for k in ("psf_max_rel", "dirty_max_rel", "WSCIMGWG_rel", "CRVAL3_rel", "CDELT3_rel")}
        print(f"B {cfg}: {'pass' if b['pass'] else 'FAIL'} " + " ".join(f"{k} {v:.2e}" for k, v in worst.items()) + (f" missing {b['missing']}" if b["missing"] else ""))
    c = res["C"]
    for who, v in c["verdict"].items():
        print(f"C {who}: {v['passed']}/{v['scored_points']} points pass, median |dalpha| {v['median_abs_dalpha']:.4f}, median |dS| {v['median_abs_dS']:.4f}")
    for r in c["sources"]:
        if r["kind"] == "gaussian":
            gr, wr = r["gemclean"], r["wsclean"]
            print(f"  gaussian {r['index']}: G dS {gr.get('dS', float('nan')):+.4f} dalpha {gr.get('dalpha', float('nan')):+.4f}; W dS {wr.get('dS', float('nan')):+.4f} dalpha {wr.get('dalpha', float('nan')):+.4f}; pass {r['gaussian_pass']}")
    print(f"C: {'pass' if c['pass'] else 'FAIL'} (points {c['points_pass']}, gaussians {c['gaussians_pass']})")
    d = res["D"]
    b = d["C0"]
    print(f"D C0: d_rms {b['d_rms']:.3f} sigma, d_max {b['d_max'] * 1e6:.1f} uJy, |dFF| {b['dff'] * 1e3:.3f} mJy (sigma {b['sigma'] * 1e6:.2f} uJy)")
    for cfg in ("C1", "C2", "C3"):
        m = d[cfg]
        print(f"D {cfg}: d_rms {m['d_rms']:.3f} (<= {m['bound_rms']:.3f}), d_max {m['d_max'] * 1e6:.1f} (<= {m['bound_max'] * 1e6:.1f}) uJy, |dFF| {m['dff'] * 1e3:.3f} (<= {m['bound_dff'] * 1e3:.3f}) mJy: {'pass' if m['pass'] else 'FAIL'}")
    f = res["F"]
    print("F peak RSS GB (G / W): " + ", ".join(f"{k} {v['gemclean'] / 1e9 if v['gemclean'] else float('nan'):.2f}/{v['wsclean'] / 1e9 if v['wsclean'] else float('nan'):.2f}" for k, v in f.items() if isinstance(v, dict)))


def avg(tag):
    """Criterion E: GeMClean -average-channels 2 on D1 against GeMClean and WSClean on D1avg."""
    out, ok = {}, True
    for mine, theirs, n in (("A1", "P1", 1), ("A4", "P4", 4)):
        for kind in ("psf", "dirty"):
            for part in parts(n) if n > 1 else [""]:
                a, _ = img(gname(tag, "D1", mine, part, kind))
                b, _ = img(gname(tag, "D1avg", theirs, part, kind))
                c, _ = img(wname("D1avg", theirs, part, kind))
                rg = float(np.abs(a - b).max() / np.abs(b).max())
                rw = float(np.abs(a - c).max() / np.abs(c).max())
                out[f"{mine}-{part}{kind}"] = {"vs_gemclean": rg, "vs_wsclean": rw}
                ok &= rg <= 1e-6 and rw <= 1e-5
    out["pass"] = bool(ok)
    (O / "runs" / tag / "score-avg.json").write_text(json.dumps(out, indent=1) + "\n")
    for k, v in out.items():
        print(k, v)


if __name__ == "__main__":
    if sys.argv[1] == "avg":
        avg(sys.argv[2])
    else:
        tag = sys.argv[1]
        for sky in sys.argv[2:]:
            show(score(tag, sky))
