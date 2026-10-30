"""Measures of big-plan task DF5-O (research/df5o-deconv-oracles.md, sections 2.4, 3, 4).

    python examples/compare_df5o.py p2 FIELD_DIR RUN_ROOT OUT.json
    python examples/compare_df5o.py floor FIELD_DIR OUT.json [--iterations 200] [--sweep-channel 8]
    python examples/compare_df5o.py measure FIELD_DIR ARM_DIR OUT.json [--floor FLOOR.json] [--p2 P2.json]
    python examples/compare_df5o.py archive FIELD_DIR RUN_ROOT OUT.json

`p2` compares each tool's dirty images and PSFs (WSClean's `dirty-r1`, pfb's
`grid-r1`) with the core's exact `fits_image` (eps 1e-9) per channel and for
the MFS, and finds pfb's FITS orientation. `floor` computes the misfit
floor `Q_inf` per channel by conjugate gradients
(`rang.core_clean.certified_clean`) and the truth's misfit. `measure`
scores one arm run (WSClean or pfb, from `run.json`): per truth source the
aperture flux, centroid and spectral index, the spurious flux, the
core-recomputed exact residual (RMS, peak), the tool's own residual and its
consistency with the exact one, Q/Q0, the reducible fractions and the
greedy ratio, and the tolerances A1/A2. `archive` gathers everything into
the results JSON (derived numbers only).

Images are in WSClean's FITS orientation, `(y, x)`; the core's gridder
layout is their transpose (`flip_v`, `flip_w`; research/df1-wgridder.md).
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_wgridder

ARCSEC = math.pi / (180 * 3600)
CELL = 2.0
NPIX = 1024
INNER = (slice(256, 768), slice(256, 768))
ORIENTATIONS = (
    "identity", "flipx", "flipy", "flipxy", "transpose", "transpose-flipx", "transpose-flipy", "transpose-flipxy",
)  # fmt: skip


# -- inputs -------------------------------------------------------------------


def load_field(field_dir):
    field_dir = Path(field_dir)
    field = json.loads((field_dir / "field.json").read_text())
    truth = json.loads((field_dir / "truth.json").read_text())
    with np.load(field_dir / "field.npz") as z:
        arrays = {k: z[k] for k in z.files}
    return field, truth, arrays


def read_fits(path):
    from astropy.io import fits

    with fits.open(path) as h:
        data = np.asarray(h[0].data, np.float64)
        header = dict(h[0].header)
    return data, header


def plane(data):
    """The (y, x) image of a FITS array with leading degenerate axes."""
    while data.ndim > 2:
        data = data[0]
    return data


def orient(image, name):
    """Apply one of the eight square symmetries (pfb's FITS to WSClean's)."""
    if name.startswith("transpose"):
        image = image.T
        name = name[len("transpose") :].lstrip("-") or "identity"
    if name in ("flipx", "flipxy"):
        image = image[:, ::-1]
    if name in ("flipy", "flipxy"):
        image = image[::-1, :]
    return np.ascontiguousarray(image)


# -- the core's exact operator --------------------------------------------------


def degrid(image_fits, uvw, freq, eps=1e-10):
    return core_wgridder.dirty2vis(
        uvw=uvw, freq=np.atleast_1d(freq), dirty=np.ascontiguousarray(image_fits.T, np.float64),
        pixsize_x=CELL * ARCSEC, pixsize_y=CELL * ARCSEC, epsilon=eps,
        do_wgridding=True, flip_v=True, flip_w=True, divide_by_n=False,
    )[:, 0]  # fmt: skip


def grid(vis, uvw, freq, weight, eps=1e-9):
    """Dirty image of one channel, FITS orientation, normalised by the
    weight sum (PSF peak one)."""
    w = np.full((len(vis), 1), weight)
    dirty = core_wgridder.vis2dirty(
        uvw=uvw, freq=np.atleast_1d(freq), vis=np.ascontiguousarray(vis[:, None], np.complex128), wgt=w,
        npix_x=NPIX, npix_y=NPIX, pixsize_x=CELL * ARCSEC, pixsize_y=CELL * ARCSEC, epsilon=eps,
        do_wgridding=True, flip_v=True, flip_w=True, divide_by_n=False,
    )  # fmt: skip
    return dirty.T / w.sum()


def exact_residual(models, arrays):
    """Per-channel exact residual images (FITS orientation, PSF peak one)
    and misfits Q_c = 1/2 sum w |V - A m|^2 / sum w of a (chan, y, x) model."""
    uvw, freqs, vis = arrays["uvw"], arrays["freqs"], arrays["vis_i"]
    weight = float(arrays["weight_i"])
    res = np.empty((len(freqs), NPIX, NPIX))
    q = np.empty(len(freqs))
    for c, f in enumerate(freqs):
        diff = vis[:, c] - (degrid(models[c], uvw, f) if np.any(models[c]) else 0.0)
        q[c] = 0.5 * float(
            np.sum(np.abs(diff) ** 2)
        )  # equal weights: sum w|d|^2 / sum w is the mean of |d|^2
        q[c] /= len(diff)
        res[c] = grid(diff, uvw, f, weight)
    return res, q


# -- apertures ------------------------------------------------------------------


def disc(x, y, radius_px, shape=(NPIX, NPIX)):
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    return (xx - x) ** 2 + (yy - y) ** 2 <= radius_px**2


def centroid(image, mask):
    w = np.where(mask, np.clip(image, 0, None), 0.0)
    s = w.sum()
    if s <= 0:
        return None
    yy, xx = np.indices(image.shape)
    return float((w * xx).sum() / s), float((w * yy).sum() / s)


def fit_alpha(freqs, fluxes, nu0):
    ok = fluxes > 0
    if ok.sum() < 3:
        return None
    x = np.log(freqs[ok] / nu0)
    a = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(a, np.log(fluxes[ok]), rcond=None)
    return float(coef[1])


def beam_area_px(field):
    return (
        math.pi
        / (4 * math.log(2))
        * field["psf"]["fwhm_major_px"]
        * field["psf"]["fwhm_minor_px"]
    )


def score_sources(model_cube, truth_cube, field, truth):
    """Per truth source: aperture flux, centroid, spectral index; and the
    spurious flux outside every aperture."""
    sigma = field["noise"]["sigma_img_mfs_jy"]
    beam_px = field["psf"]["fwhm_major_px"]
    freqs = np.array(field["geometry"]["freqs_hz"])
    nu0 = truth["nu0_hz"]
    mm, tm = model_cube.mean(0), truth_cube.mean(0)
    outside = np.ones(mm.shape, bool)
    rows = []
    for s in truth["sources"]:
        r_px = s["radius"] / CELL
        mask = disc(s["x"], s["y"], r_px)
        outside &= ~mask
        n_beams = mask.sum() / beam_area_px(field)
        sig_ap = sigma * math.sqrt(max(n_beams, 1.0))
        s_true, s_mod = float(tm[mask].sum()), float(mm[mask].sum())
        ct, cm = centroid(tm, mask), centroid(mm, mask)
        offset = None if cm is None else math.hypot(cm[0] - ct[0], cm[1] - ct[1]) * CELL
        row = {
            "name": s["name"], "kind": s["kind"], "radius_arcsec": s["radius"], "aperture_px": int(mask.sum()),
            "sigma_ap_jy": sig_ap, "s_truth_jy": s_true, "s_model_jy": s_mod, "ds_jy": s_mod - s_true,
            "ds_rel": (s_mod - s_true) / s_true, "ds_over_sigma_ap": (s_mod - s_true) / sig_ap,
            "snr_truth": s_true / sig_ap, "offset_arcsec": offset,
            "offset_over_beam": None if offset is None else offset / (beam_px * CELL),
        }  # fmt: skip
        if s_true >= 100 * sig_ap:
            ft = np.array([truth_cube[c][mask].sum() for c in range(len(freqs))])
            fm = np.array([model_cube[c][mask].sum() for c in range(len(freqs))])
            row["alpha_truth"], row["alpha_model"] = (
                fit_alpha(freqs, ft, nu0),
                fit_alpha(freqs, fm, nu0),
            )
        rows.append(row)
    spurious = {
        "positive_jy": float(np.clip(mm[outside], 0, None).sum()),
        "negative_jy": float(np.clip(mm[outside], None, 0).sum()),
        "pixels_nonzero": int(np.count_nonzero(mm[outside])),
    }
    return rows, spurious, outside


def tolerances(rows, totals, field):
    """A1 and A2 of the protocol (section 4) on one model."""
    beam_px = field["psf"]["fwhm_major_px"]
    a1_total = (
        abs(totals["model_mfs_jy"] - totals["truth_mfs_jy"])
        <= 0.02 * totals["truth_mfs_jy"]
    )
    bright = [r for r in rows if r["snr_truth"] >= 20]
    a1_fail = [
        r["name"]
        for r in bright
        if abs(r["ds_jy"]) > 0.05 * r["s_truth_jy"] + 3 * r["sigma_ap_jy"]
    ]
    a2_fail = []
    for r in bright:
        limit = (0.1 if r["kind"] == "point" else 0.25) * beam_px * CELL
        if r["offset_arcsec"] is None or r["offset_arcsec"] > limit:
            a2_fail.append(r["name"])
    return {
        "A1_total": bool(a1_total), "A1_components_tested": len(bright), "A1_failures": a1_fail,
        "A1": bool(a1_total and not a1_fail), "A2_failures": a2_fail, "A2": not a2_fail,
    }  # fmt: skip


def image_stats(img, sigma):
    return {
        "rms_inner_jy": float(np.sqrt(np.mean(img[INNER] ** 2))),
        "rms_jy": float(np.sqrt(np.mean(img**2))),
        "peak_abs_jy": float(np.abs(img).max()),
        "rms_inner_over_sigma": float(np.sqrt(np.mean(img[INNER] ** 2)) / sigma),
        "peak_over_sigma": float(np.abs(img).max() / sigma),
    }


# -- the tools' outputs -----------------------------------------------------------


def wsclean_outputs(arm_dir, arm):
    d = Path(arm_dir)
    models = np.stack(
        [plane(read_fits(d / f"{arm}-{c:04d}-model.fits")[0]) for c in range(16)]
    )
    residual = plane(read_fits(d / f"{arm}-MFS-residual.fits")[0])
    extra = {}
    src = d / f"{arm}-sources.txt"
    if src.exists():
        from rang.formats import sky

        sources = sky.load_wsclean(src)
        list_flux, model_flux = [], []
        for c in range(16):
            _, hdr = read_fits(d / f"{arm}-{c:04d}-model.fits")
            f = float(hdr["CRVAL3"])
            list_flux.append(float(sum(s.flux(f) for s in sources)))
            model_flux.append(float(models[c].sum()))
        rel = [abs(a - b) / abs(b) for a, b in zip(list_flux, model_flux, strict=True)]
        extra["source_list"] = {
            "components": len(sources),
            "gaussians": sum(s.gaussian for s in sources),
            "log_si": sorted({s.log_si for s in sources}),
            "list_flux_per_channel_jy": list_flux,
            "model_flux_per_channel_jy": model_flux,
            "max_rel_diff_list_vs_model": max(rel),
        }
    return models, residual, extra


def pfb_outputs(arm_dir, orientation):
    d = Path(arm_dir)
    cube = [
        p
        for p in sorted(d.glob("*_main_model*.fits"))
        if "mfs" not in p.name.lower() and "postmop" not in p.name
    ]
    cube = [
        p
        for p in cube
        if not any(ch.isdigit() for ch in p.stem.split("_model")[-1].strip("_")[:1])
    ]
    if not cube:
        raise FileNotFoundError(f"no pfb model cube in {d}")
    data, _ = read_fits(cube[0])
    data = data[0] if data.ndim == 4 else data
    models = np.stack([orient(data[c], orientation) for c in range(data.shape[0])])
    res = [p for p in sorted(d.glob("*_main_residual*mfs*.fits"))]
    residual = orient(plane(read_fits(res[0])[0]), orientation) if res else None
    return (
        models,
        residual,
        {"model_file": cube[0].name, "residual_file": res[0].name if res else None},
    )


# -- commands -------------------------------------------------------------------------


def cmd_p2(args):
    _field, _, arrays = load_field(args.field)
    uvw, freqs, vis = arrays["uvw"], arrays["freqs"], arrays["vis_i"]
    weight = float(arrays["weight_i"])
    root = Path(args.root)
    rec = {"wsclean": {"channels": []}, "pfb": {}}
    core_dirty, core_psf = [], []
    for c, f in enumerate(freqs):
        core = core_wgridder.fits_image(
            uvw,
            freqs[c : c + 1],
            vis[:, c : c + 1],
            np.full((len(vis), 1), weight),
            NPIX,
            NPIX,
            CELL,
            epsilon=1e-9,
        )
        core_dirty.append(core["dirty"])
        core_psf.append(core["psf"])
    core_dirty, core_psf = np.stack(core_dirty), np.stack(core_psf)
    mfs_dirty, _mfs_psf = core_dirty.mean(0), core_psf.mean(0)
    ws = root / "wsclean" / "dirty-r1"
    if ws.exists():
        worst_d = worst_p = 0.0
        for c in range(len(freqs)):
            d, hd = read_fits(ws / f"dirty-{c:04d}-dirty.fits")
            p, _ = read_fits(ws / f"dirty-{c:04d}-psf.fits")
            d, p = plane(d), plane(p)
            ld = float(np.abs(d - core_dirty[c]).max() / np.abs(core_dirty[c]).max())
            lp = float(np.abs(p - core_psf[c]).max())
            worst_d, worst_p = max(worst_d, ld), max(worst_p, lp)
            rec["wsclean"]["channels"].append(
                {"channel": c, "dirty_linf_over_peak": ld, "psf_linf": lp,
                 "WSCNVIS": hd.get("WSCNVIS"), "WSCIMGWG": hd.get("WSCIMGWG")}
            )  # fmt: skip
        d, _ = read_fits(ws / "dirty-MFS-dirty.fits")
        d = plane(d)
        rec["wsclean"]["mfs_dirty_linf_over_peak"] = float(
            np.abs(d - mfs_dirty).max() / np.abs(mfs_dirty).max()
        )
        rec["wsclean"]["worst_dirty_linf_over_peak"] = worst_d
        rec["wsclean"]["worst_psf_linf"] = worst_p
        rec["wsclean"]["core_weight_sum_per_channel"] = weight * len(vis)
        rec["wsclean"]["pass"] = bool(
            max(worst_d, worst_p, rec["wsclean"]["mfs_dirty_linf_over_peak"]) <= 1e-5
        )
    pfb = root / "pfb" / "grid-r1"
    if pfb.exists():
        dirty_cube = [
            p
            for p in sorted(pfb.glob("*_main_dirty*.fits"))
            if "mfs" not in p.name.lower()
        ]
        psf_cube = [
            p
            for p in sorted(pfb.glob("*_main_psf*.fits"))
            if "mfs" not in p.name.lower()
        ]
        rec["pfb"]["files"] = [p.name for p in sorted(pfb.glob("*.fits"))]
        if dirty_cube:
            dc, hdr = read_fits(dirty_cube[0])
            dc = dc[0] if dc.ndim == 4 else dc
            # orientation from channel 0's dirty image
            scores = {}
            for name in ORIENTATIONS:
                o = orient(dc[0], name)
                if o.shape != core_dirty[0].shape:
                    continue
                scores[name] = float(
                    np.abs(o - core_dirty[0]).max() / np.abs(core_dirty[0]).max()
                )
            best = min(scores, key=scores.get)
            rec["pfb"]["orientation_scores"] = scores
            rec["pfb"]["orientation"] = best
            worst = 0.0
            per = []
            for c in range(dc.shape[0]):
                o = orient(dc[c], best)
                ld = float(
                    np.abs(o - core_dirty[c]).max() / np.abs(core_dirty[c]).max()
                )
                per.append(ld)
                worst = max(worst, ld)
            rec["pfb"]["dirty_linf_over_peak_per_channel"] = per
            rec["pfb"]["worst_dirty_linf_over_peak"] = worst
            rec["pfb"]["header_crpix"] = [hdr.get("CRPIX1"), hdr.get("CRPIX2")]
            if psf_cube:
                pc, _ = read_fits(psf_cube[0])
                pc = pc[0] if pc.ndim == 4 else pc
                ny, nx = pc.shape[-2:]
                # pfb's PSF is larger than the image (psf-oversize): compare the central NPIX^2
                y0, x0 = (ny - NPIX) // 2, (nx - NPIX) // 2
                worst_p = 0.0
                for c in range(pc.shape[0]):
                    p = orient(pc[c], best)
                    p = (
                        p[y0 : y0 + NPIX, x0 : x0 + NPIX]
                        if p.shape != (NPIX, NPIX)
                        else p
                    )
                    worst_p = max(
                        worst_p, float(np.abs(p / p.max() - core_psf[c]).max())
                    )
                rec["pfb"]["psf_shape"] = [int(ny), int(nx)]
                rec["pfb"]["worst_psf_linf_central"] = worst_p
            rec["pfb"]["pass"] = bool(worst <= 1e-5)
    Path(args.out).write_text(json.dumps(rec, indent=1))
    print(
        json.dumps(
            {
                k: {kk: vv for kk, vv in v.items() if kk != "channels"}
                for k, v in rec.items()
            },
            indent=1,
        )
    )


def cmd_floor(args):
    from rang import core_clean

    _field, _truth, arrays = load_field(args.field)
    uvw, freqs, vis = arrays["uvw"], arrays["freqs"], arrays["vis_i"]
    weight = float(arrays["weight_i"])
    rec = {"iterations": args.iterations, "channels": []}
    t0 = time.perf_counter()
    _, q_truth = exact_residual(arrays["truth_cube"], arrays)
    rec["q_truth_per_channel"] = q_truth.tolist()
    rec["q_truth"] = float(q_truth.mean())
    rec["q0_per_channel_python"] = [
        0.5 * float(np.mean(np.abs(vis[:, c]) ** 2)) for c in range(len(freqs))
    ]
    rec["q0"] = float(np.mean(rec["q0_per_channel_python"]))

    def floor(c, iterations):
        t = time.perf_counter()
        out = core_clean.certified_clean(
            uvw, freqs[c : c + 1], vis[:, c : c + 1], np.full((len(vis), 1), weight),
            side=NPIX, scale_arcsec=CELL, epsilon=1e-9, gain=0.1, threshold=1e9, max_components=0,
            max_major=1, beam="image", floor_iterations=iterations,
        )  # fmt: skip
        s = out["summary"]
        return {
            "channel": c, "iterations": iterations, "q0_core": s["q0"], "q_floor": s["q_floor"],
            "floor_iterations": s["floor_iterations"], "floor_relative_residual": s["floor_relative_residual"],
            "seconds": time.perf_counter() - t,
        }  # fmt: skip

    for c in range(len(freqs)):
        row = floor(c, args.iterations)
        row["q0_python"] = rec["q0_per_channel_python"][c]
        rec["channels"].append(row)
        print(json.dumps(row), flush=True)
    if args.sweep_channel is not None:
        rec["sweep"] = [floor(args.sweep_channel, n) for n in (100, 200, 400)]
    rec["q_floor"] = float(np.mean([r["q_floor"] for r in rec["channels"]]))
    rec["q0_core_vs_python_max_rel"] = max(
        abs(r["q0_core"] - r["q0_python"]) / r["q0_python"] for r in rec["channels"]
    )
    rec["seconds"] = time.perf_counter() - t0
    Path(args.out).write_text(json.dumps(rec, indent=1))
    print(
        json.dumps(
            {
                k: rec[k]
                for k in (
                    "q0",
                    "q_truth",
                    "q_floor",
                    "q0_core_vs_python_max_rel",
                    "seconds",
                )
            }
        )
    )


def cmd_measure(args):
    field, truth, arrays = load_field(args.field)
    sigma = field["noise"]["sigma_img_mfs_jy"]
    arm_dir = Path(args.arm_dir)
    run = json.loads((arm_dir / "run.json").read_text())
    arm = run["arm"]
    t0 = time.perf_counter()
    if arm.startswith("ws-"):
        models, tool_residual, extra = wsclean_outputs(arm_dir, arm)
        tool = "wsclean"
    else:
        p2 = json.loads(Path(args.p2).read_text())
        models, tool_residual, extra = pfb_outputs(arm_dir, p2["pfb"]["orientation"])
        tool = "pfb"
    truth_cube = arrays["truth_cube"]
    rows, spurious, _ = score_sources(models, truth_cube, field, truth)
    totals = {
        "model_mfs_jy": float(models.mean(0).sum()),
        "truth_mfs_jy": float(truth_cube.mean(0).sum()),
    }
    totals["ratio"] = totals["model_mfs_jy"] / totals["truth_mfs_jy"]
    res, q = exact_residual(models, arrays)
    res_mfs = res.mean(0)
    rec = {
        "arm": arm, "repeat": run["repeat"], "tool": tool, "returncode": run["returncode"],
        "sources": rows, "spurious": spurious, "totals": totals,
        "exact_residual": image_stats(res_mfs, sigma),
        "q": float(q.mean()), "q_per_channel": q.tolist(), "extra": extra,
    }  # fmt: skip
    if tool_residual is not None:
        rec["tool_residual"] = image_stats(tool_residual, sigma)
        diff = tool_residual - res_mfs
        rec["consistency"] = {
            "linf_jy": float(np.abs(diff).max()), "rms_jy": float(np.sqrt(np.mean(diff**2))),
            "linf_over_sigma": float(np.abs(diff).max() / sigma),
        }  # fmt: skip
    if args.floor:
        fl = json.loads(Path(args.floor).read_text())
        q0, qf, qt = fl["q0"], fl["q_floor"], fl["q_truth"]
        rec["q_over_q0"] = rec["q"] / q0
        rec["reducible_fraction"] = (rec["q"] - qf) / (q0 - qf)
        rec["signal_fraction_left"] = (rec["q"] - qt) / (q0 - qt)
        rec["kappa_mfs"] = float(np.abs(res_mfs).max() ** 2 / (2 * (rec["q"] - qf)))
        kap = [
            float(
                np.abs(res[c]).max() ** 2 / (2 * (q[c] - fl["channels"][c]["q_floor"]))
            )
            for c in range(len(q))
        ]
        rec["kappa_channel_median"] = float(np.median(kap))
    rec["tolerances"] = tolerances(rows, totals, field)
    rec["cost"] = cost(run)
    rec["seconds"] = time.perf_counter() - t0
    Path(args.out).write_text(json.dumps(rec, indent=1))
    brief = {
        k: rec[k]
        for k in (
            "arm",
            "repeat",
            "totals",
            "exact_residual",
            "q",
            "tolerances",
            "cost",
        )
    }
    print(json.dumps(brief, indent=1))


def cost(run):
    if "steps" in run:  # pfb
        steps = {
            s["step"]: {"wall_s": s["docker_wall_s"], **s["time_v"]}
            for s in run["steps"]
        }
        return {
            "docker_wall_s": run["docker_wall_s"],
            "peak_rss_mb": max(
                (s.get("peak_rss_mb", 0) for s in steps.values()), default=None
            ),
            "steps": steps,
        }
    return {
        "docker_wall_s": run["docker_wall_s"],
        **run["time_v"],
        "log": run.get("log", {}),
    }


def spread(runs, key_path):
    vals = []
    for r in runs:
        v = r
        for k in key_path:
            v = v[k]
        vals.append(v)
    return float(max(vals) - min(vals)) if len(vals) > 1 else None


def summarise(m):
    """The per-run numbers the archive keeps (per-source rows included)."""
    out = {
        k: m[k]
        for k in (
            "returncode", "totals", "exact_residual", "tool_residual", "consistency", "q",
            "q_over_q0", "reducible_fraction", "signal_fraction_left", "kappa_mfs",
            "kappa_channel_median", "spurious", "tolerances", "cost", "extra",
        )
        if k in m
    }  # fmt: skip
    out["sources"] = m["sources"]
    return out


MATCHED = {"hogbom": ("ws-hogbom", "pfb-clark"), "multiscale": ("ws-multiscale",)}


def acceptance(arms):
    """DF5's A3/A4 bounds from the matched oracles (protocol section 4)."""
    out = {}
    for cls, names in MATCHED.items():
        have = [n for n in names if n in arms]
        if not have:
            continue
        rms = {
            n: min(
                r["exact_residual"]["rms_inner_jy"] for r in arms[n]["runs"].values()
            )
            for n in have
        }
        red = {
            n: min(r["reducible_fraction"] for r in arms[n]["runs"].values())
            for n in have
        }
        spreads = [arms[n]["spread"]["rms_inner_jy"] or 0.0 for n in have]
        best = min(rms.values())
        margin = max(0.02 * best, 2 * max(spreads))
        rbest = min(red.values())
        rspreads = [arms[n]["spread"]["reducible_fraction"] or 0.0 for n in have]
        out[cls] = {
            "matched_oracles": have,
            "rms_inner_jy": rms,
            "A3_rms_inner_bound_jy": best + margin,
            "A3_margin_jy": margin,
            "reducible_fraction": red,
            "A4_reducible_bound": rbest + max(0.02 * rbest, 2 * max(rspreads)),
        }
    return out


def cmd_archive(args):
    import hashlib
    import subprocess

    field_dir, root = Path(args.field), Path(args.root)
    field = json.loads((field_dir / "field.json").read_text())
    truth = json.loads((field_dir / "truth.json").read_text())
    measures = sorted((root / "measures").glob("*.json"))
    arms = {}
    for path in measures:
        m = json.loads(path.read_text())
        arms.setdefault(m["arm"], {"tool": m["tool"], "runs": {}})["runs"][
            str(m["repeat"])
        ] = summarise(m)
    for name, a in arms.items():
        runs = list(a["runs"].values())
        ok = [r for r in runs if r["returncode"] == 0]
        a["spread"] = {
            "rms_inner_jy": spread(ok, ("exact_residual", "rms_inner_jy")),
            "peak_abs_jy": spread(ok, ("exact_residual", "peak_abs_jy")),
            "model_mfs_jy": spread(ok, ("totals", "model_mfs_jy")),
            "reducible_fraction": spread(ok, ("reducible_fraction",)) if all("reducible_fraction" in r for r in ok) else None,
            "max_source_flux_jy": (
                max(abs(a1["s_model_jy"] - a2["s_model_jy"]) for a1, a2 in zip(ok[0]["sources"], ok[1]["sources"], strict=True))
                if len(ok) > 1 else None
            ),
        }  # fmt: skip
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()
    pre = {}
    for name in ("p1-ocasa", "p1-pfb", "p2"):
        f = root / "precondition" / f"{name}.json"
        if f.exists():
            rec = json.loads(f.read_text())
            if name == "p2":
                for tool in rec.values():
                    tool.pop("channels", None)
            pre[name] = rec
    floor = (
        json.loads((root / "floor.json").read_text())
        if (root / "floor.json").exists()
        else None
    )
    images = {}
    for f in sorted((root.parent / "df5o-20261031-00").glob("*-image.json")):
        images[f.stem] = json.loads(f.read_text())
    keep = {
        k: field[k]
        for k in (
            "settings",
            "geometry",
            "noise",
            "psf",
            "checks",
            "truth",
            "timings",
            "peak_rss_mb",
        )
    }
    keep["geometry"] = {k: v for k, v in keep["geometry"].items()}
    keep["hashes"] = {
        k: field["hashes"][k]
        for k in ("ms_digest", "files", "columns", "vis_i", "truth_cube")
    }
    out = {
        "task": "DF5-O",
        "protocol": "research/df5o-deconv-oracles.md",
        "code_commit": commit,
        "run": str(root),
        "field": keep,
        "truth": truth,
        "preconditions": pre,
        "floor": floor,
        "images": images,
        "arms": arms,
        "acceptance": acceptance(arms),
        "measure_files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in measures
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["acceptance"], indent=1))


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("p2")
    a.add_argument("field")
    a.add_argument("root")
    a.add_argument("out")
    f = sub.add_parser("floor")
    f.add_argument("field")
    f.add_argument("out")
    f.add_argument("--iterations", type=int, default=200)
    f.add_argument("--sweep-channel", type=int, default=None)
    m = sub.add_parser("measure")
    m.add_argument("field")
    m.add_argument("arm_dir")
    m.add_argument("out")
    m.add_argument("--floor")
    m.add_argument("--p2")
    r = sub.add_parser("archive")
    r.add_argument("field")
    r.add_argument("root")
    r.add_argument("out")
    args = p.parse_args()
    {"p2": cmd_p2, "floor": cmd_floor, "measure": cmd_measure, "archive": cmd_archive}[
        args.cmd
    ](args)


if __name__ == "__main__":
    sys.exit(main())
