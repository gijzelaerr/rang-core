"""Task TS-P2: score a dynamic-spectrum run against its oracles
(research/ts-p2.md, sections 3 and 5).

Usage (worktree venv):
    python examples/ts_p2_measure.py MS TRUTH_JSON LC_DIR OUT_JSON
        [--wsclean DIR] [--real --control LC_DIR_UNINJECTED]

LC_DIR is a `rang-core lightcurve --channels-out M` output at the truth's
positions (in the truth's role order). Independently of the Rust kernel, in
float64 NumPy, from the MS's residual formed here (the product's settings'
column minus its model column, WEIGHT_SPECTRUM, FLAG, FLAG_ROW, Stokes I as
WSClean's -pol I):

- the DFT flux per interval, group and position (D1), and over the band (T2a);
- the expected dirty value per cell from the truth (amplitude a_Y(t) times
  spectrum f_Y(nu)): sum_Y sum_c w_c a_Y f_Y(c) cos(phi_Y - phi_X) / sum_c w_c
  over the group's channels (D3), and over the band (T3a);
- D4 (the group-weighted mean against the product's light curve) and D5
  (empty groups NaN in CSV and null in JSON);
- with `--wsclean`, WSClean's w-tNNNN-GGGG-dirty.fits pixel at each RA/Dec
  against the DFT (D2) and the grouping check (CRVAL3 against the group's
  mean frequency).

σ per cell: the truth's `sigma_cell_jy` on simulations; with `--real`,
σ_dyn,g = 1.4826 MAD over the intervals of the control F's group-g flux in
the uninjected run (`--control`), and for P1's gates the run's σ_meas.
"""

import argparse
import csv
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms

_spec = importlib.util.spec_from_file_location(
    "ts_p1_measure", Path(__file__).with_name("ts_p1_measure.py")
)
p1m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p1m)

C = 299_792_458.0
D_BOUND = 1e-3
D4_BOUND = 1e-6
MAD = 1.482602218505602


def read_residual(t, rows, settings):
    """The residual as the run's settings name it, formed here."""
    names = t.colnames()
    data = t.getcol_rows(settings["column"], rows)
    if settings.get("model_column"):
        data = data - t.getcol_rows(settings["model_column"], rows)
    if settings.get("weights") == "unit":  # research/ts-p3.md 1a
        wt = np.ones(data.shape, np.float32)
    elif "WEIGHT_SPECTRUM" in names:
        wt = t.getcol_rows("WEIGHT_SPECTRUM", rows)
    else:
        wt = np.broadcast_to(t.getcol_rows("WEIGHT", rows)[:, None, :], data.shape)
    vis, weight = p1m.stokes_i(data, wt, t.getcol_rows("FLAG", rows))
    weight[t.getcol_rows("FLAG_ROW", rows).astype(bool)] = 0.0
    return np.asarray(t.getcol_rows("UVW", rows), np.float64), vis, weight


def group_sums(vis, weight, phi, groups):
    """(nsrc, groups) numerators and (groups,) weight sums, float64."""
    w = weight.astype(np.float64)
    re, im = vis.real.astype(np.float64), vis.imag.astype(np.float64)
    nchan = w.shape[1]
    per = nchan // groups
    wg = w.reshape(len(w), groups, per).sum(axis=(0, 2))
    num = np.array(
        [
            (w * (re * np.cos(p) + im * np.sin(p)))
            .reshape(len(w), groups, per)
            .sum(axis=(0, 2))
            for p in phi
        ]
    )
    return num, wg


def expected_sums(weight, phi, amp_k, spec, groups):
    """(nsrc, groups) numerators of the expected dirty value: sum over
    injected sources Y of a_Y f_Y(c) w_c cos(phi_Y - phi_X)."""
    w = weight.astype(np.float64)
    nchan = w.shape[1]
    per = nchan // groups
    n = len(phi)
    out = np.zeros((n, groups))
    for y in range(n):
        if amp_k[y] == 0.0:
            continue
        wy = w * (amp_k[y] * spec[y])[None, :]
        for x in range(n):
            c = np.cos(phi[y] - phi[x]) if x != y else 1.0
            out[x] += (wy * c).reshape(len(w), groups, per).sum(axis=(0, 2))
    return out


def oracle(ms, truth, lc, groups):
    """Per interval: NumPy DFT per group and position, the band DFT, the
    expected values per group and over the band, and the weight sums."""
    s = lc["settings"]
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as sw:
        freq = np.asarray(sw.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
    lm = [(p["l"], p["m"]) for p in lc["positions"]]
    amp = np.array(truth["amplitude_jy"], np.float64)
    spec = np.array(truth["spectrum"], np.float64)
    out = {k: [] for k in ("dft", "dft_band", "exp", "exp_band", "wsum")}
    with core_ms.open_table(ms) as t:
        times = t.getcol("TIME")
        keep = (t.getcol("FIELD_ID") == lc["field"]["id"]) & (
            t.getcol("ANTENNA1") != t.getcol("ANTENNA2")
        )
        for when in truth["time_mjd_s"]:
            rows = np.flatnonzero(keep & (times == when))
            uvw, vis, weight = read_residual(t, rows, s)
            phi = p1m.phases(uvw, freq, lm)
            num, wg = group_sums(vis, weight, phi, groups)
            k = len(out["dft"])
            ex = expected_sums(weight, phi, amp[k], spec, groups)
            with np.errstate(invalid="ignore", divide="ignore"):
                out["dft"].append(np.where(wg > 0, num / wg, np.nan))
                out["exp"].append(np.where(wg > 0, ex / wg, np.nan))
            out["dft_band"].append(num.sum(axis=1) / wg.sum())
            out["exp_band"].append(ex.sum(axis=1) / wg.sum())
            out["wsum"].append(wg)
    return {k: np.array(v) for k, v in out.items()}


def wsclean_pixels(directory, lc, n, groups, freq_hz):
    """(n, nsrc, groups) WSClean pixels at the positions, and the largest
    |CRVAL3 - group mean frequency| (Hz)."""
    from astropy.io import fits
    from astropy.wcs import WCS

    out = np.full((n, len(lc["positions"]), groups), np.nan)
    worst = 0.0
    pixels = None
    for k in range(n):
        for g in range(groups):
            path = Path(directory) / f"w-t{k:04d}-{g:04d}-dirty.fits"
            with fits.open(path) as h:
                image = np.asarray(h[0].data[0, 0], np.float64)
                header = h[0].header
                worst = max(worst, abs(float(header["CRVAL3"]) - freq_hz[g]))
                if pixels is None:
                    wcs = WCS(header).celestial
                    pixels = []
                    for p in lc["positions"]:
                        x, y = wcs.world_to_pixel_values(p["ra_deg"], p["dec_deg"])
                        pixels.append((round(float(x)), round(float(y))))
            for s, (x, y) in enumerate(pixels):
                out[k, s, g] = image[y, x]
    return out, worst, pixels


def robust(x):
    x = x[np.isfinite(x)]
    return float(MAD * np.median(np.abs(x - np.median(x)))) if x.size else math.nan


def csv_empty_groups(lc_dir, empty):
    """D5's CSV side: every row of an empty group reads `nan`."""
    bad = 0
    with open(Path(lc_dir) / "dynspec.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if int(row["group"]) in empty and row["flux_jy"] != "nan":
                bad += 1
    return bad


def score(ms, truth_path, lc_dir, wsclean=None, real=False, control=None):
    started = time.perf_counter()
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    lc = json.loads((Path(lc_dir) / "lightcurve.json").read_text(encoding="utf-8"))
    names = [s["name"] for s in truth["sources"]]
    if [p["name"] for p in lc["positions"]] != names:
        raise SystemExit("light curve positions are not the truth's, in order")
    groups = lc["settings"]["channels_out"]
    if not groups:
        raise SystemExit("the run has no dynamic spectrum (--channels-out)")
    n = lc["intervals"]
    if not np.array_equal(np.array(lc["time_mjd_s"]), np.array(truth["time_mjd_s"])):
        raise SystemExit("interval times differ from the truth's")
    o = oracle(ms, truth, lc, groups)
    dyn = np.array(
        [[[math.nan if v is None else v for v in g] for g in k]
         for k in lc["dynspec_flux_jy"]], np.float64)  # fmt: skip
    wsum = np.array(lc["dynspec_weight_sum"], np.float64)
    band = np.array(lc["flux_jy"], np.float64)
    freq_hz = [g["freq_hz"] for g in lc["dynspec_groups"]]
    res = {"case": truth.get("case"), "intervals": n, "groups": groups}
    # sigma per cell
    if real:
        if control is None:
            raise SystemExit("--real needs --control (the uninjected run)")
        ctl = json.loads(
            (Path(control) / "lightcurve.json").read_text(encoding="utf-8")
        )
        f_index = [p["name"] for p in ctl["positions"]].index("F")
        cdyn = np.array(
            [[math.nan if v is None else v for v in k[f_index]]
             for k in ctl["dynspec_flux_jy"]], np.float64)  # fmt: skip
        sig_g = np.array([robust(cdyn[:, g]) for g in range(groups)])
        sig_cell = np.broadcast_to(sig_g[None, :], (n, groups))
        res["sigma_dyn_jy"] = sig_g.tolist()
    else:
        sig_cell = np.array(
            [[math.nan if v is None else v for v in k] for k in truth["sigma_cell_jy"]],
            np.float64,
        )
    sc = sig_cell[:, None, :]
    finite = np.isfinite(o["dft"])
    empty = sorted(
        int(g) for g in np.flatnonzero(~np.isfinite(o["dft"]).any(axis=(0, 1)))
    )
    d1 = np.abs(dyn - o["dft"]) / sc
    res["D1"] = {
        "max_over_sigma": float(np.nanmax(d1)),
        "finite_cells_equal": bool(np.array_equal(np.isfinite(dyn), finite)),
        "weight_sum_max_rel": float(
            np.nanmax(np.abs(wsum - o["wsum"]) / np.where(o["wsum"] > 0, o["wsum"], 1))
        ),
    }
    res["D1"]["pass"] = bool(
        res["D1"]["max_over_sigma"] <= D_BOUND and res["D1"]["finite_cells_equal"]
    )
    # D3, D3b
    z = (dyn - o["exp"]) / sc
    per = {}
    for s, name in enumerate(names):
        zs = z[:, s, :][np.isfinite(z[:, s, :])]
        nc = zs.size
        per[name] = {
            "cells": int(nc),
            "bias_over_sigma": float(zs.mean()),
            "bias_bound": 3.0 / math.sqrt(nc),
            "chi2_reduced": float(np.mean(zs**2)),
            "chi2_range": [1 - 3 * math.sqrt(2.0 / nc), 1 + 3 * math.sqrt(2.0 / nc)],
        }
    sources_d3 = names if not real else [x for x in names if x != "F"]
    res["D3"] = {
        "per_source": {k: per[k]["bias_over_sigma"] for k in names},
        "bound": {k: per[k]["bias_bound"] for k in names},
        "gated_sources": sources_d3,
        "pass": all(
            abs(per[k]["bias_over_sigma"]) <= per[k]["bias_bound"] for k in sources_d3
        ),
    }
    res["D3b"] = {
        "per_source": {k: per[k]["chi2_reduced"] for k in names},
        "range": {k: per[k]["chi2_range"] for k in names},
        "pass": all(
            per[k]["chi2_range"][0] <= per[k]["chi2_reduced"] <= per[k]["chi2_range"][1]
            for k in names
        ),
        "gated": not real,
    }
    # D4: group-weighted mean against the light curve
    with np.errstate(invalid="ignore"):
        wmean = np.nansum(dyn * wsum[:, None, :], axis=2) / wsum.sum(axis=1)[:, None]
    sig_k = np.array(
        truth.get("sigma_snap_interval_jy") or [x for x in lc["sigma_meas_jy"]],
        np.float64,
    )[:, None]
    d4 = np.abs(wmean - band) / sig_k
    res["D4"] = {"max_over_sigma": float(d4.max()), "pass": bool(d4.max() <= D4_BOUND)}
    # D5: empty groups
    js = [
        g
        for g in empty
        if any(
            lc["dynspec_flux_jy"][k][s][g] is not None
            for k in range(n)
            for s in range(len(names))
        )
    ]
    bad_csv = csv_empty_groups(lc_dir, set(empty)) if empty else 0
    res["D5"] = {
        "empty_groups": empty,
        "json_not_null": js,
        "csv_not_nan_rows": bad_csv,
        "pass": bool(empty and not js and bad_csv == 0) if not real else not js,
        "gated": bool(empty),
    }
    # P1 band-level parity and recovery (the real track's T2a, T3a, T3c, T3d)
    if real:
        sigma_meas = np.array(lc["sigma_meas_jy"], np.float64)
        sm = sigma_meas[:, None]
        t2a = np.abs(band - o["dft_band"]) / sm
        res["T2a"] = {
            "max_over_sigma": float(t2a.max()),
            "pass": bool(t2a.max() <= D_BOUND),
        }
        snap = np.array(
            [[math.nan if v is None else v for v in k] for k in lc["flux_snapshot_jy"]]
        )
        t2b = np.abs(snap - band) / sm
        res["T2b"] = {"max_over_sigma": float(np.nanmax(t2b)),
                      "pass": bool(np.nanmax(t2b) <= D_BOUND)}  # fmt: skip
        zb = (band - o["exp_band"]) / np.median(sigma_meas)
        bound = 3.0 / math.sqrt(n)
        t3 = {nm: float(zb[:, s].mean()) for s, nm in enumerate(names)}
        res["T3a"] = {
            "per_source": t3,
            "bound": bound,
            "gated_sources": sources_d3,
            "pass": all(abs(t3[k]) <= bound for k in sources_d3),
        }
        res["T3b"] = {
            "per_source": {
                nm: float(
                    np.mean(((band[:, s] - o["exp_band"][:, s]) / sigma_meas) ** 2)
                )
                for s, nm in enumerate(names)
            },
            "gated": False,
        }
        res["T3c"] = {"pass": True}
        amp_truth = dict(truth)
        amp_truth["flux_jy"] = truth["amplitude_jy"]
        res["T3d"] = recovery_real(amp_truth, band, sigma_meas)
        res["sigma_meas_jy"] = {
            "median": float(np.median(sigma_meas)),
            "min": float(sigma_meas.min()),
            "max": float(sigma_meas.max()),
        }
    if wsclean:
        pix, worst, pixels = wsclean_pixels(wsclean, lc, n, groups, freq_hz)
        d2 = np.abs(pix - dyn) / sc
        res["D2"] = {
            "max_over_sigma": float(np.nanmax(d2)),
            "crval3_max_offset_hz": worst,
            "pixels": pixels,
            "pixels_equal_rang": [
                list(p["pixel"] or []) == list(q)
                for p, q in zip(lc["positions"], pixels, strict=True)
            ]
            if lc["settings"].get("images")
            else None,
            "pass": bool(np.nanmax(d2) <= D_BOUND),
        }
    gates = ["D1", "D3", "D4"] + (["D5"] if res["D5"]["gated"] else [])
    gates += ["D3b"] if not real else ["T2a", "T2b", "T3a", "T3c", "T3d"]
    if wsclean:
        gates.append("D2")
    res["gates"] = {g: res[g]["pass"] for g in gates}
    res["all_pass"] = all(res["gates"].values())
    res["seconds"] = time.perf_counter() - started
    return res


def recovery_real(truth, flux, sigma_meas):
    """T3d with sigma_meas as the unit (ts-p2.md 5): each pulse with peak
    truth >= 7 median sigma_meas."""
    sig = float(np.median(sigma_meas))
    return p1m.recovery(truth, flux, sigma_meas, sig)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ms")
    p.add_argument("truth")
    p.add_argument("lc_dir")
    p.add_argument("out")
    p.add_argument("--wsclean", help="directory of WSClean's w-tNNNN-GGGG-dirty.fits")
    p.add_argument("--real", action="store_true", help="the real track (ts-p2.md 4.2)")
    p.add_argument("--control", help="the uninjected run's LC_DIR (with --real)")
    a = p.parse_args(argv)
    res = score(a.ms, a.truth, a.lc_dir, a.wsclean, a.real, a.control)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": res["gates"], "all_pass": res["all_pass"]}))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
