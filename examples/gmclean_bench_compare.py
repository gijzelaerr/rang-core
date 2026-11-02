"""Score any imager's CLEAN output against a truth catalogue (gmclean benchmark).

Research note: research/gmclean-benchmark.md. Three subcommands:

prepare MS CATALOGUE OUT_DIR
    Reads the Measurement Set through rang's own reader (`rang.core_ms`),
    forms WSClean's `-pol I` Stokes I and Briggs 0.5 weights on the padded
    weight grid (as examples/clean_certified_export.py), and writes
    uvw.f64, freq.f64, vis.c128, wgt.f64 (gridding weight = Stokes I weight
    x Briggs weight) and meta.json. It makes the core's exact dirty image and
    PSF (WSClean FITS order) and compares them with WSClean `-niter 0`
    images (`--wsclean-dirty PREFIX`, repeatable): L-inf over the peak, the
    peak position against the brightest catalogue component, WSCNVIS and
    WSCIMGWG against rang's visibility count and weight sum. With `--noise`
    (the simulator's Stokes I noise, complex64 (row, chan)) it images the
    noise alone with natural and with Briggs weights (measured image noise)
    and records Q_truth = 1/2 sum w |n|^2 / sum w, the misfit of the true
    sky, an absolute floor for every imager's Q.

score PREP_DIR CATALOGUE RUN_DIR OUT_JSON [--jobs NAME ...]
    For every job NAME in RUN_DIR (default: every NAME-model.fits) reads
    NAME-{model,residual,image}.fits (WSClean's FITS orientation), the log,
    timing/NAME.txt (GNU time -v), load/NAME.txt and NAME-report.json if
    present, and computes: residual rms and peak in the inner field (the
    central 2N/3 box), dynamic range (restored peak / residual rms), per-
    source flux recovery (model flux within one beam of a true position,
    each model pixel given to its nearest true source) with mean and scatter
    per flux decade, false components (model pixels farther than two beams
    from every true source), total model flux error, the disc's flux, centroid
    and second-moment FWHM (S2), the calibrator flux against the catalogue
    flux (slice), and the exact misfit Q/Q_0 of the model through the core's
    exact gridder (the same quadratic for every imager: the prepare step's
    weights, w-gridding, WSClean's flips), with the exact residual's rms and
    peak.

truth PREP_DIR CATALOGUE RUN_DIR [--name truth]
    Writes the catalogue pixelised on the image grid as NAME-model.fits with
    its exact residual, to check the metrics and give the on-grid misfit.

tables JSON [JSON ...]
    Markdown tables of scored runs (for the note and the paper).

Usage:
    .venv/bin/python examples/gmclean_bench_compare.py prepare MS CAT OUT --size 2048 \
        --scale 1.5 [--datacol DATA] [--field 0] [--noise NOISE.c64] [--wsclean-dirty P]
    .venv/bin/python examples/gmclean_bench_compare.py score PREP CAT RUN OUT.json
    .venv/bin/python examples/gmclean_bench_compare.py tables OUT.json ...
"""

import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_weights, core_wgridder
from rang.core_imaging import read_fits
from scipy.spatial import cKDTree

ARCSEC = math.pi / (180.0 * 3600.0)
ROBUST = 0.5


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def catalogue(path):
    """Catalogue dict: the simulator's JSON, or a slice record
    {"components": [{"x", "y", "flux", "kind"}], "image": {...}}."""
    return _read_json(path)


# -- prepare ------------------------------------------------------------------


def read_ms(ms, datacol):
    with core_ms.open_table(ms) as t:
        cols = {
            n: t.getcol(n)
            for n in (
                "UVW",
                datacol,
                "FLAG",
                "FLAG_ROW",
                "WEIGHT_SPECTRUM",
                "FIELD_ID",
                "ANTENNA1",
                "ANTENNA2",
                "DATA_DESC_ID",
            )
        }
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as spw:
        cols["CHAN_FREQ"] = spw.getcol("CHAN_FREQ")[0]
    with core_ms.open_table(Path(ms) / "POLARIZATION") as pol:
        cols["CORR_TYPE"] = pol.getcol("CORR_TYPE")[0]
    return cols


def weights(uvw, freq, weight, rows, size, scale):
    padded = core_weights.padded_size(size)
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freq),
        weight,
        rows,
        mode="briggs",
        robust=ROBUST,
        width=padded,
        height=padded,
        pixel_scale=core_weights.pixel_scale_radians(scale),
        return_grid=False,
    )
    gw = weight.astype(np.float64) * imaging["weights"].astype(np.float64)
    gw[~rows] = 0.0
    return gw, padded, imaging["sums"]


def brightest_peak(cat):
    """FITS (y, x) pixel of the component with the highest peak per beam:
    point sources first (a disc's peak is far below its flux)."""
    points = [c for c in cat["components"] if c["kind"] == "point"]
    if not points:
        return None
    c = max(points, key=lambda c: c["flux"])
    return [round(c["y"]), round(c["x"])], c["flux"]


def prepare(args):
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    cols = read_ms(args.ms, args.datacol)
    t_read = time.perf_counter()
    if tuple(int(c) for c in cols["CORR_TYPE"]) != (9, 10, 11, 12):
        raise SystemExit("XX, XY, YX, YY correlations required")
    rows = (
        (cols["FIELD_ID"] == args.field)
        & (cols["ANTENNA1"] != cols["ANTENNA2"])
        & (cols["DATA_DESC_ID"] == 0)
        & ~np.asarray(cols["FLAG_ROW"], bool)
    )
    vis, weight = core_weights.stokes_i(
        cols[args.datacol], cols["WEIGHT_SPECTRUM"], cols["FLAG"]
    )
    freq = np.ascontiguousarray(cols["CHAN_FREQ"], np.float64)
    uvw = np.ascontiguousarray(cols["UVW"], np.float64)
    gw, padded, sums = weights(uvw, freq, weight, rows, args.size, args.scale)
    vis128 = np.ascontiguousarray(vis, np.complex128)
    del cols, vis
    t_w = time.perf_counter()
    images = core_wgridder.fits_image(
        uvw, freq, vis128, gw, args.size, args.size, args.scale, epsilon=args.epsilon
    )
    t_img = time.perf_counter()
    cat = catalogue(args.catalogue)
    bright = brightest_peak(cat)
    q0 = 0.5 * float(np.sum(gw * np.abs(vis128) ** 2) / gw.sum())
    meta = {
        "ms": str(Path(args.ms).resolve()),
        "catalogue": str(Path(args.catalogue).resolve()),
        "catalogue_sha256": _sha(args.catalogue),
        "datacol": args.datacol,
        "field": args.field,
        "size": args.size,
        "scale_arcsec": args.scale,
        "epsilon": args.epsilon,
        "weighting": f"briggs {ROBUST}, padded weight grid {padded}",
        "nrow": int(uvw.shape[0]),
        "nchan": int(freq.size),
        "active_visibilities": int(np.count_nonzero(gw)),
        "gridding_weight_sum": float(gw.sum()),
        "imaging_weight_sums": sums,
        "q0": q0,
        "core_dirty_peak": float(images["dirty"].max()),
        "core_dirty_argmax_yx": [
            int(i)
            for i in np.unravel_index(np.argmax(images["dirty"]), images["dirty"].shape)
        ],
        "brightest_point_yx_flux": bright,
        "comparisons": {},
    }
    for prefix in args.wsclean_dirty:
        d, h = read_fits(f"{prefix}-dirty.fits")
        psf, hp = read_fits(f"{prefix}-psf.fits")
        peak = float(np.abs(d).max())
        inner = slice(args.size // 4, 3 * args.size // 4)
        k = [int(i) for i in np.unravel_index(np.argmax(d), d.shape)]
        meta["comparisons"][Path(prefix).name] = {
            "dirty_sha256": _sha(f"{prefix}-dirty.fits"),
            "dirty_linf_over_peak": float(np.abs(images["dirty"] - d).max() / peak),
            "dirty_inner_half_linf_over_peak": float(
                np.abs(images["dirty"][inner, inner] - d[inner, inner]).max() / peak
            ),
            "psf_linf": float(np.abs(images["psf"] - psf).max()),
            "wsclean_dirty_peak": float(d.max()),
            "wsclean_dirty_argmax_yx": k,
            "peak_at_brightest_point": bool(bright and k == bright[0]),
            "wscnvis": float(h.get("WSCNVIS", float("nan"))),
            "wscimgwg": float(h.get("WSCIMGWG", float("nan"))),
            "crpix": [h["CRPIX1"], h["CRPIX2"]],
            "cdelt_arcsec": [h["CDELT1"] * 3600, h["CDELT2"] * 3600],
            "psf_bmaj_arcsec": float(hp.get("BMAJ", float("nan"))) * 3600,
            "psf_bmin_arcsec": float(hp.get("BMIN", float("nan"))) * 3600,
            "psf_bpa_deg": float(hp.get("BPA", float("nan"))),
        }
    if args.noise:
        n = np.fromfile(args.noise, np.complex64).reshape(vis128.shape)
        n128 = n.astype(np.complex128)
        nat = core_wgridder.fits_image(
            uvw,
            freq,
            n128,
            (gw > 0).astype(np.float64),
            args.size,
            args.size,
            args.scale,
            epsilon=1e-6,
        )["dirty"]
        bri = core_wgridder.fits_image(
            uvw, freq, n128, gw, args.size, args.size, args.scale, epsilon=1e-6
        )["dirty"]
        sig = float(np.std(n.real))
        meta["noise"] = {
            "file": str(Path(args.noise).resolve()),
            "sha256": _sha(args.noise),
            "stokes_i_sigma_per_component_measured": sig,
            "natural_image_rms": float(np.sqrt(np.mean(nat**2))),
            "briggs_image_rms": float(np.sqrt(np.mean(bri**2))),
            "briggs_image_rms_predicted": float(
                sig * math.sqrt(np.sum(gw**2)) / gw.sum()
            ),
            "q_truth": 0.5 * float(np.sum(gw * np.abs(n128) ** 2) / gw.sum()),
        }
        meta["noise"]["q_truth_over_q0"] = meta["noise"]["q_truth"] / q0
        del n, n128, nat, bri
    uvw.tofile(out / "uvw.f64")
    freq.tofile(out / "freq.f64")
    vis128.tofile(out / "vis.c128")
    np.ascontiguousarray(gw).tofile(out / "wgt.f64")
    np.save(out / "core-dirty-fits-order.npy", images["dirty"].astype(np.float32))
    np.save(out / "core-psf-fits-order.npy", images["psf"].astype(np.float32))
    meta["seconds"] = {
        "read": t_read - t0,
        "stokes_and_weights": t_w - t_read,
        f"core_dirty_psf_eps{args.epsilon:g}": t_img - t_w,
        "total": time.perf_counter() - t0,
    }
    _write_json(out / "meta.json", meta)
    print(
        json.dumps(
            {k: v for k, v in meta.items() if k != "imaging_weight_sums"}, indent=1
        )
    )


# -- score --------------------------------------------------------------------


class Exact:
    """Q and the exact residual of FITS-order models (the prepare arrays)."""

    def __init__(self, prep):
        self.meta = _read_json(prep / "meta.json")
        nrow, nchan = self.meta["nrow"], self.meta["nchan"]
        self.size = self.meta["size"]
        self.uvw = np.fromfile(prep / "uvw.f64").reshape(nrow, 3)
        self.freq = np.fromfile(prep / "freq.f64")
        self.vis = np.fromfile(prep / "vis.c128", np.complex128).reshape(nrow, nchan)
        w = np.fromfile(prep / "wgt.f64").reshape(nrow, nchan)
        self.wgt = w / w.sum()
        scale = self.meta["scale_arcsec"] * ARCSEC
        self.kw = {
            "pixsize_x": scale,
            "pixsize_y": scale,
            "epsilon": self.meta["epsilon"],
            "flip_v": True,
            "flip_w": True,
        }

    def score(self, model):
        m = np.ascontiguousarray(model.T, np.float64)
        e = self.vis - core_wgridder.dirty2vis(
            uvw=self.uvw, freq=self.freq, dirty=m, **self.kw
        )
        q = 0.5 * float(np.sum(self.wgt * np.abs(e) ** 2))
        r = core_wgridder.vis2dirty(
            uvw=self.uvw,
            freq=self.freq,
            vis=e,
            wgt=self.wgt,
            npix_x=self.size,
            npix_y=self.size,
            **self.kw,
        )
        return q, r.T


def inner_box(size):
    lo = size // 2 - size // 3
    hi = size // 2 + size // 3
    return slice(lo, hi), slice(lo, hi)


def time_v(path):
    """GNU time -v fields."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    pats = {
        "user_s": r"User time \(seconds\): ([\d.]+)",
        "system_s": r"System time \(seconds\): ([\d.]+)",
        "cpu_percent": r"Percent of CPU this job got: (\d+)%",
        "max_rss_kb": r"Maximum resident set size \(kbytes\): (\d+)",
        "exit_status": r"Exit status: (\d+)",
    }
    for k, p in pats.items():
        m = re.search(p, text)
        if m:
            out[k] = float(m.group(1))
    m = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", text)
    if m:
        parts = [float(x) for x in m.group(1).split(":")]
        out["wall_s"] = sum(v * 60**i for i, v in enumerate(reversed(parts)))
    if "user_s" in out:
        out["cpu_s"] = out["user_s"] + out.get("system_s", 0.0)
    return out


def wsclean_log(path):
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    iters = [int(x) for x in re.findall(r"Performed (\d+) iterations in total", text)]
    majors = re.findall(r"(\d+) major iterations were performed", text)
    logged = [int(x) for x in re.findall(r"^Iteration (\d+):", text, re.MULTILINE)]
    timing = re.findall(
        r"Inversion: ([\d:.]+), prediction: ([\d:.]+), deconvolution: ([\d:.]+)", text
    )

    def secs(s):
        parts = [float(x) for x in s.split(":")]
        return sum(v * 60**i for i, v in enumerate(reversed(parts)))

    rec = {
        "components": iters[-1] if iters else None,
        "major_iterations": int(majors[-1]) if majors else None,
        "diverged": "divergence" in text.lower(),
        # The plain minor loop only logs every 10th or 100th iteration: a lower
        # bound on its component count.
        "last_logged_iteration": max(logged) if logged else None,
        "auto_threshold_lines": re.findall(r"Estimated standard deviation[^\n]*", text)[
            -3:
        ],
    }
    if timing:
        inv, pred, dec = timing[-1]
        rec.update(
            inversion_s=secs(inv), prediction_s=secs(pred), deconvolution_s=secs(dec)
        )
    return rec


def flux_metrics(model, cat, beam_px):
    """Per-source recovery, false components and disc moments."""
    comps = cat["components"]
    yy, xx = np.nonzero(model)
    vals = model[yy, xx]
    out = {
        "model_pixels": int(vals.size),
        "model_flux_total": float(vals.sum()),
        "model_flux_negative": float(vals[vals < 0].sum()),
        "true_flux_total": float(sum(c["flux"] for c in comps)),
    }
    out["total_flux_error"] = out["model_flux_total"] - out["true_flux_total"]
    if not comps:
        return out
    pos = np.array([[c["x"], c["y"]] for c in comps])
    tree = cKDTree(pos)
    if vals.size:
        d, idx = tree.query(np.column_stack([xx, yy]))
    else:
        d, idx = np.zeros(0), np.zeros(0, int)
    disc = [i for i, c in enumerate(comps) if c["kind"] == "gaussian"]
    # A disc's pixels: within 2 FWHM of its centre; they are not "false".
    in_disc = np.zeros(vals.size, bool)
    for i in disc:
        r = 2.0 * comps[i]["fwhm_arcsec"] / cat["image"]["scale_arcsec"]
        in_disc |= (xx - pos[i, 0]) ** 2 + (yy - pos[i, 1]) ** 2 <= r * r
    near = (d <= beam_px) & ~in_disc
    false = (d > 2 * beam_px) & ~in_disc
    rec = np.zeros(len(comps))
    np.add.at(rec, idx[near], vals[near])
    points = [i for i, c in enumerate(comps) if c["kind"] == "point"]
    ratios = {i: rec[i] / comps[i]["flux"] for i in points}
    decades = {}
    for i in points:
        f = comps[i]["flux"]
        lo = 10 ** math.floor(math.log10(f) + 1e-12)
        decades.setdefault(f"{lo:g}-{10 * lo:g} Jy", []).append(ratios[i])
    out["recovery_by_decade"] = {
        k: {
            "n": len(v),
            "mean": float(np.mean(v)),
            "std": float(np.std(v)),
            "min": float(np.min(v)),
        }
        for k, v in sorted(decades.items())
    }
    if points:
        allr = np.array(list(ratios.values()))
        out["recovery_all"] = {
            "n": len(allr),
            "mean": float(allr.mean()),
            "std": float(allr.std()),
            "flux_weighted": float(
                sum(rec[i] for i in points) / sum(comps[i]["flux"] for i in points)
            ),
        }
    out["false_pixels"] = int(false.sum())
    out["false_flux_positive"] = float(vals[false & (vals > 0)].sum())
    out["false_flux_negative"] = float(vals[false & (vals < 0)].sum())
    out["false_flux_abs"] = float(np.abs(vals[false]).sum())
    out["between_1_and_2_beams_flux"] = float(
        vals[(d > beam_px) & (d <= 2 * beam_px) & ~in_disc].sum()
    )
    for i in disc:
        c = comps[i]
        sel = in_disc
        w = vals[sel]
        x, y = xx[sel], yy[sel]
        flux = float(w.sum())
        rec_d = {"true_flux": c["flux"], "flux": flux, "pixels": int(sel.sum())}
        if flux > 0:
            cx, cy = float((w * x).sum() / flux), float((w * y).sum() / flux)
            cxx = float((w * (x - cx) ** 2).sum() / flux)
            cyy = float((w * (y - cy) ** 2).sum() / flux)
            cxy = float((w * (x - cx) * (y - cy)).sum() / flux)
            ev = np.linalg.eigvalsh([[cxx, cxy], [cxy, cyy]])
            k = 2 * math.sqrt(2 * math.log(2)) * cat["image"]["scale_arcsec"]
            rec_d.update(
                flux_error=flux - c["flux"],
                centroid_offset_px=math.hypot(cx - c["x"], cy - c["y"]),
                fwhm_major_arcsec=k * math.sqrt(max(ev[1], 0)),
                fwhm_minor_arcsec=k * math.sqrt(max(ev[0], 0)),
                true_fwhm_arcsec=c["fwhm_arcsec"],
            )
        out["disc"] = rec_d
    return out


def score_job(exact, cat, run, name, beam_px, noise_rms):
    model, _ = read_fits(run / f"{name}-model.fits")
    residual, _ = read_fits(run / f"{name}-residual.fits")
    ib = inner_box(exact.size)
    rec = {"name": name}
    rec["residual_inner_rms"] = float(np.sqrt(np.mean(residual[ib] ** 2)))
    rec["residual_inner_peak_abs"] = float(np.abs(residual[ib]).max())
    rec["residual_rms"] = float(np.sqrt(np.mean(residual**2)))
    image_path = run / f"{name}-image.fits"
    if image_path.exists():
        image, h = read_fits(image_path)
        rec["restored_peak"] = float(image.max())
        rec["restoring_beam_arcsec"] = [
            float(h.get("BMAJ", float("nan"))) * 3600,
            float(h.get("BMIN", float("nan"))) * 3600,
        ]
        rec["dynamic_range"] = rec["restored_peak"] / rec["residual_inner_rms"]
    if noise_rms:
        rec["residual_inner_rms_over_noise"] = rec["residual_inner_rms"] / noise_rms
    rec.update(flux_metrics(model, cat, beam_px))
    if cat.get("calibrator_flux_jy"):
        h = exact.size // 2
        box = model[h - 32 : h + 33, h - 32 : h + 33]
        rec["calibrator_flux"] = float(box.sum())
        rec["calibrator_flux_error_relative"] = (
            rec["calibrator_flux"] / cat["calibrator_flux_jy"] - 1.0
        )
    s = time.perf_counter()
    q, er = exact.score(model)
    rec["q"] = q
    rec["q_over_q0"] = q / exact.meta["q0"]
    if exact.meta.get("noise"):
        rec["q_over_q_truth"] = q / exact.meta["noise"]["q_truth"]
    rec["exact_residual_inner_rms"] = float(np.sqrt(np.mean(er[ib] ** 2)))
    rec["exact_residual_inner_peak_abs"] = float(np.abs(er[ib]).max())
    rec["exact_vs_imager_residual_inner_linf"] = float(
        np.abs(er[ib] - residual[ib]).max()
    )
    rec["score_seconds"] = time.perf_counter() - s
    rec["log"] = wsclean_log(run / f"{name}.log")
    rec["time"] = time_v(run / "timing" / f"{name}.txt")
    load = run / "load" / f"{name}.txt"
    if load.exists():
        rec["loadavg_before_after"] = [
            line.split()[:3] for line in load.read_text(encoding="utf-8").splitlines()
        ]
    samples = run / "load" / f"{name}.samples.txt"
    if samples.exists():
        one = [
            float(line.split()[0])
            for line in samples.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        rec["loadavg1_samples_max"] = max(one) if one else None
    busy = run / "load" / f"{name}.busy.txt"
    if busy.exists():
        rec["busy_processes"] = busy.read_text(encoding="utf-8").splitlines()
    cmd = run / f"{name}.cmd"
    if cmd.exists():
        rec["command"] = cmd.read_text(encoding="utf-8").strip()
    report = run / f"{name}-report.json"
    if report.exists():
        rec["report"] = _read_json(report)
    for kind in ("model", "residual"):
        rec[f"{kind}_fits_sha256"] = _sha(run / f"{name}-{kind}.fits")
    return rec


def score(args):
    prep, run = Path(args.prep), Path(args.run)
    exact = Exact(prep)
    cat = catalogue(args.catalogue)
    cmp = exact.meta.get("comparisons", {})
    # One beam: the geometric-mean FWHM of WSClean's fitted PSF without the
    # minimum-grid-resolution upsampling (the exact-transform PSF).
    fits_beam = [
        math.sqrt(c["psf_bmaj_arcsec"] * c["psf_bmin_arcsec"])
        for k, c in sorted(cmp.items())
        if "nominres" in k and c.get("psf_bmaj_arcsec")
    ]
    beam_arcsec = args.beam_arcsec or (fits_beam[0] if fits_beam else None)
    if not beam_arcsec:
        raise SystemExit("no beam: give --beam-arcsec or prepare with --wsclean-dirty")
    beam_px = beam_arcsec / exact.meta["scale_arcsec"]
    noise_rms = (exact.meta.get("noise") or {}).get("briggs_image_rms")
    jobs = args.jobs or sorted(
        p.name[: -len("-model.fits")] for p in run.glob("*-model.fits")
    )
    out = Path(args.out_json)
    result = _read_json(out) if out.exists() else {}
    result.update(
        {
            "prep": str(prep.resolve()),
            "run": str(run.resolve()),
            "q0": exact.meta["q0"],
            "q_truth": (exact.meta.get("noise") or {}).get("q_truth"),
            "briggs_noise": noise_rms,
            "beam_arcsec": beam_arcsec,
            "timing_status": args.timing_status,
        }
    )
    result.setdefault("jobs", {})
    for name in jobs:
        if name in result["jobs"] and not args.force:
            continue
        rec = score_job(exact, cat, run, name, beam_px, noise_rms)
        result["jobs"][name] = rec
        _write_json(out, result)
        print(
            f"{name}: Q/Q0 {rec['q_over_q0']:.4e} rms {rec['residual_inner_rms']:.3e} "
            f"peak {rec['residual_inner_peak_abs']:.3e} flux {rec['model_flux_total']:.4f} "
            f"({rec['score_seconds']:.1f} s)",
            flush=True,
        )
    _write_json(out, result)


# -- truth ---------------------------------------------------------------------


def truth_image(cat, size):
    """The catalogue on the image grid: points at their nearest pixel, a disc
    as its sampled Gaussian with the catalogue flux."""
    image = np.zeros((size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for c in cat["components"]:
        if c["kind"] == "point":
            image[round(c["y"]), round(c["x"])] += c["flux"]
        else:
            fwhm = c["fwhm_arcsec"] / cat["image"]["scale_arcsec"]
            sig2 = (fwhm / (2 * math.sqrt(2 * math.log(2)))) ** 2
            g = np.exp(-((xx - c["x"]) ** 2 + (yy - c["y"]) ** 2) / (2 * sig2))
            image += c["flux"] * g / g.sum()
    return image


def truth(args):
    """Writes NAME-{model,residual}.fits of the pixelised catalogue: a check of
    the metrics (recovery 1, no false flux) and the misfit of the on-grid sky."""
    from astropy.io import fits

    exact = Exact(Path(args.prep))
    model = truth_image(catalogue(args.catalogue), exact.size)
    _, residual = exact.score(model)
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    fits.writeto(run / f"{args.name}-model.fits", model, overwrite=True)
    fits.writeto(run / f"{args.name}-residual.fits", residual, overwrite=True)


# -- tables -------------------------------------------------------------------


def _f(v, fmt):
    return "–" if v is None else format(v, fmt)


def tables(args):
    for path in args.json:
        res = _read_json(path)
        print(
            f"\n#### {Path(path).name} (Q0 {res['q0']:.4g} Jy², beam {res['beam_arcsec']:.2f}″)\n"
        )
        if res.get("q_truth"):
            print(
                f"Q_truth/Q0 = {res['q_truth'] / res['q0']:.4e}; "
                f"Briggs image noise {res['briggs_noise'] * 1e6:.2f} µJy\n"
            )
        print(
            "Wall and CPU times are PROVISIONAL (contended host) unless "
            "this table says it comes from the quiet-window rerun. DR is restored "
            "peak over residual rms at each imager's own restoring beam: compare "
            "beams before comparing DR.\n"
        )
        print(
            "| job | wall s | CPU s | RSS GB | majors | comps | inner rms | inner peak "
            "| DR | Q/Q0 | Q/Q_truth | flux err | recovery (flux-wt) | false \\|flux\\| |"
        )
        print("| --- | " + "---: | " * 13)
        for name, r in sorted(res["jobs"].items()):
            t, lg = r.get("time", {}), r.get("log", {})
            rep = (r.get("report") or {}).get("run") or {}
            majors = lg.get("major_iterations") or rep.get("major_cycles")
            comps = lg.get("components")
            if comps is None:
                comps = rep.get("components")
            comps_text = _f(comps, "d")
            if comps is None and lg.get("last_logged_iteration"):
                # The plain minor loop logs every 10th or 100th iteration.
                comps_text = f"≥ {lg['last_logged_iteration']}"
            rss = t.get("max_rss_kb")
            print(
                f"| {name} | {_f(t.get('wall_s'), '.1f')} | {_f(t.get('cpu_s'), '.1f')} "
                f"| {_f(rss and rss / 1048576, '.2f')} | {_f(majors, 'd')} "
                f"| {comps_text} | {r['residual_inner_rms']:.3e} "
                f"| {r['residual_inner_peak_abs']:.3e} | {_f(r.get('dynamic_range'), '.0f')} "
                f"| {r['q_over_q0']:.4e} | {_f(r.get('q_over_q_truth'), '.4f')} "
                f"| {r['total_flux_error']:+.4f} "
                f"| {_f((r.get('recovery_all') or {}).get('flux_weighted'), '.4f')} "
                f"| {_f(r.get('false_flux_abs'), '.4f')} |"
            )
        decs = sorted(
            {k for r in res["jobs"].values() for k in r.get("recovery_by_decade", {})}
        )
        if decs:
            print(
                "\nPer-source recovery (model flux within one beam / true flux), mean ± std:\n"
            )
            print("| job | " + " | ".join(decs) + " |")
            print("| --- | " + "---: | " * len(decs))
            for name, r in sorted(res["jobs"].items()):
                cells = []
                for k in decs:
                    d = r.get("recovery_by_decade", {}).get(k)
                    cells.append(
                        f"{d['mean']:.3f} ± {d['std']:.3f} (n={d['n']})" if d else "–"
                    )
                print(f"| {name} | " + " | ".join(cells) + " |")
        discs = {n: r["disc"] for n, r in res["jobs"].items() if r.get("disc")}
        if discs:
            print(
                "\n| job | disc flux | error | centroid offset px | FWHM maj × min ″ |"
            )
            print("| --- | ---: | ---: | ---: | --- |")
            for name, d in sorted(discs.items()):
                print(
                    f"| {name} | {d['flux']:.4f} | {_f(d.get('flux_error'), '+.4f')} "
                    f"| {_f(d.get('centroid_offset_px'), '.2f')} "
                    f"| {_f(d.get('fwhm_major_arcsec'), '.1f')} × {_f(d.get('fwhm_minor_arcsec'), '.1f')} |"
                )
        cals = {n: r for n, r in res["jobs"].items() if "calibrator_flux" in r}
        if cals:
            print("\n| job | calibrator flux (central 65 px) | vs catalogue |")
            print("| --- | ---: | ---: |")
            for name, r in sorted(cals.items()):
                print(
                    f"| {name} | {r['calibrator_flux']:.4f} | {r['calibrator_flux_error_relative']:+.4%} |"
                )
        reps = {
            n: r["report"]
            for n, r in res["jobs"].items()
            if (r.get("report") or {}).get("run")
        }
        if reps:
            print(
                "\n| job (gmclean report.json) | major | resyncs | max \\|gap\\|/Q "
                "| ascending majors | τ min | τ median | minor s | resync s | major s | stop |"
            )
            print("| --- | " + "---: | " * 9 + "--- |")
            for name, rep in sorted(reps.items()):
                run = rep["run"]
                tau = run.get("tau") or {}
                sec = run.get("seconds") or {}
                total = (run.get("resyncs") or {}).get("total")
                print(
                    f"| {name} | {run.get('major_cycles')} | {total} "
                    f"| {_f(run.get('max_abs_gap_relative'), '.2e')} "
                    f"| {run.get('ascending_major_cycles')} | {_f(tau.get('min'), '.3f')} "
                    f"| {_f(tau.get('median'), '.3f')} | {_f(sec.get('minor'), '.1f')} "
                    f"| {_f(sec.get('resync'), '.1f')} | {_f(sec.get('major'), '.1f')} "
                    f"| {run.get('stop')} |"
                )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("ms")
    a.add_argument("catalogue")
    a.add_argument("out_dir")
    a.add_argument("--size", type=int, required=True)
    a.add_argument("--scale", type=float, required=True)
    a.add_argument("--datacol", default="DATA")
    a.add_argument("--field", type=int, default=0)
    a.add_argument("--epsilon", type=float, default=1e-9)
    a.add_argument("--noise")
    a.add_argument("--wsclean-dirty", action="append", default=[], metavar="PREFIX")
    b = sub.add_parser("score")
    b.add_argument("prep")
    b.add_argument("catalogue")
    b.add_argument("run")
    b.add_argument("out_json")
    b.add_argument("--jobs", nargs="*")
    b.add_argument("--beam-arcsec", type=float)
    b.add_argument("--force", action="store_true")
    b.add_argument(
        "--timing-status",
        default="PROVISIONAL (contended): shared host, not for speed comparisons",
    )
    t = sub.add_parser("truth")
    t.add_argument("prep")
    t.add_argument("catalogue")
    t.add_argument("run")
    t.add_argument("--name", default="truth")
    c = sub.add_parser("tables")
    c.add_argument("json", nargs="+")
    args = p.parse_args(argv)
    {"prepare": prepare, "score": score, "truth": truth, "tables": tables}[args.cmd](
        args
    )


if __name__ == "__main__":
    main()
