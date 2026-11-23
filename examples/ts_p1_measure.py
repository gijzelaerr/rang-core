"""Task TS-P1: score a light-curve run against its oracles (research/ts-p1.md,
section 5).

Usage (worktree venv):
    python examples/ts_p1_measure.py MS TRUTH_JSON LC_DIR OUT_JSON [--wsclean DIR]

LC_DIR is a `rang-core lightcurve` output run with `--fits` at the
simulation's positions (in the truth's role order). The script computes,
independently of the Rust kernel, in float64 NumPy:

- the DFT flux at each position from the MS's residual (DATA - MODEL_DATA,
  complex64 as the product forms it), with Stokes I and its weight formed
  here from the correlations (T2a);
- the expected dirty value at each position from the injected list:
  sum_Y S_Y(t) B_t(X, Y), B_t(X, Y) = sum w cos(phi_Y - phi_X) / sum w (T3);

and compares the snapshot pixels with the DFT (T2b) and, with `--wsclean`,
WSClean's `-intervals-out` images with rang's snapshots (T1) and WSClean's
pixel at each RA/Dec with the DFT (T2c). Writes OUT_JSON with every measure
and the verdict of each gate under the frozen bounds.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms

C = 299_792_458.0
T1_BOUND = 1e-5
T2_BOUND = 1e-3
T3A_BOUND = 0.1
T3B_RANGE = (0.8, 1.2)
T3D_SNR = 4.0
TWIN_BOUND = 0.01  # amendment 9.2, the noiseless twin's |bias| in sigma_snap


def stokes_i(data, weights, flags):
    """WSClean's -pol I from (row, chan, 4) correlations, in NumPy."""
    xx, yy = data[..., 0], data[..., 3]
    vis = (0.5 * (xx.astype(np.complex128) + yy.astype(np.complex128))).astype(
        np.complex64
    )
    wx = np.where(flags[..., 0], 0.0, 4.0 * weights[..., 0])
    wy = np.where(flags[..., 3], 0.0, 4.0 * weights[..., 3])
    return vis, np.minimum(wx, wy).astype(np.float32)


def phases(uvw, freq, lm):
    """(nsrc, row, chan) phi = 2 pi nu / c (u l + v m + w (n - 1))."""
    out = []
    for el, em in lm:
        n1 = math.sqrt(1.0 - el * el - em * em) - 1.0
        b = uvw[:, 0] * el + uvw[:, 1] * em + uvw[:, 2] * n1
        out.append(2 * math.pi / C * b[:, None] * freq[None, :])
    return np.array(out)


def numpy_dft(vis, weight, phi):
    """Flux per position: sum w Re[I exp(-i phi)] / sum w, float64."""
    w = weight.astype(np.float64)
    re, im = vis.real.astype(np.float64), vis.imag.astype(np.float64)
    num = [np.sum(w * (re * np.cos(p) + im * np.sin(p))) for p in phi]
    return np.array(num) / np.sum(w)


def beams(weight, phi):
    """(nsrc, nsrc) B(X, Y) = sum w cos(phi_Y - phi_X) / sum w."""
    w = weight.astype(np.float64)
    wsum = np.sum(w)
    n = len(phi)
    out = np.eye(n)
    for x in range(n):
        for y in range(x + 1, n):
            out[x, y] = out[y, x] = np.sum(w * np.cos(phi[y] - phi[x])) / wsum
    return out


def read_interval(t, rows):
    """The residual of `rows` as the product should read it, formed here:
    CORRECTED_DATA (else DATA) - MODEL_DATA, WEIGHT_SPECTRUM (else WEIGHT),
    FLAG and FLAG_ROW (protocol 2, research/ts-p1.md 13.1)."""
    names = t.colnames()
    column = "CORRECTED_DATA" if "CORRECTED_DATA" in names else "DATA"
    data = t.getcol_rows(column, rows) - t.getcol_rows("MODEL_DATA", rows)
    if "WEIGHT_SPECTRUM" in names:
        wt = t.getcol_rows("WEIGHT_SPECTRUM", rows)
    else:
        wt = np.broadcast_to(t.getcol_rows("WEIGHT", rows)[:, None, :], data.shape)
    flags = t.getcol_rows("FLAG", rows)
    vis, weight = stokes_i(data, wt, flags)
    weight[t.getcol_rows("FLAG_ROW", rows).astype(bool)] = 0.0
    return np.asarray(t.getcol_rows("UVW", rows), np.float64), vis, weight


def oracle(ms, truth):
    """Per interval: NumPy DFT fluxes and expected dirty values (T2a, T3)."""
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as sw:
        freq = np.asarray(sw.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
    lm = [(s["l"], s["m"]) for s in truth["sources"]]
    injected = np.array(truth["flux_jy"])
    dft, expected = [], []
    with core_ms.open_table(ms) as t:
        times = t.getcol("TIME")
        keep = (t.getcol("FIELD_ID") == truth["field_id"]) & (
            t.getcol("ANTENNA1") != t.getcol("ANTENNA2")
        )
        for k, when in enumerate(truth["time_mjd_s"]):
            rows = np.flatnonzero(keep & (times == when))
            uvw, vis, weight = read_interval(t, rows)
            phi = phases(uvw, freq, lm)
            dft.append(numpy_dft(vis, weight, phi))
            expected.append(beams(weight, phi) @ injected[k])
    return np.array(dft), np.array(expected)


def wsclean_images(directory, n):
    from astropy.io import fits

    paths = [Path(directory) / f"w-t{k:04d}-dirty.fits" for k in range(n)]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"WSClean images missing: {missing[:3]} ...")
    for p in paths:
        with fits.open(p) as h:
            yield np.asarray(h[0].data[0, 0], np.float64), h[0].header.copy()


def score(ms, truth_path, lc_dir, wsclean=None, flag_row_ignored=False):
    started = time.perf_counter()
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    lc = json.loads((Path(lc_dir) / "lightcurve.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in truth["sources"]]
    if [p["name"] for p in lc["positions"]] != names:
        raise SystemExit("light curve positions are not the truth's, in order")
    n = len(truth["time_mjd_s"])
    sig = truth["sigma_snap_jy"]
    # Protocol 2: sigma_snap per interval (13.1); else the design value.
    per_k = truth.get("sigma_snap_interval_jy")
    sig_k = np.array(per_k if per_k else [sig] * n, np.float64)[:, None]
    flux = np.array(lc["flux_jy"], np.float64)
    snap = np.array(lc["flux_snapshot_jy"], np.float64)
    sigma_meas = np.array(lc["sigma_meas_jy"], np.float64)
    injected = np.array(truth["flux_jy"])
    dft, expected = oracle(ms, truth)
    res = {"case": truth["case"], "sigma_snap_jy": sig, "intervals": n}
    res["sigma_meas_jy"] = {
        "median": float(np.median(sigma_meas)),
        "min": float(sigma_meas.min()),
        "max": float(sigma_meas.max()),
        "median_over_sigma_snap": float(np.median(sigma_meas) / sig),
    }
    d2a = np.abs(flux - dft) / sig_k
    d2b = np.abs(snap - flux) / sig_k
    res["T2a"] = {
        "max_over_sigma": float(d2a.max()),
        "pass": bool(d2a.max() <= T2_BOUND),
    }
    res["T2b"] = {
        "max_over_sigma": float(d2b.max()),
        "pass": bool(d2b.max() <= T2_BOUND),
    }
    z = (flux - expected) / sig_k
    per = {}
    for s, name in enumerate(names):
        alone = np.all(np.delete(injected, s, axis=1) == 0.0, axis=1) & (
            injected[:, s] > 0
        )
        per[name] = {
            "bias_over_sigma": float(z[:, s].mean()),
            "chi2_reduced": float(np.mean(z[:, s] ** 2)),
            "bias_vs_injected_alone_over_sigma": float(
                np.mean((flux[alone, s] - injected[alone, s]) / sig)
            )
            if alone.any()
            else None,
            "intervals_alone": int(alone.sum()),
        }
    worst = max(abs(v["bias_over_sigma"]) for v in per.values())
    res["T3a"] = {
        "per_source": {k: v["bias_over_sigma"] for k, v in per.items()},
        "max_abs": worst,
        "pass": bool(worst <= T3A_BOUND),
        # Amendment 9.2 (post hoc): three standard errors of an n-point mean.
        "amended_bound": 3.0 / math.sqrt(n),
        "pass_amended": bool(worst <= 3.0 / math.sqrt(n)),
        # Amendment 9.2: the noiseless twin's bound (its fluxes equal the
        # expected dirty values up to complex64 rounding).
        "twin_bound": TWIN_BOUND,
        "pass_twin": bool(worst <= TWIN_BOUND),
    }
    res["T3b"] = {
        "per_source": {k: v["chi2_reduced"] for k, v in per.items()},
        "pass": all(
            T3B_RANGE[0] <= v["chi2_reduced"] <= T3B_RANGE[1] for v in per.values()
        ),
    }
    res["sources"] = per
    res["T3c"] = {
        "pass": bool(
            np.array_equal(np.array(lc["time_mjd_s"]), np.array(truth["time_mjd_s"]))
        )
    }
    res["T3d"] = recovery(truth, flux, sigma_meas, sig)
    if wsclean:
        res.update(compare_wsclean(wsclean, ms, lc_dir, lc, flux, sig_k[:, 0], n))
        if flag_row_ignored:
            res.update(
                compare_wsclean_flag_row_ignored(wsclean, ms, lc, sig_k[:, 0], n)
            )
    gates = ["T2a", "T2b", "T3a", "T3b", "T3c", "T3d"] + (
        ["T1", "T2c"] if wsclean else []
    )
    res["gates"] = {g: res[g]["pass"] for g in gates}
    res["all_pass"] = all(res["gates"].values())
    res["seconds"] = time.perf_counter() - started
    return res


def recovery(truth, flux, sigma_meas, sig):
    """T3d: each pulse with peak truth >= 7 sigma_snap."""
    names = [s["name"] for s in truth["sources"]]
    injected = np.array(truth["flux_jy"])
    pulses = []
    for s, name in enumerate(names):
        spec = truth["layout"][name]
        spans = [(a, a + k) for a, k, _ in spec.get("pulses", [])]
        if "periodic" in spec:
            on = np.flatnonzero(injected[:, s] > 0)
            if on.size:
                breaks = np.flatnonzero(np.diff(on) > 1)
                for chunk in np.split(on, breaks + 1):
                    spans.append((int(chunk[0]), int(chunk[-1]) + 1))
        for a, b in spans:
            peak = float(injected[a:b, s].max())
            if peak < 7 * sig:
                continue
            bright = [i for i in range(a, b) if injected[i, s] >= 7 * sig]
            snr = [float(flux[i, s] / sigma_meas[i]) for i in bright]
            lo, hi = max(0, a - 3), min(len(flux), b + 3)
            best = lo + int(np.argmax(flux[lo:hi, s]))
            ok = all(x >= T3D_SNR for x in snr) and injected[best, s] >= 0.5 * peak
            pulses.append(
                {
                    "source": name,
                    "start": a,
                    "end": b,
                    "peak_over_sigma": peak / sig,
                    "snr_meas": snr,
                    "best_interval": best,
                    "pass": bool(ok),
                }
            )
    return {"pulses": pulses, "pass": all(p["pass"] for p in pulses)}


def rang_snapshots(ms, lc_dir, lc):
    """rang's snapshot images in interval order: the run's FITS files when it
    wrote them (`--fits`), else made again in stream by the product's own
    `light_curves` with the run's settings (amendment 9.1: no FITS on disk);
    the second form also checks that the fluxes repeat bit for bit."""
    from astropy.io import fits

    snapshots = Path(lc_dir) / "snapshots"
    if snapshots.is_dir():
        for k in range(lc["intervals"]):
            path = snapshots / f"snapshot-t{k:04d}-dirty.fits"
            with fits.open(path) as h:
                yield np.asarray(h[0].data[0, 0], np.float64)
        return
    import queue
    import threading

    from rang import lightcurve

    s = lc["settings"]
    images = queue.Queue(maxsize=2)
    rerun = {}

    def run():
        try:
            rerun["result"] = lightcurve.light_curves(
                ms,
                [(p["name"], p["ra_deg"], p["dec_deg"]) for p in lc["positions"]],
                field=lc["field"]["id"],
                column=s["column"],
                model_column=s["model_column"],
                interval_steps=s["interval_steps"],
                size=s["size"],
                scale_arcsec=s["scale_arcsec"],
                epsilon=s["epsilon"],
                gridder=s.get("gridder", "wgrid"),
                device=s.get("device", "cpu"),
                weights=s.get("weights", "ms"),
                on_snapshot=lambda k, image, header: images.put(image),
            )
        finally:
            images.put(None)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while (image := images.get()) is not None:
        yield image
    worker.join()
    if rerun.get("result", {}).get("flux_jy") != lc["flux_jy"]:
        raise SystemExit("the in-stream rerun's fluxes differ from the run's")


def compare_wsclean(directory, ms, lc_dir, lc, flux, sig, n):
    from astropy.wcs import WCS

    t1, t2c, pix_ok = [], [], []
    ours_all = rang_snapshots(ms, lc_dir, lc)
    for k, (image, header) in enumerate(wsclean_images(directory, n)):
        ours = next(ours_all)
        t1.append(float(np.max(np.abs(ours - image)) / np.max(np.abs(image))))
        wcs = WCS(header).celestial
        row = []
        for s, pos in enumerate(lc["positions"]):
            x, y = wcs.world_to_pixel_values(pos["ra_deg"], pos["dec_deg"])
            x, y = round(float(x)), round(float(y))
            if k == 0:
                pix_ok.append(list(pos["pixel"] or []) == [x, y])
            row.append(abs(image[y, x] - flux[k, s]) / sig[k])
        t2c.append(row)
    for _ in ours_all:  # drain: runs the rerun's flux check
        pass
    t1, t2c = np.array(t1), np.array(t2c)
    return {
        "T1": {
            "max_relative": float(t1.max()),
            "median_relative": float(np.median(t1)),
            "worst_interval": int(np.argmax(t1)),
            "pass": bool(t1.max() <= T1_BOUND),
        },
        "T2c": {
            "max_over_sigma": float(t2c.max()),
            "pixels_equal_rang": pix_ok,
            "pass": bool(t2c.max() <= T2_BOUND),
        },
    }


def flag_row_ignored_stream(ms, lc):
    """Per interval, rang's snapshot and DFT fluxes with FLAG_ROW ignored
    (cells still flagged by FLAG): WSClean 3.7's reading of an MS, the known
    oracle difference of research/ts-p1.md 14.1 and 15.3. The product's own
    snapshot and DFT functions; only the FLAG_ROW step is left out."""
    from rang import core_model, core_weights
    from rang import lightcurve as lcm

    s = lc["settings"]
    field = lc["field"]["id"]
    rows = core_model.selected_rows(ms, field)
    freq, _, _ = core_model.band(ms, field)
    lm = np.array([[p["l"], p["m"]] for p in lc["positions"]])
    with core_ms.open_table(ms) as t:
        times = t.getcol_rows("TIME", rows)
        for when in np.unique(times):
            sel = np.sort(rows[times == when])
            data = t.getcol_rows(s["column"], sel)
            if s["model_column"]:
                data = data - t.getcol_rows(s["model_column"], sel)
            if s.get("weights") == "unit":  # research/ts-p3.md 1a
                wt = np.ones(data.shape, np.float32)
            elif s["weight_column"] == "WEIGHT_SPECTRUM":
                wt = t.getcol_rows("WEIGHT_SPECTRUM", sel)
            else:
                wt = np.broadcast_to(
                    t.getcol_rows("WEIGHT", sel)[:, None, :], data.shape
                )
            vis, w = core_weights.stokes_i(data, wt, t.getcol_rows("FLAG", sel))
            uvw = np.ascontiguousarray(t.getcol_rows("UVW", sel), np.float64)
            image = lcm.snapshot(uvw, freq, vis, w, s["size"], s["scale_arcsec"],
                                 s["epsilon"])  # fmt: skip
            flux, _, _ = lcm.dft(uvw, freq, vis, w, lm)
            yield image, flux


def compare_wsclean_flag_row_ignored(directory, ms, lc, sig, n):
    """T1 and T2c against rang with FLAG_ROW ignored (15.3), reported beside
    the raw verdict."""
    from astropy.wcs import WCS

    t1, t2c = [], []
    ours_all = flag_row_ignored_stream(ms, lc)
    for k, (image, header) in enumerate(wsclean_images(directory, n)):
        ours, flux = next(ours_all)
        t1.append(float(np.max(np.abs(ours - image)) / np.max(np.abs(image))))
        wcs = WCS(header).celestial
        row = []
        for s, pos in enumerate(lc["positions"]):
            x, y = wcs.world_to_pixel_values(pos["ra_deg"], pos["dec_deg"])
            x, y = round(float(x)), round(float(y))
            row.append(abs(image[y, x] - flux[s]) / sig[k])
        t2c.append(row)
    t1, t2c = np.array(t1), np.array(t2c)
    return {
        "T1_flag_row_ignored": {
            "max_relative": float(t1.max()),
            "median_relative": float(np.median(t1)),
            "pass": bool(t1.max() <= T1_BOUND),
        },
        "T2c_flag_row_ignored": {
            "max_over_sigma": float(t2c.max()),
            "pass": bool(t2c.max() <= T2_BOUND),
        },
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument("truth")
    p.add_argument("lc_dir")
    p.add_argument("out")
    p.add_argument("--wsclean", help="directory of WSClean's w-tNNNN-dirty.fits")
    p.add_argument(
        "--flag-row-ignored",
        action="store_true",
        help="also report T1/T2c against rang with FLAG_ROW ignored (15.3)",
    )
    a = p.parse_args(argv)
    res = score(a.ms, a.truth, a.lc_dir, a.wsclean, a.flag_row_ignored)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": res["gates"], "all_pass": res["all_pass"]}))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
