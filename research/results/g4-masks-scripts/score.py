"""score.py TAG RUN [TRUTH.json]: criteria S, B, M and X of research/g4-masks.md, mechanically.

GeMClean from $O/runs/TAG/RUN/g-*, WSClean from $O/runs/wsclean/RUN/w-*. Simulated runs take the
simulator's catalogue (TRUTH.json); P takes the held-out comparison's source mask (G5's D regions).
Prints the verdicts and writes $O/runs/TAG/score-RUN.json. G5's scorer supplies criterion B and
the aperture helpers.
"""

import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

HERE = Path(__file__).resolve().parent
G5 = HERE.parent / "g5-multiscale-scripts" / "score.py"
spec = importlib.util.spec_from_file_location("g5score", G5)
g5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g5)

O = Path(os.environ.get("G4_OUT", "D:/rang/outputs/g4-20261109-01"))
PILOT_MASK = Path(
    "D:/rang/outputs/20261103-gemclean-heldout/real/images/source-mask.fits"
)
R_POINT = 6.0
S_MIN = 0.03  # the truth mask's point limit (make_mask.py)


def img(path):
    with fits.open(path) as h:
        return np.asarray(h[0].data, dtype=np.float64).squeeze(), h[0].header


# -- S: selection ---------------------------------------------------------------------------


def crit_s(gdir, wdir):
    rows, ok, missing = [], True, []
    for wf in sorted(wdir.glob("w-*.fits")):
        kind = wf.stem.rsplit("-", 1)[-1]
        gf = gdir / ("g-" + wf.name[2:])
        if kind not in ("dirty", "psf", "image"):
            continue
        if not gf.exists():
            missing.append(wf.name)
            ok = False
            continue
        dw, hw = img(wf)
        dg, hg = img(gf)
        row = {"file": wf.name}
        if kind in ("dirty", "psf"):
            peak = float(np.abs(dw).max())
            row["max_abs_diff_rel"] = float(np.abs(dg - dw).max()) / peak
            row["images_ok"] = row["max_abs_diff_rel"] <= 1e-5
            ok &= row["images_ok"]
        if kind == "dirty":
            row["wscnvis_g"], row["wscnvis_w"] = int(hg["WSCNVIS"]), int(hw["WSCNVIS"])
            for key in ("WSCIMGWG", "WSCVWSUM"):
                row[key.lower() + "_rel"] = abs(float(hg[key]) / float(hw[key]) - 1)
            row["headers_ok"] = (
                row["wscnvis_g"] == row["wscnvis_w"]
                and row["wscimgwg_rel"] <= 1e-6
                and row["wscvwsum_rel"] <= 1e-6
            )
            ok &= row["headers_ok"]
        if kind == "image":
            for key in ("BMAJ", "BMIN"):
                row[key.lower() + "_rel"] = abs(float(hg[key]) / float(hw[key]) - 1)
            row["beam_ok"] = row["bmaj_rel"] <= 1e-3 and row["bmin_rel"] <= 1e-3
            ok &= row["beam_ok"]
        rows.append(row)
    return {"pass": bool(ok and rows), "missing": missing, "rows": rows}


# -- M: mask behaviour ----------------------------------------------------------------------


def pick(d, stem):
    """The single-channel file, or the MFS one for joined channels."""
    for name in (f"{stem}.fits", stem.replace("-", "-MFS-", 1) + ".fits"):
        if (d / name).exists():
            return d / name
    raise SystemExit(f"{d}: no {stem}")


def apertures_sim(cat, n):
    scale = cat["image"]["scale_arcsec"]
    comps = cat["components"]
    out = []
    every = np.zeros((n, n), bool)
    for members in g5.groups(comps, scale):
        m = np.zeros((n, n), bool)
        for c, r in members:
            m |= g5.disc(n, c["x"], c["y"], r)
        every |= m
        out.append(("group", m, members[0][0]["x"], members[0][0]["y"]))
    points = [c for c in comps if c["kind"] == "point"]
    point_any = np.zeros((n, n), bool)
    for c in points:
        point_any |= g5.disc(n, c["x"], c["y"], R_POINT)
    return out, points, every, point_any


def crit_m(gdir, wdir, cat, mask_file):
    gm, _ = img(pick(gdir, "g-model"))
    gr, _ = img(pick(gdir, "g-residual"))
    wm, hw = img(pick(wdir, "w-model"))
    wr, _ = img(pick(wdir, "w-residual"))
    gi_head = img(pick(wdir, "w-image"))[1]
    n = gm.shape[0]
    omega = g5.beam_area(gi_head)
    out = {"omega_pixels": omega, "apertures": []}
    ok = True
    if cat is not None:
        aps, points, every, point_any = apertures_sim(cat, n)
        sigma = g5.mad_sigma(wr[g5.inner_mask(n) & ~every & ~point_any])
        flux = lambda c: c["flux"] if "flux" in c else c.get("flux_jy", 0.0)
        for c in points:
            if flux(c) / sigma < 200:
                continue
            d = g5.disc(n, c["x"], c["y"], R_POINT)
            if (d & every).any():
                continue
            aps.append(("point", d, c["x"], c["y"]))
        support = every | point_any
    else:
        m, _ = img(PILOT_MASK)
        m = m > 0.5
        pix_arcmin = abs(float(hw["CDELT1"])) * 60
        core = m & g5.disc(n, n / 2, n / 2, 10.0 / pix_arcmin)
        aps = [("M", m, n / 2, n / 2), ("R", core, n / 2, n / 2)]
        sigma = g5.mad_sigma(wr[g5.inner_mask(n) & ~m])
        support = m
        points = []
    out["sigma"] = sigma
    for kind, m, x, y in aps:
        npix = int(m.sum())
        eps = 3 * sigma * math.sqrt(npix / omega)
        fg, fw = float(gm[m].sum()), float(wm[m].sum())
        rg = float(np.sqrt(np.mean(gr[m] ** 2)))
        rw = float(np.sqrt(np.mean(wr[m] ** 2)))
        m2 = abs(fg - fw) <= 0.02 * abs(fw) + math.sqrt(2) * eps
        m3 = rg <= max(1.5 * rw, rw + 0.5 * sigma)
        ok &= m2 and m3
        out["apertures"].append(
            {
                "kind": kind,
                "x": x,
                "y": y,
                "pixels": npix,
                "eps": eps,
                "flux_g": fg,
                "flux_w": fw,
                "rel_diff": fg / fw - 1 if fw else float("nan"),
                "res_rms_g": rg,
                "res_rms_w": rw,
                "M2": bool(m2),
                "M3": bool(m3),
            }
        )
    out["model_flux_g"], out["model_flux_w"] = float(gm.sum()), float(wm.sum())
    out["off_support_abs_flux_g"] = float(np.abs(gm[~support]).sum())
    out["off_support_abs_flux_w"] = float(np.abs(wm[~support]).sum())
    out["off_support_pixels_g"] = int((gm[~support] != 0).sum())
    out["off_support_pixels_w"] = int((wm[~support] != 0).sum())
    nz_g, nz_w = gm != 0, wm != 0
    out["support_g"], out["support_w"] = int(nz_g.sum()), int(nz_w.sum())
    out["support_both"] = int((nz_g & nz_w).sum())
    if mask_file is not None:
        fm, _ = img(mask_file)
        fm = fm != 0
        out["model_outside_mask_g"] = int((nz_g & ~fm).sum())
        out["model_outside_mask_w"] = int((nz_w & ~fm).sum())
        # The masked-out points keep their residual (F1, M3).
        held = []
        for c in points:
            if c["flux"] < S_MIN:
                px, py = round(c["x"]), round(c["y"])
                held.append(abs(gr[py, px] - wr[py, px]) <= 3 * sigma)
        out["masked_out_points"] = len(held)
        out["masked_out_points_ok"] = int(sum(held))
        ok &= all(held)
    mj = gdir / "g-mask.json"
    if mj.exists():
        rec = json.loads(mj.read_text())
        out["mask_json"] = rec
        if rec.get("fits_outside_picks") is not None:
            out["M1_fits_picks_outside"] = rec["fits_outside_picks"]
            ok &= rec["fits_outside_picks"] == 0
        for a in rec.get("auto", []):
            ok &= a.get("outside_picks", 0) == 0
    out["pass"] = bool(ok)
    return out


# -- X: the switch-over ---------------------------------------------------------------------

SIGMA = re.compile(
    r"Estimated standard deviation of background noise: ([0-9.e+-]+) ?(µJy|mJy|Jy|nJy|KJy)"
)
DECONV = re.compile(r"== Deconvolving \((\d+)\) ==")
REACHED = "Auto-masking threshold reached"
UNIT = {"nJy": 1e-9, "µJy": 1e-6, "mJy": 1e-3, "Jy": 1.0, "KJy": 1e3}


def wsclean_auto(log):
    """Per major iteration: σ (Jy) and its printed half-unit; the finishing iteration."""
    sig, fin, it = {}, None, None
    for line in log.splitlines():
        m = DECONV.search(line)
        if m:
            it = int(m.group(1))
        m = SIGMA.search(line)
        if m and it is not None:
            v = m.group(1)
            digits = len(v.split(".")[1]) if "." in v else 0
            sig[it] = (
                float(v) * UNIT[m.group(2)],
                0.5 * 10.0**-digits * UNIT[m.group(2)],
            )
        if REACHED in line and fin is None:
            fin = it
    return sig, fin, it


def crit_x(gdir, wdir):
    log = (wdir / "log.txt").read_text(encoding="utf-8", errors="replace")
    sig_w, fin_w, last_w = wsclean_auto(log)
    rec = json.loads((gdir / "g-mask.json").read_text())["auto"][0]
    fin_g = rec["finishing_iteration"]
    fin_g = None if fin_g is None else int(fin_g)
    rows, ok = [], fin_g == fin_w and fin_w is not None
    for c in rec["cycles"]:
        i = c["index"]
        if fin_w is not None and i > fin_w:
            continue
        sw = sig_w.get(i)
        row = {
            "iteration": i,
            "sigma_g": c["sigma"],
            "sigma_w": None if sw is None else sw[0],
        }
        if sw is not None:
            row["ok"] = abs(c["sigma"] - sw[0]) <= max(0.01 * sw[0], sw[1])
            ok &= row["ok"]
        rows.append(row)
    rep = json.loads((gdir / "g-report.json").read_text())
    majors_g = rep.get("major_cycles") or rep.get("run", {}).get("major_cycles")
    out = {
        "finishing_g": fin_g,
        "finishing_w": fin_w,
        "majors_g": majors_g,
        "majors_w": last_w,
        "X3": majors_g is not None
        and last_w is not None
        and abs(int(majors_g) - last_w) <= 1,
        "rows": rows,
    }
    ok &= out["X3"]
    out["pass"] = bool(ok)
    return out


def main():
    tag, run = sys.argv[1:3]
    truth = json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else None
    gdir, wdir = O / "runs" / tag / run, O / "runs" / "wsclean" / run
    res = {"run": run, "tag": tag, "S": crit_s(gdir, wdir)}
    cleaned = (wdir / "w-model.fits").exists() or (wdir / "w-MFS-model.fits").exists()
    if cleaned:
        mask_file = O / "masks" / "s2-truth.fits" if run in ("F1", "F2") else None
        res["M"] = crit_m(gdir, wdir, truth, mask_file)
    if run.startswith("A") or run in ("P", "H"):
        res["X"] = crit_x(gdir, wdir)
    if run in ("A3", "H"):
        res["B"] = g5.crit_b(gdir, wdir)
    (O / "runs" / tag / f"score-{run}.json").write_text(json.dumps(res, indent=1))
    for k in ("S", "B", "M", "X"):
        if k in res:
            print(f"{run} {k}: {'pass' if res[k]['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
