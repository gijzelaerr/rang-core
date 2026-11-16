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
    data = t.getcol_rows("DATA", rows) - t.getcol_rows("MODEL_DATA", rows)
    wt = t.getcol_rows("WEIGHT", rows)
    flags = t.getcol_rows("FLAG", rows)
    vis, weight = stokes_i(data, np.broadcast_to(wt[:, None, :], data.shape), flags)
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


def score(ms, truth_path, lc_dir, wsclean=None):
    started = time.perf_counter()
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    lc = json.loads((Path(lc_dir) / "lightcurve.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in truth["sources"]]
    if [p["name"] for p in lc["positions"]] != names:
        raise SystemExit("light curve positions are not the truth's, in order")
    n = len(truth["time_mjd_s"])
    sig = truth["sigma_snap_jy"]
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
    d2a = np.abs(flux - dft) / sig
    d2b = np.abs(snap - flux) / sig
    res["T2a"] = {
        "max_over_sigma": float(d2a.max()),
        "pass": bool(d2a.max() <= T2_BOUND),
    }
    res["T2b"] = {
        "max_over_sigma": float(d2b.max()),
        "pass": bool(d2b.max() <= T2_BOUND),
    }
    z = (flux - expected) / sig
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
    res["T3a"] = {
        "per_source": {k: v["bias_over_sigma"] for k, v in per.items()},
        "pass": all(abs(v["bias_over_sigma"]) <= T3A_BOUND for v in per.values()),
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
        res.update(compare_wsclean(wsclean, lc_dir, lc, flux, sig, n))
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


def compare_wsclean(directory, lc_dir, lc, flux, sig, n):
    from astropy.io import fits
    from astropy.wcs import WCS

    t1, t2c, pix_ok = [], [], []
    for k, (image, header) in enumerate(wsclean_images(directory, n)):
        mine = Path(lc_dir) / "snapshots" / f"snapshot-t{k:04d}-dirty.fits"
        with fits.open(mine) as h:
            ours = np.asarray(h[0].data[0, 0], np.float64)
        t1.append(float(np.max(np.abs(ours - image)) / np.max(np.abs(image))))
        wcs = WCS(header).celestial
        row = []
        for s, pos in enumerate(lc["positions"]):
            x, y = wcs.world_to_pixel_values(pos["ra_deg"], pos["dec_deg"])
            x, y = round(float(x)), round(float(y))
            if k == 0:
                pix_ok.append(list(pos["pixel"] or []) == [x, y])
            row.append(abs(image[y, x] - flux[k, s]) / sig)
        t2c.append(row)
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument("truth")
    p.add_argument("lc_dir")
    p.add_argument("out")
    p.add_argument("--wsclean", help="directory of WSClean's w-tNNNN-dirty.fits")
    a = p.parse_args(argv)
    res = score(a.ms, a.truth, a.lc_dir, a.wsclean)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": res["gates"], "all_pass": res["all_pass"]}))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
