"""score.py TAG RUN [TRUTH.json] : criteria B to F of research/g5-multiscale.md, mechanically.

GeMClean is read from $O/runs/TAG/RUN/g-*, WSClean from $O/runs/wsclean/RUN/w-*. Simulated runs
take the simulator's catalogue (TRUTH.json); D2j takes G3's D2.json; P takes the held-out
comparison's source mask. Prints the verdicts and writes $O/runs/TAG/score-RUN.json.
"""

import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

O = Path(os.environ.get("G5_OUT", "/mnt/d/rang/outputs/g5-20261107-01"))
MASK = Path(
    "/mnt/d/rang/outputs/20261103-gemclean-heldout/real/images/source-mask.fits"
)
NU0 = 1.2e9
R_POINT = 6.0


def img(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, dtype=np.float64).squeeze(), dict(h[0].header)


def mad_sigma(a):
    a = np.asarray(a).ravel()
    return 1.4826 * float(np.median(np.abs(a - np.median(a))))


def inner_mask(n):
    m = np.zeros((n, n), bool)
    m[n // 6 : n - n // 6, n // 6 : n - n // 6] = True
    return m


def disc(n, x, y, r):
    yy, xx = np.mgrid[0:n, 0:n]
    return (xx - x) ** 2 + (yy - y) ** 2 <= r * r


def beam_area(header):
    pix = abs(float(header["CDELT1"]))
    return (
        math.pi
        * float(header["BMAJ"])
        * float(header["BMIN"])
        / (4 * math.log(2))
        / pix**2
    )


# -- B: scales against WSClean's log -------------------------------------------------------

NICE = re.compile(r"Theoretic beam = ([0-9.]+)(''|'|deg|mas)")
SCALE = re.compile(
    r"- Scale ([0-9.]+), bias factor=([0-9.e+-]+), psfpeak=([0-9.e+-]+), gain=([0-9.e+-]+)"
)


def crit_b(gdir, wdir):
    rep = json.loads((gdir / "g-report.json").read_text())
    ms = rep["multiscale"]
    ms = ms[0] if isinstance(ms, list) else ms
    log = (wdir / "log.txt").read_text()
    unit = {"''": 1 / 3600, "'": 1 / 60, "deg": 1.0, "mas": 1 / 3.6e6}
    # WSClean logs each output channel's theoretic beam; radler takes the
    # smallest (minTheoreticalBeamSize). Scorer correction, labelled in the note.
    m = min(NICE.finditer(log), key=lambda x: float(x.group(1)) * unit[x.group(2)])
    w_beam_deg = float(m.group(1)) * unit[m.group(2)]
    digits = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
    half_unit = 0.5 * 10.0 ** (-digits) * unit[m.group(2)]
    g_beam_deg = math.degrees(ms["theoretic_beam_rad"])
    beam_ok = abs(g_beam_deg - w_beam_deg) <= half_unit * 1.0000001
    # The first block of scale lines (radler logs them for the integrated PSF).
    lines = SCALE.findall(log)
    nscales = len(ms["scales"])
    w = [tuple(float(v) for v in t) for t in lines[:nscales]]
    rows, ok = [], beam_ok and len(lines) >= nscales
    for s, t in zip(ms["scales"], w, strict=False):
        row = {
            "scale_g": s["scale_pixels"],
            "scale_w": t[0],
            "bias_g": s["bias_factor"],
            "bias_w": t[1],
            "psf_peak_g": s["psf_peak"],
            "psf_peak_w": t[2],
            "gain_g": s["gain"],
            "gain_w": t[3],
        }
        row["ok"] = (
            round(s["scale_pixels"]) == round(t[0])
            and round(s["bias_factor"] * 10) / 10 == t[1]
            and abs(s["psf_peak"] / t[2] - 1) <= 1e-4
            and abs(s["gain"] / t[3] - 1) <= 1e-4
        )
        ok &= row["ok"]
        rows.append(row)
    return {
        "pass": bool(ok),
        "beam_deg_g": g_beam_deg,
        "beam_deg_w": w_beam_deg,
        "beam_print": m.group(0),
        "scales_w_lines": len(lines),
        "rows": rows,
    }


# -- C: extended flux on the simulated skies ----------------------------------------------


def gaussian_pixels(comp, n, scale_arcsec, mask):
    """The Gaussian's flux in each pixel of `mask`, integrated at 8 x 8 subsamples."""
    fwhm = comp.get("fwhm_px") or comp["fwhm_arcsec"] / scale_arcsec
    s = fwhm / (2 * math.sqrt(2 * math.log(2)))
    yy, xx = np.nonzero(mask)
    sub = (np.arange(8) + 0.5) / 8 - 0.5
    total = np.zeros(len(xx))
    for dy in sub:
        for dx in sub:
            r2 = (xx + dx - comp["x"]) ** 2 + (yy + dy - comp["y"]) ** 2
            total += np.exp(-r2 / (2 * s * s))
    return total / 64 / (2 * math.pi * s * s)


def groups(comps, scale_arcsec):
    gs = [c for c in comps if c["kind"] == "gaussian"]
    radius = [2 * (c.get("fwhm_px") or c["fwhm_arcsec"] / scale_arcsec) for c in gs]
    parent = list(range(len(gs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(gs)):
        for j in range(i):
            d = math.hypot(gs[i]["x"] - gs[j]["x"], gs[i]["y"] - gs[j]["y"])
            if d < radius[i] + radius[j]:
                parent[find(i)] = find(j)
    out = {}
    for i in range(len(gs)):
        out.setdefault(find(i), []).append(i)
    return [[(gs[i], radius[i]) for i in members] for members in out.values()]


def flux_of(comp, freq_weights=None):
    if freq_weights is None:
        return comp["flux"]
    return float(np.dot(comp["_channel_truth"], freq_weights))


def crit_c(g_model, g_res, w_model, w_res, w_head, cat, weights=None):
    """C1-C4 and F on one pair of (model, residual) images; `weights` the MFS channel weights."""
    n = g_model.shape[0]
    scale = cat["image"]["scale_arcsec"]
    comps = cat["components"]
    grp = groups(comps, scale)
    apertures = []
    for members in grp:
        m = np.zeros((n, n), bool)
        for c, r in members:
            m |= disc(n, c["x"], c["y"], r)
        apertures.append(m)
    every = np.zeros((n, n), bool)
    for m in apertures:
        every |= m
    points = [c for c in comps if c["kind"] == "point"]
    point_any = np.zeros((n, n), bool)
    for c in points:
        point_any |= disc(n, c["x"], c["y"], R_POINT)
    sigma = mad_sigma(w_res[inner_mask(n) & ~every & ~point_any])
    omega = beam_area(w_head)
    out = {"sigma": sigma, "omega_pixels": omega, "groups": []}
    ok = True
    for members, m in zip(grp, apertures, strict=True):
        t = 0.0
        for c, _ in members:
            t += flux_of(c, weights) * float(gaussian_pixels(c, n, scale, m).sum())
        inside = [c for c in points if m[round(c["y"]), round(c["x"])]]
        t += sum(flux_of(c, weights) for c in inside)
        npix = int(m.sum())
        eps = 3 * sigma * math.sqrt(npix / omega)
        fg, fw = float(g_model[m].sum()), float(w_model[m].sum())
        rg = float(np.sqrt(np.mean(g_res[m] ** 2)))
        rw = float(np.sqrt(np.mean(w_res[m] ** 2)))
        c1 = (
            abs(fg - t) <= 0.02 * t + eps or abs(fg - t) <= abs(fw - t) + 0.01 * t + eps
        )
        c2 = abs(fg - fw) <= 0.02 * t + math.sqrt(2) * eps or abs(fg - t) <= abs(fw - t)
        c3 = rg <= max(1.5 * rw, rw + 0.5 * sigma)
        ok &= c1 and c2 and c3
        out["groups"].append(
            {
                "gaussians": len(members),
                "fwhm_px": [round(r / 2, 2) for _, r in members],
                "centre": [members[0][0]["x"], members[0][0]["y"]],
                "points_inside": len(inside),
                "pixels": npix,
                "truth": t,
                "eps": eps,
                "flux_g": fg,
                "flux_w": fw,
                "rel_err_g": fg / t - 1,
                "rel_err_w": fw / t - 1,
                "restored_g": fg + float(g_res[m].sum()) / omega,
                "restored_w": fw + float(w_res[m].sum()) / omega,
                "res_rms_g": rg,
                "res_rms_w": rw,
                "C1": bool(c1),
                "C2": bool(c2),
                "C3": bool(c3),
            }
        )
    # C4: isolated bright points.
    errs = {"g": [], "w": []}
    for c in points:
        s = flux_of(c, weights)
        if s / sigma < 200:
            continue
        d = disc(n, c["x"], c["y"], R_POINT)
        if (disc(n, c["x"], c["y"], 2 * R_POINT) & every).any():
            continue
        errs["g"].append(abs(float(g_model[d].sum()) / s - 1))
        errs["w"].append(abs(float(w_model[d].sum()) / s - 1))
    med = {k: float(np.median(v)) if v else float("nan") for k, v in errs.items()}
    c4 = (not errs["g"]) or med["g"] <= med["w"] + 0.005
    ok &= c4
    off = ~every & ~point_any
    out.update(
        {
            "points_scored": len(errs["g"]),
            "median_point_err_g": med["g"],
            "median_point_err_w": med["w"],
            "C4": bool(c4),
            "false_flux_g": float(g_model[off].sum()),
            "false_flux_w": float(w_model[off].sum()),
            "false_abs_flux_g": float(np.abs(g_model[off]).sum()),
            "false_abs_flux_w": float(np.abs(w_model[off]).sum()),
            "model_flux_g": float(g_model.sum()),
            "model_flux_w": float(w_model.sum()),
            "pass": bool(ok),
        }
    )
    return out


# -- D: the real field ---------------------------------------------------------------------


def crit_d(g_model, g_res, w_model, w_res, w_head):
    mask, _ = img(MASK)
    mask = mask > 0.5
    n = g_model.shape[0]
    if mask.shape != g_model.shape:
        raise SystemExit(f"mask {mask.shape} against image {g_model.shape}")
    pix_arcmin = abs(float(w_head["CDELT1"])) * 60
    core = mask & disc(n, n / 2, n / 2, 10.0 / pix_arcmin)
    sigma = mad_sigma(w_res[inner_mask(n) & ~mask])
    omega = beam_area(w_head)
    out = {"sigma": sigma, "omega_pixels": omega, "regions": {}}
    ok = True
    for name, m in (("M", mask), ("R", core)):
        npix = int(m.sum())
        eps = 3 * sigma * math.sqrt(npix / omega)
        fg, fw = float(g_model[m].sum()), float(w_model[m].sum())
        rg = float(np.sqrt(np.mean(g_res[m] ** 2)))
        rw = float(np.sqrt(np.mean(w_res[m] ** 2)))
        flux_ok = abs(fg - fw) <= 0.02 * abs(fw) + math.sqrt(2) * eps
        rms_ok = name != "R" or rg <= max(1.5 * rw, rw + 0.5 * sigma)
        ok &= flux_ok and rms_ok
        out["regions"][name] = {
            "pixels": npix,
            "eps": eps,
            "flux_g": fg,
            "flux_w": fw,
            "rel_diff": fg / fw - 1,
            "restored_g": fg + float(g_res[m].sum()) / omega,
            "restored_w": fw + float(w_res[m].sum()) / omega,
            "res_rms_g": rg,
            "res_rms_w": rw,
            "flux_ok": bool(flux_ok),
            "rms_ok": bool(rms_ok),
        }
    off = ~mask
    out.update(
        {
            "off_flux_g": float(g_model[off].sum()),
            "off_flux_w": float(w_model[off].sum()),
            "off_abs_flux_g": float(np.abs(g_model[off]).sum()),
            "off_abs_flux_w": float(np.abs(w_model[off]).sum()),
            "off_res_sigma_g": mad_sigma(g_res[inner_mask(n) & ~mask]),
            "off_res_sigma_w": sigma,
            "model_flux_g": float(g_model.sum()),
            "model_flux_w": float(w_model.sum()),
            "pass": bool(ok),
        }
    )
    return out


# -- E: joined channels (G3's criterion C for the Gaussians) --------------------------------


def fit_spectrum(f, nu, sigma):
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
        "se_alpha": float(math.sqrt(cov[1, 1])),
    }


def crit_e(gdir, wdir, cat, nout):
    n = cat["image"]["size"]
    nchan = cat["nchan"]
    chans = [
        list(range(i * nchan // nout, (i + 1) * nchan // nout)) for i in range(nout)
    ]
    nu = np.array([img(wdir / f"w-{k:04d}-psf.fits")[1]["CRVAL3"] for k in range(nout)])
    wk = np.array(
        [img(wdir / f"w-{k:04d}-dirty.fits")[1]["WSCIMGWG"] for k in range(nout)]
    )
    w_mfs_res, w_head = img(wdir / "w-MFS-residual.fits")
    sigma_mfs = mad_sigma(w_mfs_res[inner_mask(n)])
    sigma_k = sigma_mfs * np.sqrt(wk.sum() / wk)
    gm = [img(gdir / f"g-{k:04d}-model.fits")[0] for k in range(nout)]
    wm = [img(wdir / f"w-{k:04d}-model.fits")[0] for k in range(nout)]
    gauss = []
    ok = True
    for c in cat["components"]:
        s = np.asarray(c["flux_per_channel"])
        c["_channel_truth"] = np.array([s[g].mean() for g in chans])
        if c["kind"] != "gaussian":
            continue
        m = disc(n, c["x"], c["y"], 2 * c["fwhm_px"])
        t = fit_spectrum(c["_channel_truth"], nu, sigma_k)
        rec = {"centre": [c["x"], c["y"]], "fwhm_px": c["fwhm_px"], "truth": t}
        for who, models in (("g", gm), ("w", wm)):
            f = np.array([mk[m].sum() for mk in models])
            e = fit_spectrum(f, nu, sigma_k)
            rec[who] = {"flux": f.tolist(), "fit": e}
            if e is not None:
                rec[who]["dS"] = e["S0"] / t["S0"] - 1
                rec[who]["dalpha"] = e["alpha"] - t["alpha"]
        g, w = rec["g"], rec["w"]
        if g["fit"] is None:
            passed = False
        else:
            passed = abs(g["dS"]) <= 0.05 and abs(g["dalpha"]) <= 0.1
            if not passed and w["fit"] is not None:
                passed = (
                    abs(g["dS"]) <= abs(w["dS"]) + 0.03
                    and abs(g["dalpha"]) <= abs(w["dalpha"]) + 0.05
                )
        rec["pass"] = bool(passed)
        ok &= passed
        gauss.append(rec)
    a = wk / wk.sum()
    mfs = crit_c(
        img(gdir / "g-MFS-model.fits")[0],
        img(gdir / "g-MFS-residual.fits")[0],
        img(wdir / "w-MFS-model.fits")[0],
        w_mfs_res,
        w_head,
        cat,
        weights=a,
    )
    ok &= mfs["pass"]
    return {"pass": bool(ok), "gaussians": gauss, "mfs": mfs, "weights": wk.tolist()}


# -- F: cycles, components, memory -----------------------------------------------------------


def crit_f(gdir, wdir):
    rep = json.loads((gdir / "g-report.json").read_text())
    ms = rep["multiscale"]
    runs = ms if isinstance(ms, list) else [ms]
    log = (wdir / "log.txt").read_text()
    w_majors = len(re.findall(r"== Deconvolving \(", log))
    w_iters = re.findall(r"Total: (\d+) components", log)

    def rss(d):
        t = (d / "time.txt").read_text()
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", t)
        w = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", t)
        return (int(m.group(1)) * 1024 if m else None, w.group(1) if w else None)

    run = rep["run"]
    return {
        "g_major_cycles": run["major_cycles"] if run != "null" and run else None,
        "g_components": run["components"] if run else None,
        "g_stop": run["stop"] if run else None,
        "g_per_scale": [
            [(s["scale_pixels"], s["components"], s["flux"]) for s in r["scales"]]
            for r in runs
        ],
        "g_sub_minor_loops": [r["sub_minor_loops"] for r in runs],
        "g_end": [r["end"] for r in runs],
        "w_major_cycles": w_majors,
        "w_components_logged": [int(v) for v in w_iters],
        "g_rss_bytes, wall": rss(gdir),
        "w_rss_bytes, wall": rss(wdir),
    }


def main():
    tag, run = sys.argv[1], sys.argv[2]
    gdir, wdir = O / "runs" / tag / run, O / "runs" / "wsclean" / run
    out = {"tag": tag, "run": run, "B": crit_b(gdir, wdir)}
    if run == "D2j":
        cat = json.loads(
            Path("/mnt/d/rang/outputs/20261106-g3-spectral/data/D2.json").read_text()
        )
        out["E"] = crit_e(gdir, wdir, cat, 8)
    elif run == "P":
        gm, _ = img(gdir / "g-model.fits")
        gr, _ = img(gdir / "g-residual.fits")
        wm, _ = img(wdir / "w-model.fits")
        wr, wh = img(wdir / "w-residual.fits")
        out["D"] = crit_d(gm, gr, wm, wr, wh)
    else:
        cat = json.loads(Path(sys.argv[3]).read_text())
        gm, _ = img(gdir / "g-model.fits")
        gr, _ = img(gdir / "g-residual.fits")
        wm, _ = img(wdir / "w-model.fits")
        wr, wh = img(wdir / "w-residual.fits")
        out["C"] = crit_c(gm, gr, wm, wr, wh, cat)
    out["F"] = crit_f(gdir, wdir)
    (O / "runs" / tag / f"score-{run}.json").write_text(
        json.dumps(out, indent=1, default=float)
    )
    verdicts = {
        k: v["pass"] for k, v in out.items() if isinstance(v, dict) and "pass" in v
    }
    print(json.dumps({"run": run, "verdicts": verdicts}, default=float))
    for k in ("C", "D", "E"):
        if k in out:
            print(k, json.dumps(out[k], default=float)[:3000])
    print("F", json.dumps(out["F"], default=float))


if __name__ == "__main__":
    main()
