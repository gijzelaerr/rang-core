"""Scorer of research/rml-gap.md (issue #24 step 1): any imager's MFS model against the
analytic truth of a gemclean bench sky, on a common Gaussian beam.

    rml_gap_score.py beam PSF.fits                       the common beam's FWHM (pixels)
    rml_gap_score.py control PREP CAT OUT.json --beam-px B
    rml_gap_score.py orient PREP DIRTY.fits OUT.json     pfb's orientation against the core
    rml_gap_score.py score PREP CAT MODEL.fits OUT.json --beam-px B [--orient K]
                                                         [--sigma S] [--no-exact]

PREP is a `gemclean_bench_compare.py prepare` directory (the core's exact gridder, Briggs 0.5
weights, the core's dirty image in WSClean's FITS order). CAT is the simulator's catalogue
(components with FITS pixel x, y, flux, kind, fwhm_arcsec). Images are WSClean's FITS order,
`data[y, x]`. Section 4 of the note defines every measure; nothing here imports a tool's
own residual.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemclean_bench_compare import Exact, inner_box, truth_image  # noqa: E402
from rang.core_imaging import read_fits  # noqa: E402

FWHM_TO_SIGMA = 1.0 / (2.0 * math.sqrt(2.0 * math.log(2.0)))


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=1), encoding="utf-8")


# -- the common beam ------------------------------------------------------------


def halfmax_major_px(psf, step_deg=0.5):
    """Major axis (pixels) of the half-maximum region around the PSF peak: along every
    direction through the peak, the distance between the two half-maximum crossings
    (linear interpolation), and the largest over directions."""
    py, px = np.unravel_index(np.argmax(psf), psf.shape)
    peak = psf[py, px]
    best = 0.0
    for a in np.arange(0.0, 180.0, step_deg):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        width = 0.0
        for sign in (1.0, -1.0):
            prev, r = 1.0, 0.0
            while True:
                r += 0.05
                x, y = px + sign * r * c, py + sign * r * s
                v = bilinear(psf, x, y) / peak
                if v < 0.5:
                    width += r - 0.05 * (0.5 - v) / (prev - v)
                    break
                prev = v
        best = max(best, width)
    return best


def bilinear(img, x, y):
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - x0, y - y0
    return (
        img[y0, x0] * (1 - fx) * (1 - fy)
        + img[y0, x0 + 1] * fx * (1 - fy)
        + img[y0 + 1, x0] * (1 - fx) * fy
        + img[y0 + 1, x0 + 1] * fx * fy
    )


# -- truth and model on the beam ------------------------------------------------------


def components(cat):
    scale = cat["image"]["scale_arcsec"]
    out = []
    for c in cat["components"]:
        fwhm = c["fwhm_arcsec"] / scale if c["kind"] == "gaussian" else 0.0
        out.append((float(c["x"]), float(c["y"]), float(c["flux"]), fwhm))
    return out


def truth_on_beam(comps, size, beam_px):
    """B * T at every pixel centre, analytically (Jy per pixel, flux preserved)."""
    out = np.zeros((size, size))
    sb2 = (beam_px * FWHM_TO_SIGMA) ** 2
    for x, y, f, fwhm in comps:
        s2 = sb2 + (fwhm * FWHM_TO_SIGMA) ** 2
        h = int(math.ceil(9.0 * math.sqrt(s2)))
        x0, x1 = max(0, int(x) - h), min(size, int(x) + h + 2)
        y0, y1 = max(0, int(y) - h), min(size, int(y) + h + 2)
        gx = np.exp(-((np.arange(x0, x1) - x) ** 2) / (2 * s2))
        gy = np.exp(-((np.arange(y0, y1) - y) ** 2) / (2 * s2))
        out[y0:y1, x0:x1] += f / (2 * math.pi * s2) * np.outer(gy, gx)
    return out


def beam_transform(shape, beam_px):
    ky = np.fft.fftfreq(shape[0])[:, None]
    kx = np.fft.rfftfreq(shape[1])[None, :]
    sb = beam_px * FWHM_TO_SIGMA
    return np.exp(-2 * math.pi**2 * sb**2 * (kx**2 + ky**2))


def model_on_beam(model, beam_px):
    return np.fft.irfft2(
        np.fft.rfft2(model) * beam_transform(model.shape, beam_px), s=model.shape
    )


def bandlimited_truth(comps, size):
    """The truth's analytic transform on the grid, inverse FFT: the band-limited truth."""
    ky = np.fft.fftfreq(size)
    kx = np.fft.rfftfreq(size)
    spec = np.zeros((size, kx.size), np.complex128)
    k2 = kx[None, :] ** 2 + ky[:, None] ** 2
    for x, y, f, fwhm in comps:
        env = np.exp(-2 * math.pi**2 * (fwhm * FWHM_TO_SIGMA) ** 2 * k2) if fwhm else 1.0
        spec += (
            f
            * env
            * np.outer(np.exp(-2j * math.pi * ky * y), np.exp(-2j * math.pi * kx * x))
        )
    return np.fft.irfft2(spec, s=(size, size))


# -- apertures --------------------------------------------------------------------------


def groups(comps, size, beam_px):
    """Discs of radius 2 sqrt(FWHM^2 + b^2) per component, overlapping discs merged.
    Returns (label image, 0 = outside; list of groups with members)."""
    n = len(comps)
    radius = [2.0 * math.sqrt(c[3] ** 2 + beam_px**2) for c in comps]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            d = math.hypot(comps[i][0] - comps[j][0], comps[i][1] - comps[j][1])
            if d < radius[i] + radius[j]:
                parent[find(i)] = find(j)
    roots = sorted({find(i) for i in range(n)})
    gid = {r: k + 1 for k, r in enumerate(roots)}
    label = np.zeros((size, size), np.int32)
    for i, (x, y, _f, _w) in enumerate(comps):
        r = radius[i]
        x0, x1 = max(0, int(x - r) - 1), min(size, int(x + r) + 2)
        y0, y1 = max(0, int(y - r) - 1), min(size, int(y + r) + 2)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        disc = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
        label[y0:y1, x0:x1][disc] = gid[find(i)]
    out = []
    for r in roots:
        members = [i for i in range(n) if find(i) == r]
        out.append(
            {
                "id": gid[r],
                "members": members,
                "extended": any(comps[i][3] > 0 for i in members),
                "truth_flux_catalogue": float(sum(comps[i][2] for i in members)),
            }
        )
    return label, out


def centroid(img, mask):
    yy, xx = np.nonzero(mask)
    w = img[yy, xx]
    s = w.sum()
    return float((w * xx).sum() / s), float((w * yy).sum() / s)


def measures(bm, bt, model, label, grps, beam_px, sigma):
    omega = 2 * math.pi * (beam_px * FWHM_TO_SIGMA) ** 2
    diff = bm - bt
    rec = {"relative_l2": float(np.linalg.norm(diff) / np.linalg.norm(bt))}
    ext = np.isin(label, [g["id"] for g in grps if g["extended"]])
    pts = (label > 0) & ~ext
    for name, m in (("extended", ext), ("points", pts)):
        if m.any():
            rec[f"relative_l2_{name}"] = float(
                np.linalg.norm(diff[m]) / np.linalg.norm(bt[m])
            )
    rows = []
    # One pass over the labels: sums and first moments per group.
    lab = label.ravel()
    nlab = len(grps) + 1
    npx = np.bincount(lab, minlength=nlab)
    yy, xx = np.indices(label.shape)
    for name, img in (("m", bm), ("t", bt)):
        v = img.ravel()
        rec[f"_{name}"] = (
            np.bincount(lab, v, nlab),
            np.bincount(lab, v * xx.ravel(), nlab),
            np.bincount(lab, v * yy.ravel(), nlab),
        )
    fm, mxm, mym = rec.pop("_m")
    ft, mxt, myt = rec.pop("_t")
    for g in grps:
        k = g["id"]
        eps = 3 * sigma * math.sqrt(npx[k] / omega)
        row = {
            "id": k,
            "n": len(g["members"]),
            "extended": g["extended"],
            "pixels": int(npx[k]),
            "F_T": float(ft[k]),
            "F_M": float(fm[k]),
            "eps": float(eps),
        }
        row["rel_err"] = row["F_M"] / row["F_T"] - 1.0
        row["flux_pass"] = abs(row["F_M"] - row["F_T"]) <= 0.02 * row["F_T"] + eps
        if row["F_T"] >= 20 * eps / 3:
            # A2: a single point within 0.1 b, an extended group within 0.25 b; a group of
            # several points is not gated (its centroid mixes sources).
            lim = 0.25 if g["extended"] else (0.1 if row["n"] == 1 else None)
            if fm[k] > 0:
                dx = mxm[k] / fm[k] - mxt[k] / ft[k]
                dy = mym[k] / fm[k] - myt[k] / ft[k]
                row["offset_beams"] = math.hypot(dx, dy) / beam_px
                row["position_pass"] = None if lim is None else row["offset_beams"] <= lim
            else:
                row["offset_beams"] = None
                row["position_pass"] = None if lim is None else False
        rows.append(row)
    rec["groups"] = rows
    e = [r for r in rows if r["extended"]]
    rec["extended_flux_all_pass"] = all(r["flux_pass"] for r in e) if e else None
    pos = [r["position_pass"] for r in rows if r.get("position_pass") is not None]
    rec["positions_all_pass"] = all(pos) if pos else None
    rec["positions_failed"] = [
        r["id"] for r in rows if r.get("position_pass") is False
    ]
    rec["extended_rel_err"] = [r["rel_err"] for r in e]
    outside = model[label == 0]
    rec["false_flux_pos"] = float(outside[outside > 0].sum())
    rec["false_flux_neg"] = float(outside[outside < 0].sum())
    rec["false_flux_abs"] = float(np.abs(outside).sum())
    rec["model_flux_total"] = float(model.sum())
    rec["truth_flux_total"] = float(bt.sum())
    return rec


ORIENT = {
    0: lambda a: a,
    1: lambda a: a.T,
    2: lambda a: a[::-1, :],
    3: lambda a: a[:, ::-1],
    4: lambda a: a[::-1, ::-1],
    5: lambda a: a.T[::-1, :],
    6: lambda a: a.T[:, ::-1],
    7: lambda a: a.T[::-1, ::-1],
}


def load_prep(prep):
    return json.loads((Path(prep) / "meta.json").read_text(encoding="utf-8"))


def sigma_of(meta, given):
    if given:
        return float(given)
    return float(meta["noise"]["briggs_image_rms"])


# -- commands ---------------------------------------------------------------------------


def cmd_beam(args):
    psf, _ = read_fits(args.psf)
    print(json.dumps({"psf": str(args.psf), "beam_px": halfmax_major_px(psf)}))


def cmd_control(args):
    t0 = time.perf_counter()
    meta = load_prep(args.prep)
    cat = json.loads(Path(args.cat).read_text(encoding="utf-8"))
    size = meta["size"]
    comps = components(cat)
    bt = truth_on_beam(comps, size, args.beam_px)
    label, grps = groups(comps, size, args.beam_px)
    sigma = sigma_of(meta, args.sigma)
    out = {"beam_px": args.beam_px, "sigma": sigma, "groups": len(grps)}
    # The analytic truth on the beam holds the catalogue flux in each group.
    for g in grps:
        g["F_T_analytic"] = float(bt[label == g["id"]].sum())
    out["truth_group_over_catalogue"] = [
        g["F_T_analytic"] / g["truth_flux_catalogue"] for g in grps
    ]
    for name, model in (
        ("bandlimited", bandlimited_truth(comps, size)),
        ("nearest_pixel", truth_image(cat, size)),
    ):
        bm = model_on_beam(model, args.beam_px)
        rec = measures(bm, bt, model, label, grps, args.beam_px, sigma)
        ratios = [r["F_M"] / r["F_T"] for r in rec["groups"]]
        rec["group_ratio_min"], rec["group_ratio_max"] = min(ratios), max(ratios)
        rec.pop("groups")
        out[name] = rec
    b = out["bandlimited"]
    out["control_pass"] = bool(
        b["relative_l2"] <= 0.002
        and abs(b["group_ratio_min"] - 1) <= 0.002
        and abs(b["group_ratio_max"] - 1) <= 0.002
    )
    out["seconds"] = time.perf_counter() - t0
    _write(args.out, out)
    print(json.dumps({k: v for k, v in out.items() if k != "truth_group_over_catalogue"}, indent=1))


def cmd_orient(args):
    core = np.load(Path(args.prep) / "core-dirty-fits-order.npy").astype(np.float64)
    pfb, _ = read_fits(args.dirty)
    peak = np.abs(core).max()
    rec = {"dirty": str(args.dirty)}
    for k, f in ORIENT.items():
        cand = f(pfb)
        if cand.shape != core.shape:
            rec[str(k)] = None
            continue
        scale = float(np.sum(cand * core) / np.sum(cand * cand))
        rec[str(k)] = {
            "linf_over_peak": float(np.abs(cand - core).max() / peak),
            "linf_over_peak_scaled": float(np.abs(scale * cand - core).max() / peak),
            "scale": scale,
        }
    ok = {k: v for k, v in rec.items() if isinstance(v, dict)}
    best = min(ok, key=lambda k: ok[k]["linf_over_peak_scaled"])
    others = [v["linf_over_peak_scaled"] for k, v in ok.items() if k != best]
    rec["orientation"] = int(best)
    rec["margin"] = min(others) - ok[best]["linf_over_peak_scaled"]
    rec["pass"] = rec["margin"] >= 0.5
    _write(args.out, rec)
    print(json.dumps({"orientation": rec["orientation"], **ok[best], "margin": rec["margin"]}))


def cmd_score(args):
    t0 = time.perf_counter()
    meta = load_prep(args.prep)
    cat = json.loads(Path(args.cat).read_text(encoding="utf-8"))
    size = meta["size"]
    comps = components(cat)
    model, _ = read_fits(args.model)
    model = ORIENT[args.orient](model)
    model = np.nan_to_num(model)
    bt = truth_on_beam(comps, size, args.beam_px)
    label, grps = groups(comps, size, args.beam_px)
    sigma = sigma_of(meta, args.sigma)
    rec = measures(
        model_on_beam(model, args.beam_px), bt, model, label, grps, args.beam_px, sigma
    )
    rec.update(
        {
            "model": str(Path(args.model).resolve()),
            "orientation": args.orient,
            "beam_px": args.beam_px,
            "sigma": sigma,
        }
    )
    if not args.no_exact:
        ex = Exact(Path(args.prep))
        q, r = ex.score(model)
        ib = inner_box(size)
        rec["q_over_q0"] = q / meta["q0"]
        if meta.get("noise"):
            rec["q_over_q_truth"] = q / meta["noise"]["q_truth"]
        rec["exact_residual_inner_rms_sigma"] = float(np.sqrt(np.mean(r[ib] ** 2)) / sigma)
        rec["exact_residual_inner_peak_sigma"] = float(np.abs(r[ib]).max() / sigma)
    rec["seconds"] = time.perf_counter() - t0
    _write(args.out, rec)
    brief = {
        k: rec.get(k)
        for k in (
            "relative_l2",
            "relative_l2_extended",
            "extended_flux_all_pass",
            "positions_all_pass",
            "false_flux_abs",
            "exact_residual_inner_rms_sigma",
            "seconds",
        )
    }
    print(json.dumps(brief))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("beam")
    b.add_argument("psf")
    c = sub.add_parser("control")
    c.add_argument("prep")
    c.add_argument("cat")
    c.add_argument("out")
    c.add_argument("--beam-px", type=float, required=True)
    c.add_argument("--sigma", type=float)
    o = sub.add_parser("orient")
    o.add_argument("prep")
    o.add_argument("dirty")
    o.add_argument("out")
    s = sub.add_parser("score")
    s.add_argument("prep")
    s.add_argument("cat")
    s.add_argument("model")
    s.add_argument("out")
    s.add_argument("--beam-px", type=float, required=True)
    s.add_argument("--orient", type=int, default=0)
    s.add_argument("--sigma", type=float)
    s.add_argument("--no-exact", action="store_true")
    args = p.parse_args(argv)
    {"beam": cmd_beam, "control": cmd_control, "orient": cmd_orient, "score": cmd_score}[
        args.cmd
    ](args)


if __name__ == "__main__":
    main()
