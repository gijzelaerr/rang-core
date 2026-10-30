"""B1-2 driver: the identifiability survey on S1-S5 (research/b1-2-identifiability.md).

Subcommands (every run writes into a fresh `OUT` directory under outputs/):

- `fieldmodel OUT --pilot DIR`: the frozen ESO137 field model (three
  self-calibration rounds, core-gridder images, Hogbom CLEAN, merged
  components, gate E0) from the S4 pilot fetch;
- `survey SET OUT [--pilot DIR] [--track DIR] [--field DIR]`: the survey of
  one set (S1-S5): noise calibration, the Schur-reduced normal blocks, the
  measures, the decision rule, and on S1 the native anchored response;
- `archive OUT_JSON RUN...`: the committed archive of derived numbers.

Inputs: LUNO tiles archived by K/L1/L2 (nothing fetched), the B1-0
holography product (CC BY-NC 4.0, de Villiers 2023, DOI
10.48479/wdb0-h061), the L1-M lsm, and the ESO137 fetches of
`examples/fetch_eso137_pilot.py` (CC BY 4.0, Ramatsoku et al. 2020).
"""

import argparse
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import (
    beam_holography,
    core,
    core_campaign,
    core_grid,
    core_weights,
    lsm,
    measures,
    rusage,
)
from rang import beam_identifiability as bi
from rang import core_campaign_1830 as l2
from rang.core_campaign_fieldmodel import LSM_SHA256, verify_lsm

ROOT = Path(__file__).resolve().parents[1]
HOLOGRAPHY = ROOT / "outputs/b1-20261030-05-holography"
LSM = ROOT / "outputs/l1m-20261030-00-fieldmodel/pks1934-638.lsm"
L2_FETCH = ROOT / "outputs/l2-1830-20261030-01-fetch"
FEED_ROOT = ROOT / "outputs/luno-solve-20261029-02/inputs"
S3_POINT = {"i0_jy": 7.838918377161836, "alpha": 0.22227145111749222, "nu0_hz": 1.284e9}
TRACK_TILE = 20
CHUNK_ROWS = 512
# The convergence check on S1 (outputs/b1-2-20261030-03-S1) changed the
# common pointing sigma by far more than 5 % between 32- and 16-channel beam
# evaluation, so by the frozen rule the 16-channel evaluation ("sub16") is
# the verdict evaluation for every set; "nominal" (32) is kept as a record.
VERDICT_VARIANT = "sub16"
VARIANTS_CHECKED = (
    ("nominal", 0.0, 1),
    ("sub16", 0.0, 2),
    ("rot90", math.pi / 2, 2),
)
VARIANTS_FINER = (("nominal", 0.0, 1), ("sub16", 0.0, 2))
VARIANTS_POSTHOC_S1 = (("sub16", 0.0, 2), ("sub8", 0.0, 4))
IMAGE = {
    "width": 4096,
    "height": 4096,
    "scale_arcsec": 4.0,
    "w_layers": 128,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
WINDOW = 2048
ROUNDS = (
    {"phase_only": True, "sigma": 20.0, "max_iter": 5000},
    {"phase_only": True, "sigma": 10.0, "max_iter": 10000},
    {"phase_only": False, "sigma": 5.0, "max_iter": 20000},
)
MAX_COMPONENTS = 300
MERGE_PIXELS = 3
E0_SNR = 50.0
E0_FLUX = 0.5
ESO_REF_FREQ = 1.4e9


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)


def write_json(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, default=core_campaign._json_default) + "\n"
    )


def git_head():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# --------------------------------------------------------------------------
# Loaders


def _decode(objects, name, chunk=None):
    meta = json.loads((objects / name / ".zarray").read_text())
    if meta.get("filters") or meta["dtype"] == "|O":
        raise ValueError(f"{name}: object or filtered arrays are refused")
    key = chunk or ".".join("0" for _ in meta["shape"])
    raw = core.blosc_decode((objects / name / key).read_bytes())
    full = np.frombuffer(raw, np.dtype(meta["dtype"])).reshape(meta["chunks"])
    index = [int(i) for i in key.split(".")]
    return full[
        tuple(
            slice(0, min(c, s - i * c))
            for c, s, i in zip(meta["chunks"], meta["shape"], index, strict=True)
        )
    ]


def load_luno(group, stations=None):
    roots = l2.roots_for(group, L2_FETCH if group == "MAIN/MAIN_2" else None)
    started = time.perf_counter()
    arrays, rows, stats = l2.decode_inputs(
        group, roots, stations, ("DATA", "FLAG", "WEIGHT_SPECTRUM")
    )
    extra = l2.decode_extra(group, rows, roots)
    receptor = _decode(FEED_ROOT / "FEED", "FEED_0/RECEPTOR_ANGLE")
    return {
        "label": group,
        "data": arrays["DATA"],
        "flag": arrays["FLAG"],
        "weight": arrays["WEIGHT_SPECTRUM"],
        "a1": arrays["ANTENNA1"].astype(int),
        "a2": arrays["ANTENNA2"].astype(int),
        "time": arrays["TIME"],
        "uvw": extra["uvw"],
        "freqs": extra["chan_freq"],
        "positions": extra["antenna_position"],
        "phase_dir": extra["phase_dir"],
        "field": extra["field_name"],
        "receptor_angle": np.asarray(receptor).tolist(),
        "decode": {**stats, "seconds": time.perf_counter() - started},
    }


def _eso_rows(objects, group, cube_key):
    a1 = _decode(objects, f"{group}/ANTENNA1").astype(int)
    a2 = _decode(objects, f"{group}/ANTENNA2").astype(int)
    frow = _decode(objects, f"{group}/FLAG_ROW")
    keep = (a1 != a2) & ~frow
    out = {
        "a1": a1[keep],
        "a2": a2[keep],
        "time": _decode(objects, f"{group}/TIME")[keep],
        "uvw": np.ascontiguousarray(_decode(objects, f"{group}/UVW")[keep], float),
    }
    for col in ("DATA", "FLAG", "WEIGHT_SPECTRUM"):
        out[col] = np.ascontiguousarray(
            _decode(objects, f"{group}/{col}", cube_key)[keep]
        )
    return out, keep


def load_eso_pilot(pilot):
    objects = Path(pilot) / "objects"
    started = time.perf_counter()
    rows, keep = _eso_rows(objects, "MAIN/MAIN_0", "0.0.0")
    return {
        "label": "ESO137 ms1_target_subset MAIN_0 row chunk 0",
        "data": rows["DATA"],
        "flag": rows["FLAG"],
        "weight": rows["WEIGHT_SPECTRUM"],
        "a1": rows["a1"],
        "a2": rows["a2"],
        "time": rows["time"],
        "uvw": rows["uvw"],
        "freqs": _decode(objects, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ")[
            0
        ].astype(float),
        "positions": _decode(objects, "ANTENNA/ANTENNA_0/POSITION").astype(float),
        "phase_dir": _decode(objects, "FIELD/FIELD_0/PHASE_DIR")[0, 0].astype(float),
        "field": "ESO137 (FIELD 0)",
        "receptor_angle": _decode(objects, "FEED/FEED_0/RECEPTOR_ANGLE").tolist(),
        "decode": {"seconds": time.perf_counter() - started, "rows": int(keep.sum())},
    }


def load_eso_track(track):
    objects = Path(track) / "objects"
    freqs_all = _decode(objects, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ")[0]
    freqs = freqs_all[TRACK_TILE * 128 : (TRACK_TILE + 1) * 128].astype(float)
    positions = _decode(objects, "ANTENNA/ANTENNA_0/POSITION").astype(float)
    phase_dir = _decode(objects, "FIELD/FIELD_0/PHASE_DIR")[0, 0].astype(float)
    scans = []
    for k in range(7):
        group = f"MAIN/MAIN_{k}"
        attrs = json.loads((objects / group / ".zattrs").read_text())
        rows, _keep = _eso_rows(objects, group, f"0.{TRACK_TILE}.0")
        scans.append(
            {
                "label": f"ESO137 ms1_target {group} scan {attrs.get('SCAN_NUMBER')}",
                "scan_number": attrs.get("SCAN_NUMBER"),
                "data": rows["DATA"],
                "flag": rows["FLAG"],
                "weight": rows["WEIGHT_SPECTRUM"],
                "a1": rows["a1"],
                "a2": rows["a2"],
                "time": rows["time"],
                "uvw": rows["uvw"],
                "freqs": freqs,
                "positions": positions,
                "phase_dir": phase_dir,
                "field": "ESO137 (FIELD 0)",
                "receptor_angle": None,
            }
        )
    return scans


# --------------------------------------------------------------------------
# Sky models


def sky_lsm():
    verify_lsm(LSM, LSM_SHA256)
    return lsm.load(LSM)


def sky_from_sources(sources, phase_dir):
    comps = lsm.components(sources, phase_dir)
    return {
        k: comps[k] for k in ("lm", "kind", "flux", "coeffs", "ref_freq", "gauss_shape")
    }


def sky_point(i0, alpha, nu0):
    return {
        "lm": np.zeros((1, 2)),
        "kind": np.zeros(1, np.uint8),
        "flux": np.array([i0]),
        "coeffs": np.array([[alpha]]),
        "ref_freq": np.array([nu0]),
        "gauss_shape": np.zeros((1, 3)),
    }


def sky_components(lm, flux):
    k = len(flux)
    return {
        "lm": np.asarray(lm, float),
        "kind": np.zeros(k, np.uint8),
        "flux": np.asarray(flux, float),
        "coeffs": np.zeros((k, 1)),
        "ref_freq": np.full(k, ESO_REF_FREQ),
        "gauss_shape": np.zeros((k, 3)),
    }


def predict(sky, uvw, freqs, block=2048):
    out = np.empty((len(uvw), len(freqs)), np.complex128)
    for start in range(0, len(uvw), block):
        out[start : start + block] = core.predict_components(
            uvw[start : start + block],
            freqs,
            sky["lm"],
            sky["kind"],
            sky["flux"],
            sky["coeffs"],
            np.ones(len(sky["flux"]), bool),
            sky["ref_freq"],
            sky["gauss_shape"],
        )
    return out


# --------------------------------------------------------------------------
# Noise calibration


HANDS = ((0, 0), (1, 3))  # (hand, correlation): X = XX, Y = YY


def eligible(d, hand_corr):
    c = hand_corr
    return (
        (~d["flag"][..., c])
        & (d["weight"][..., c] > 0)
        & np.isfinite(d["data"][..., c])
    )


def noise_for(d):
    out = {}
    for hand, c in HANDS:
        e = eligible(d, c)
        rec = bi.noise_scale(d["data"][..., c], d["weight"][..., c], e)
        rec["eligible_samples"] = int(e.sum())
        out[hand] = rec
    return out


def amplitude_scale_luno(d, sky):
    """c_h = median |D_h| / median |M| over the eligible samples of hand h."""
    started = time.perf_counter()
    model = np.abs(predict(sky, d["uvw"], d["freqs"])).astype(np.float32)
    out = {}
    for hand, c in HANDS:
        e = eligible(d, c)
        num = float(np.median(np.abs(d["data"][..., c][e])))
        den = float(np.median(model[e]))
        out[hand] = {"median_abs_data": num, "median_abs_model": den, "c": num / den}
    out["seconds"] = time.perf_counter() - started
    return out


# --------------------------------------------------------------------------
# Field model (S4) and per-scan gains (S5)


def solve_gains(d, model, phase_only, block=32):
    """Diagonal gains per hand and per 32-channel block, constant in time."""
    nant = len(d["positions"])
    nchan = len(d["freqs"])
    nblk = math.ceil(nchan / block)
    gains = np.ones((nblk, nant, 2), complex)
    iters = []
    for f in range(nblk):
        ch = slice(f * block, min((f + 1) * block, nchan))
        for hand, c in HANDS:
            e = eligible(d, c)[:, ch]
            rows, cols = np.nonzero(e)
            data = d["data"][:, ch, c][rows, cols].astype(complex)
            m = model[:, ch][rows, cols]
            w = d["weight"][:, ch, c][rows, cols].astype(float)
            g, it = bi.stefcal(
                data, m, w, d["a1"][rows], d["a2"][rows], nant, phase_only
            )
            gains[f, :, hand] = g
            iters.append(it)
    return gains, {
        "iterations_max": int(max(iters)),
        "iterations_median": float(np.median(iters)),
    }


def corrected(d, gains, block=32):
    nchan = len(d["freqs"])
    out = np.empty(d["data"].shape[:2] + (2,), np.complex64)
    wout = np.zeros(d["data"].shape[:2] + (2,), np.float32)
    for f in range(gains.shape[0]):
        ch = slice(f * block, min((f + 1) * block, nchan))
        for hand, c in HANDS:
            gp = gains[f, d["a1"], hand][:, None]
            gq = gains[f, d["a2"], hand][:, None]
            prod = gp * np.conj(gq)
            out[:, ch, hand] = d["data"][:, ch, c] / prod
            e = eligible(d, c)[:, ch]
            wout[:, ch, hand] = np.where(
                e, d["weight"][:, ch, c] * np.abs(prod) ** 2, 0
            )
    return out, wout


def image(d, vis, wts):
    """Stokes I dirty image and PSF with the core gridder (Briggs 0.5)."""
    sample = (0.5 * (vis[..., 0] + vis[..., 1])).astype(np.complex64)
    both = (wts[..., 0] > 0) & (wts[..., 1] > 0)
    weight = np.where(both, 4 * np.minimum(wts[..., 0], wts[..., 1]), 0).astype(
        np.float32
    )
    sample = np.where(both, sample, 0).astype(np.complex64)
    padded = core_weights.padded_size(IMAGE["width"], IMAGE["padding"])
    padded_h = core_weights.padded_size(IMAGE["height"], IMAGE["padding"])
    imaging = core_weights.imaging_weights(
        d["uvw"],
        core_weights.wsclean_wavelengths(d["freqs"]),
        weight,
        np.ones(len(weight), bool),
        mode="briggs",
        robust=0.5,
        width=padded,
        height=padded_h,
        pixel_scale=core_weights.pixel_scale_radians(IMAGE["scale_arcsec"]),
        return_grid=False,
    )
    products = core_grid.invert(
        d["uvw"], d["freqs"], sample, weight, imaging["weights"], **IMAGE
    )
    return products["dirty"], products["psf"], products["stats"]


def pixel_lm(rows, cols):
    """(l, m) of image pixels (row, col) in WSClean's FITS orientation."""
    scale = math.radians(IMAGE["scale_arcsec"] / 3600)
    l = -(np.asarray(cols) - IMAGE["width"] / 2) * scale
    m = (np.asarray(rows) - IMAGE["height"] / 2) * scale
    return l, m


def merged_components(comp):
    """CLEAN components merged on MERGE_PIXELS cells; positive cells only."""
    y0 = IMAGE["height"] // 2 - WINDOW // 2
    x0 = IMAGE["width"] // 2 - WINDOW // 2
    rr, cc = np.nonzero(comp)
    flux = comp[rr, cc]
    cell = (rr // MERGE_PIXELS) * (WINDOW // MERGE_PIXELS + 1) + cc // MERGE_PIXELS
    uniq, inv = np.unique(cell, return_inverse=True)
    total = np.bincount(inv, flux)
    ry = np.bincount(inv, flux * rr)
    rx = np.bincount(inv, flux * cc)
    keep = total > 0
    rows = ry[keep] / total[keep] + y0
    cols = rx[keep] / total[keep] + x0
    l, m = pixel_lm(rows, cols)
    return (
        np.stack([l, m], 1),
        total[keep],
        {
            "clean_components": len(flux),
            "clean_flux": float(flux.sum()),
            "cells": len(uniq),
            "positive_cells": int(keep.sum()),
        },
    )


def robust_sigma(x):
    med = np.median(x)
    return float(1.4826 * np.median(np.abs(x - med)))


def orientation_check(d):
    """A point predicted by the core at a known (l, m) must image at the
    pixel `pixel_lm` maps to it (WSClean orientation)."""
    lm0 = np.array([[math.radians(0.2), math.radians(-0.1)]])
    sky = sky_components(lm0, [1.0])
    sub = slice(0, len(d["uvw"]), 7)
    dd = {k: (v[sub] if k in ("uvw", "a1", "a2") else v) for k, v in d.items()}
    vis = predict(sky, dd["uvw"], d["freqs"][::25])
    dd["freqs"] = d["freqs"][::25]
    v2 = np.stack([vis, vis], -1).astype(np.complex64)
    w2 = np.ones(v2.shape, np.float32)
    dirty, _, _ = image(dd, v2, w2)
    r, c = np.unravel_index(np.argmax(dirty), dirty.shape)
    l, m = pixel_lm(r, c)
    scale = math.radians(IMAGE["scale_arcsec"] / 3600)
    return {
        "injected_lm_deg": np.degrees(lm0[0]).tolist(),
        "peak_pixel": [int(r), int(c)],
        "recovered_lm_deg": [math.degrees(l), math.degrees(m)],
        "pass": bool(
            abs(l - lm0[0, 0]) <= 1.5 * scale and abs(m - lm0[0, 1]) <= 1.5 * scale
        ),
    }


def first_null_radius(beam, freq_hz):
    x, y = beam_holography.grid(2.4, beam_holography.PIXEL_DEG / 2)
    power = beam.power_i("array_average", x.ravel(), y.ravel(), freq_hz).reshape(
        x.shape
    )
    radius, profile = beam_holography.radial_profile(power, x, y, rmax_deg=2.4)
    return beam_holography.lobe_radii(radius, profile)


def field_model(pilot, out, beam):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    stages = {}
    t0 = time.perf_counter()
    d = load_eso_pilot(pilot)
    stages["load"] = time.perf_counter() - t0
    record = {
        "protocol": "research/b1-2-identifiability.md",
        "git_head": git_head(),
        "rows": len(d["a1"]),
        "channels": len(d["freqs"]),
        "rounds": [],
    }
    mark = time.perf_counter()
    record["orientation_check"] = orientation_check(d)
    stages["orientation_check"] = time.perf_counter() - mark
    log("orientation", record["orientation_check"])
    lobes = first_null_radius(beam, float(d["freqs"][0]))
    record["lobes_at_lowest_frequency"] = lobes
    model = np.ones(d["data"].shape[:2], complex)  # round 0: 1 Jy at the centre
    comps = None
    for k, rnd in enumerate(ROUNDS):
        mark = time.perf_counter()
        gains, solve = solve_gains(d, model, rnd["phase_only"])
        if k == 1:
            # orientation sanity: the model and its conjugate against the data
            vis, wts = corrected(d, gains)
            rec = {}
            for name, m in (("model", model), ("conjugate", np.conj(model))):
                r = 0.0
                for hand in range(2):
                    r += float(np.sum(wts[..., hand] * np.abs(vis[..., hand] - m) ** 2))
                rec[name] = r
            record["model_sign_check_chi2"] = rec
        vis, wts = corrected(d, gains)
        dirty, psf, stats = image(d, vis, wts)
        sigma = robust_sigma(
            dirty[
                IMAGE["height"] // 2 - WINDOW // 2 : IMAGE["height"] // 2 + WINDOW // 2,
                IMAGE["width"] // 2 - WINDOW // 2 : IMAGE["width"] // 2 + WINDOW // 2,
            ]
        )
        comp, res, iters = bi.hogbom(
            dirty, psf, WINDOW, 0.1, rnd["sigma"] * sigma, rnd["max_iter"]
        )
        res_sigma = robust_sigma(res)
        lm, flux, merge = merged_components(comp)
        comps = (lm, flux)
        np.savez(
            out / f"round{k}.npz",
            lm=lm,
            flux=flux,
            gains=gains,
            peak=float(dirty.max()),
        )
        core_grid.write_fits(
            out / f"round{k}-dirty.fits",
            dirty,
            core_grid.wcs_header(
                d["phase_dir"],
                IMAGE["width"],
                IMAGE["height"],
                IMAGE["scale_arcsec"],
                d["freqs"],
            ),
        )
        model = predict(sky_components(lm, flux), d["uvw"], d["freqs"])
        record["rounds"].append(
            {
                "round": k,
                **rnd,
                "solve": solve,
                "dirty_peak": float(dirty.max()),
                "dirty_robust_sigma": sigma,
                "residual_robust_sigma": res_sigma,
                "clean_iterations": int(iters),
                "gridder": stats,
                **merge,
                "seconds": time.perf_counter() - mark,
            }
        )
        log("round", k, record["rounds"][-1])
        stages[f"round{k}"] = time.perf_counter() - mark
    lm, flux = comps
    r = np.degrees(np.hypot(lm[:, 0], lm[:, 1]))
    inside = r <= lobes["r_first_null_deg"]
    order = np.argsort(-np.where(inside, flux, -np.inf))
    kept = order[: min(MAX_COMPONENTS, int(inside.sum()))]
    final = record["rounds"][-1]
    snr = final["dirty_peak"] / final["residual_robust_sigma"]
    kept_fraction = float(flux[kept].sum() / final["clean_flux"])
    # c_h from the round-2 gains: median over solved baselines |g_p g_q|
    c = gain_scale(d, np.load(out / "round2.npz")["gains"])
    record.update(
        {
            "components_kept": len(kept),
            "flux_kept": float(flux[kept].sum()),
            "flux_kept_fraction": kept_fraction,
            "radius_max_deg": float(r[kept].max()) if len(kept) else None,
            "flux_by_radius": {
                f"<= {lim} deg": float(flux[kept][r[kept] <= lim].sum())
                for lim in (0.1, 0.25, 0.5, 0.75, 1.0)
            },
            "brightest_jy": float(flux[kept].max()) if len(kept) else None,
            "e0": {
                "snr": snr,
                "snr_min": E0_SNR,
                "flux_fraction_min": E0_FLUX,
                "pass": bool(snr >= E0_SNR and kept_fraction >= E0_FLUX),
            },
            "c": c,
            "stages_seconds": stages,
            "peak_rss_mb": rusage.peak_rss_mb(),
        }
    )
    np.savez(out / "components.npz", lm=lm[kept], flux=flux[kept])
    write_json(out / "fieldmodel.json", record)
    log("E0", record["e0"], "kept", len(kept), kept_fraction)
    return record


def gain_scale(d, gains, block=32):
    """c_h = median over solved (block, baseline) pairs of |g_p g_q|. A
    baseline counts in a block when it has eligible samples of that hand
    there, so fully flagged blocks (gains left at 1) do not enter."""
    nchan = len(d["freqs"])
    nant = len(d["positions"])
    out = {}
    for hand, c in HANDS:
        values = []
        e = eligible(d, c)
        for f in range(gains.shape[0]):
            ch = slice(f * block, min((f + 1) * block, nchan))
            rows = np.flatnonzero(e[:, ch].any(axis=1))
            if not len(rows):
                continue
            key = np.unique(d["a1"][rows] * nant + d["a2"][rows])
            p, q = key // nant, key % nant
            values.append(np.abs(gains[f, p, hand] * gains[f, q, hand]))
        out[hand] = float(np.median(np.concatenate(values)))
    return out


def scan_scale(d, sky):
    """c_h of one S5 scan: amplitude-and-phase gains against the field model."""
    model = predict(sky, d["uvw"], d["freqs"])
    gains, solve = solve_gains(d, model, False)
    return gain_scale(d, gains), solve


# --------------------------------------------------------------------------
# The survey of one set


def native_anchored(d, sky, rows_t, ch, terms, fac, kappa, survey_nant):
    """S1 only: the native full-Jones anchored response per direction for one
    gain bin, and the NumPy diagonal response on the same samples."""
    from rang.core_influence import anchored_response, training_normals

    ok = np.ones((len(rows_t), len(ch)), bool)
    for hand, c in HANDS:
        ok &= eligible(
            {
                k: v[rows_t][:, ch] if k in ("data", "flag", "weight") else v
                for k, v in d.items()
            },
            c,
        )
    w = d["weight"][rows_t][:, ch].astype(float)
    ok &= (w[..., 1] > 0) & (w[..., 2] > 0)
    ok &= ~d["flag"][rows_t][:, ch][..., 1] & ~d["flag"][rows_t][:, ch][..., 2]
    rr, cc = np.nonzero(ok)
    if len(rr) == 0:
        return None
    p = d["a1"][rows_t][rr]
    q = d["a2"][rows_t][rr]
    t = terms[rr, cc]  # (n, K) unwhitened S K
    model = t.sum(1)
    models = np.zeros((len(rr), 2, 2), complex)
    models[:, 0, 0] = model
    models[:, 1, 1] = model
    kx, ky = kappa[(0, 0)], kappa[(0, 1)]
    weights = np.stack(
        [
            w[rr, cc, 0] * kx,
            w[rr, cc, 1] * 0.5 * (kx + ky),
            w[rr, cc, 2] * 0.5 * (kx + ky),
            w[rr, cc, 3] * ky,
        ],
        1,
    )
    nant = 4
    sigs = []
    for j in range(2):
        for a in range(nant):
            s = np.zeros((len(rr), 2), complex)
            for hand in range(2):
                g = fac["gamma"][:, hand, j]
                s[:, hand] = np.where(p == a, t @ g, 0) + np.where(
                    q == a, t @ np.conj(g), 0
                )
            sigs.append(s)
    for c6 in range(6):
        s = np.stack([t @ fac["beta"][:, hand, c6] for hand in range(2)], 1)
        sigs.append(s)
    identity = np.broadcast_to(np.eye(2), (1, 4, 2, 2)).astype(complex).copy()
    out = []
    for s in sigs:
        res = np.zeros((len(rr), 2, 2), complex)
        res[:, 0, 0] = s[:, 0]
        res[:, 1, 1] = s[:, 1]
        h, b, _ = training_normals(
            identity, models, res, weights, p, q, np.zeros(len(rr), int)
        )
        resp = anchored_response(
            h[0], np.zeros(32), np.zeros((32, 32)), -b[0], identity[0], np.ones(4, bool)
        )
        rec = {
            "status": resp["native_status"],
            "guard_pass": resp["guard_pass"],
            "max_relative_step": resp["diagnostics"]["max_relative_step"],
        }
        if resp["delta"] is not None:
            # NumPy diagonal response on the same samples, with the native damping
            lam = resp["diagnostics"]["largest_curvature"]
            diffs = []
            num_all = []
            for hand in range(2):
                kap = kx if hand == 0 else ky
                z = (
                    t
                    * math.sqrt(1.0)
                    * np.sqrt(w[rr, cc, 0 if hand == 0 else 3] * kap)[:, None]
                )
                sw = np.sqrt(w[rr, cc, 0 if hand == 0 else 3] * kap)
                gam = np.zeros((1, 1, len(sky["flux"]), 2), complex)
                bet = np.zeros((1, 1, len(sky["flux"]), 6))
                hh = bi.block_normals(p, q, nant, z, gam, bet)
                a_g = hh[: 2 * nant, : 2 * nant]
                # score of the signature against the gains in the same metric
                sv = s[:, hand] * sw
                mdl = z.sum(1)
                xe = np.bincount(p, (np.conj(mdl) * sv).real, nant) + np.bincount(
                    q, (np.conj(mdl) * sv).real, nant
                )
                xp = np.bincount(p, (np.conj(mdl) * sv).imag, nant) - np.bincount(
                    q, (np.conj(mdl) * sv).imag, nant
                )
                delta = bi.anchored_diagonal(a_g, np.r_[xe, xp][:, None], lam_max=lam)[
                    :, 0
                ]
                native = resp["delta"][:, hand, hand]
                ours = delta[:nant] + 1j * delta[nant:]
                diffs.append(np.max(np.abs(native - ours)))
                num_all.append(np.max(np.abs(ours)))
            rec["relative_difference_diagonal"] = float(
                max(diffs) / max(max(num_all), 1e-300)
            )
        out.append(rec)
    del survey_nant
    return out


def run_survey(
    scans, sky, beam, variants, kappa_raw, out, native=False, slope=False, taper=None
):
    """Accumulate the survey over all scans of a set; returns the Survey and
    the native anchored records (S1). `slope` (post hoc) also frees a
    per-antenna log-amplitude and phase slope across each gain bin.
    `taper` (post hoc): [(lo_m, hi_m, ratio)], the model visibilities of rows
    with baseline length in [lo, hi) scaled by `ratio` (the measured median
    |data| / |model| of the band), i.e. weights scaled by ratio^2."""
    nant = len(scans[0]["positions"])
    ncomp = len(sky["flux"])
    nvar = len(variants)
    nsub = max(v[2] for v in variants)
    survey = bi.Survey(
        nant,
        ncomp,
        nscan=len(scans),
        nvar=nvar,
        anchored=not slope,
        gain_sets=2 if slope else 1,
    )
    native_records = []
    pa = []
    floor_counts = []
    for s, d in enumerate(scans):
        times = np.unique(d["time"])
        integ = np.searchsorted(times, d["time"])
        tbin = integ // bi.GRID[0]
        centre = measures.array_centre(d["positions"])
        bins = np.unique(tbin)
        tmean = np.array([d["time"][tbin == t].mean() for t in bins])
        q_all = measures.parallactic_angle(tmean, *d["phase_dir"], centre)
        pa.append(np.degrees(q_all).tolist())
        nchan = len(d["freqs"])
        nblk = math.ceil(nchan / bi.GRID[1])
        started = time.perf_counter()
        for ti, t in enumerate(bins):
            rows_t = np.flatnonzero(tbin == t)
            for f in range(nblk):
                ch = np.arange(f * bi.GRID[1], min((f + 1) * bi.GRID[1], nchan))
                nu_c = float(d["freqs"][ch].mean())
                # finest sub-blocks of the set's variants; a variant with
                # vsub sub-blocks evaluates the beam at the centre of the
                # (GRID[1] // vsub)-channel sub-block holding each fine one
                fine = bi.GRID[1] // nsub
                position = np.arange(len(ch))
                subidx = position // fine
                nfine = int(subidx.max()) + 1
                gamma = np.zeros((nvar, nfine, ncomp, 2, 2), complex)
                beta = np.zeros((nvar, nfine, ncomp, 2, 6))
                fac_nominal = None
                for v, (_name, rot, vsub) in enumerate(variants):
                    width = bi.GRID[1] // vsub
                    cache = {}
                    for sb in range(nfine):
                        coarse = (sb * fine) // width
                        if coarse not in cache:
                            nu = float(
                                d["freqs"][ch][position // width == coarse].mean()
                            )
                            cache[coarse] = bi.factors_at(
                                beam, sky["lm"], q_all[ti], nu, rot
                            )
                        fac = cache[coarse]
                        gamma[v, sb] = fac["gamma"]
                        beta[v, sb] = fac["beta"]
                    if v == 0:
                        fac_nominal = cache[0]
                floor_counts.append(int((~fac_nominal["kept"]).sum()))
                hsum = [None, None]
                nsamp = [0, 0]
                spec = bi.spectra(sky, d["freqs"][ch]).T  # (c, K)
                terms_bin = [] if native else None
                for start in range(0, len(rows_t), CHUNK_ROWS):
                    rows = rows_t[start : start + CHUNK_ROWS]
                    terms = (
                        bi.phase_terms(d["uvw"][rows], d["freqs"][ch], sky) * spec[None]
                    )
                    if native:
                        terms_bin.append(terms)
                    sel = np.ix_(rows, ch)
                    dd = {
                        "flag": d["flag"][sel],
                        "weight": d["weight"][sel],
                        "data": d["data"][sel],
                    }
                    for hand, c in HANDS:
                        e = eligible(dd, c)
                        if not e.any():
                            continue
                        rr, cc = np.nonzero(e)
                        sw = np.sqrt(dd["weight"][..., c][rr, cc].astype(float))
                        if taper is not None:
                            blen = np.hypot(*d["uvw"][rows][rr, :2].T)
                            scale = np.ones(len(rr))
                            for lo, hi, ratio in taper:
                                scale[(blen >= lo) & (blen < hi)] = ratio
                            sw = sw * scale
                        z = terms[rr, cc] * sw[:, None]
                        h = bi.block_normals(
                            d["a1"][rows][rr],
                            d["a2"][rows][rr],
                            nant,
                            z,
                            gamma[:, :, :, hand],
                            beta[:, :, :, hand],
                            subidx[cc],
                            slope=(
                                ((position - (len(ch) - 1) / 2) / len(ch))[cc]
                                if slope
                                else None
                            ),
                        )
                        hsum[hand] = h if hsum[hand] is None else hsum[hand] + h
                        nsamp[hand] += len(rr)
                for hand in range(2):
                    if hsum[hand] is not None:
                        survey.add(s, f, hand, nu_c, hsum[hand], nsamp[hand])
                if native:
                    tb = np.concatenate(terms_bin)
                    kap = {(0, h_): kappa_raw[(0, h_)] for h_ in range(2)}
                    rec = native_anchored(
                        d, sky, rows_t, ch, tb, fac_nominal, kap, nant
                    )
                    if rec is not None:
                        native_records.append(
                            {"time_bin": int(t), "block": f, "directions": rec}
                        )
            log(
                f"scan {s} time bin {ti + 1}/{len(bins)}",
                f"{time.perf_counter() - started:.1f} s",
            )
    return survey, native_records, pa, floor_counts


def anchored_summary(survey, labels):
    """Median and max over gain bins of the relative station step per unit."""
    nb = survey.nb
    out = [None] * len(labels)
    for (scan, hand), steps in survey.anchor.items():
        arr = np.array(steps)  # (blocks, nvar * nb)
        for v in range(survey.nvar):
            idx = survey.theta_index(scan, v)
            local = arr[:, v * nb : (v + 1) * nb]
            for col, j in enumerate(idx):
                vals = local[:, col]
                rec = out[j] or {"values": []}
                rec["values"].append(vals)
                out[j] = rec
    summary = []
    for j, label in enumerate(labels):
        vals = np.concatenate(out[j]["values"]) if out[j] else np.array([np.nan])
        unit = 0.01 if label["unit"] == "fraction" else 1.0
        summary.append(
            {"median": float(np.median(vals) * unit), "max": float(np.max(vals) * unit)}
        )
    return summary


def survey_set(
    name,
    out,
    pilot=None,
    track=None,
    field=None,
    beam_sampling="native",
    gain_slope=False,
    taper_json=None,
):
    """`beam_sampling` "product" (post hoc only) samples the array average at
    the 95 product channels (9.2 MHz, G0b-validated linear interpolation)
    instead of its 1,024 native channels. `taper_json` (post hoc only): the
    band ratios of `posthoc_model.py` (mean of the hands' raw ratios)."""
    taper = None
    if taper_json:
        bands = json.loads(Path(taper_json).read_text())["bands_m"]
        taper = [
            (
                b["band_m"][0],
                b["band_m"][1],
                0.5 * (b["hand0"]["raw_ratio"] + b["hand1"]["raw_ratio"]),
            )
            for b in bands
        ]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    stages = {}
    beam = beam_holography.HolographyBeam(
        HOLOGRAPHY, native_average=beam_sampling == "native"
    )
    grad = bi.HolographyGradient(beam, "array_average")
    record = {
        "beam_sampling": beam_sampling,
        "gain_slope_post_hoc": gain_slope,
        "taper_post_hoc": taper,
        "set": name,
        "protocol": "research/b1-2-identifiability.md",
        "git_head": git_head(),
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    native = name == "S1"
    if name in ("S1", "S2", "S1-posthoc"):
        d = load_luno("MAIN/MAIN_1", None if name == "S2" else [0, 1, 2, 3])
        sky = sky_from_sources(sky_lsm(), d["phase_dir"])
        scans = [d]
    elif name in ("S3", "S3-posthoc"):
        d = load_luno("MAIN/MAIN_2", None)
        sky = sky_point(S3_POINT["i0_jy"], S3_POINT["alpha"], S3_POINT["nu0_hz"])
        scans = [d]
    elif name in ("S4", "S4-posthoc"):
        d = load_eso_pilot(pilot)
        comps = np.load(Path(field) / "components.npz")
        sky = sky_components(comps["lm"], comps["flux"])
        scans = [d]
    elif name == "S5":
        scans = load_eso_track(track)
        comps = np.load(Path(field) / "components.npz")
        sky = sky_components(comps["lm"], comps["flux"])
    else:
        raise ValueError(name)
    if name == "S1":
        # as measured: the S1 run that triggered the convergence rule
        variants = (("nominal", 0.0, 1), ("sub16", 0.0, 2), ("rot90", math.pi / 2, 1))
    elif name == "S4":
        variants = VARIANTS_CHECKED
    elif name == "S1-posthoc":
        variants = VARIANTS_POSTHOC_S1
    elif name == "S3-posthoc":
        variants = (("sub16", 0.0, 2), ("sub1", 0.0, 32))
    elif name == "S4-posthoc":
        variants = (("sub16", 0.0, 2),)
    else:
        variants = VARIANTS_FINER
    record["verdict_variant"] = VERDICT_VARIANT
    stages["load"] = time.perf_counter() - started
    log("loaded", name, [len(s["a1"]) for s in scans], "components", len(sky["flux"]))
    # noise and amplitude scales
    mark = time.perf_counter()
    kappa, kappa_raw = {}, {}
    record["noise"] = []
    field_rec = (
        json.loads((Path(field) / "fieldmodel.json").read_text()) if field else None
    )
    for s, d in enumerate(scans):
        noise = noise_for(d)
        if name in ("S1", "S2", "S3", "S1-posthoc", "S3-posthoc"):
            amp = amplitude_scale_luno(d, sky)
            c = {h: amp[h]["c"] for h in range(2)}
        elif name in ("S4", "S4-posthoc"):
            # the round-2 gains of the field model, solved baselines only
            c = gain_scale(d, np.load(Path(field) / "round2.npz")["gains"])
            amp = {
                "from": "field model round 2 gains",
                "fieldmodel_json_c": field_rec["c"],
            }
        else:
            c, solve = scan_scale(d, sky)
            amp = {"from": "per-scan gains against the field model", "solve": solve}
        for h in range(2):
            kappa[(s, h)] = c[h] ** 2 / noise[h]["s2"]
            kappa_raw[(s, h)] = 1.0
        record["noise"].append(
            {
                "scan": s,
                "label": d["label"],
                "noise": noise,
                "amplitude": amp,
                "c": c,
                "kappa": [kappa[(s, 0)], kappa[(s, 1)]],
            }
        )
        log("noise", s, noise, c)
    stages["noise"] = time.perf_counter() - mark
    # survey
    mark = time.perf_counter()
    survey, native_records, pa, floors = run_survey(
        scans,
        sky,
        grad,
        variants,
        kappa,
        out,
        native and not gain_slope,
        gain_slope,
        taper,
    )
    stages["survey"] = time.perf_counter() - mark
    mark = time.perf_counter()
    nu0 = float(np.mean(np.concatenate([s["freqs"] for s in scans])))
    nant = len(scans[0]["positions"])
    info = survey.information(kappa, nu0)
    info_raw = survey.information(kappa_raw, nu0)
    labels = bi.direction_labels(
        nant, len(scans), len(variants), [v[0] for v in variants]
    )
    duration = float(sum(np.ptp(s["time"]) + 8.0 for s in scans))
    m = bi.measures_from(info, labels, nant, len(scans), len(variants), duration)
    m_raw = bi.measures_from(
        info_raw, labels, nant, len(scans), len(variants), duration
    )
    anchor = anchored_summary(survey, labels)
    for rec, rec_raw, anc in zip(
        m["directions"], m_raw["directions"], anchor, strict=True
    ):
        rec["sigma_primary_raw_weights"] = rec_raw["sigma_primary"]
        rec["anchored_relative_step_median"] = anc["median"]
        rec["anchored_relative_step_max"] = anc["max"]
    rows = bi.summarise(m["directions"], nant)
    stages["measures"] = time.perf_counter() - mark
    record.update(
        {
            "scans": [
                {
                    "label": s["label"],
                    "rows": len(s["a1"]),
                    "channels": len(s["freqs"]),
                    "freq_mhz": [
                        float(s["freqs"][0] / 1e6),
                        float(s["freqs"][-1] / 1e6),
                    ],
                    "span_s": float(np.ptp(s["time"])),
                    "receptor_angle": s.get("receptor_angle"),
                    "field": s["field"],
                }
                for s in scans
            ],
            "antennas": nant,
            "components": len(sky["flux"]),
            "component_flux_sum_at_ref": float(sky["flux"].sum()),
            "variants": [list(v) for v in variants],
            "parallactic_angle_deg_per_time_bin": pa,
            "components_below_ib_floor_per_block": {
                "median": float(np.median(floors)),
                "max": int(max(floors)),
            },
            "gain_bins": survey.blocks,
            "samples": survey.samples,
            "nu0_hz": nu0,
            "duration_s": duration,
            "directions": m["directions"],
            "verdict_rows": rows,
            "native_anchored": native_records if native else None,
            "stages_seconds": stages,
            "wall_seconds": time.perf_counter() - started,
            "peak_rss_mb": rusage.peak_rss_mb(),
        }
    )
    if native:
        recs = [r for b in native_records for r in b["directions"]]
        statuses = {}
        for r in recs:
            statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1
        diffs = [
            r["relative_difference_diagonal"]
            for r in recs
            if "relative_difference_diagonal" in r
        ]
        record["native_anchored_summary"] = {
            "calls": len(recs),
            "guard_pass": int(sum(r["guard_pass"] for r in recs)),
            "status_counts": statuses,
            "max_relative_difference_diagonal": float(max(diffs)) if diffs else None,
            "tolerance": 1e-6,
            "pass": bool(diffs) and max(diffs) <= 1e-6,
        }
        log("native", record["native_anchored_summary"])
    write_json(out / "survey.json", record)
    any_pass = any(r["constrainable"] for r in rows if r["variant"] == VERDICT_VARIANT)
    log(
        "done",
        name,
        "any constrainable (nominal):",
        any_pass,
        f"{record['wall_seconds']:.0f} s",
    )
    for r in rows:
        if r["variant"] == VERDICT_VARIANT:
            log(json.dumps(r, default=float))
    return record


# --------------------------------------------------------------------------
# Archive


def archive(out_json, verdict_runs, posthoc_runs=(), trigger_runs=(), fieldmodel=None):
    """The committed archive. Entries are keyed by run directory; the
    verdict (`closes_null`) is computed from `verdict_runs` only (one frozen
    run per set); `trigger_runs` (the run that triggered the convergence
    rule) and `posthoc_runs` are recorded and labelled, never counted."""
    payload = {
        "protocol": "research/b1-2-identifiability.md",
        "note": "derived numbers only; holography beam CC BY-NC 4.0 (de Villiers 2023, "
        "doi:10.48479/wdb0-h061); ESO137 CC BY 4.0 (Ramatsoku et al. 2020)",
        "verdict_variant": VERDICT_VARIANT,
        "runs": {},
    }
    roles = [(r, "verdict") for r in verdict_runs]
    roles += [(r, "trigger") for r in trigger_runs]
    roles += [(r, "post hoc") for r in posthoc_runs]
    if fieldmodel:
        roles.append((fieldmodel, "field model"))
    for run, role in roles:
        run = Path(run)
        if (run / "fieldmodel.json").exists():
            fm = json.loads((run / "fieldmodel.json").read_text())
            payload["field_model"] = {
                k: fm[k]
                for k in (
                    "orientation_check",
                    "lobes_at_lowest_frequency",
                    "model_sign_check_chi2",
                    "components_kept",
                    "flux_kept",
                    "flux_kept_fraction",
                    "radius_max_deg",
                    "flux_by_radius",
                    "brightest_jy",
                    "e0",
                    "c",
                )
                if k in fm
            }
            payload["field_model"]["rounds"] = [
                {
                    k: r[k]
                    for k in (
                        "round",
                        "phase_only",
                        "sigma",
                        "dirty_peak",
                        "dirty_robust_sigma",
                        "residual_robust_sigma",
                        "clean_iterations",
                        "clean_components",
                        "clean_flux",
                        "positive_cells",
                    )
                }
                for r in fm["rounds"]
            ]
            continue
        rec = json.loads((run / "survey.json").read_text())

        def rounded(x):
            if isinstance(x, float):
                return float(f"{x:.6g}")
            if isinstance(x, dict):
                return {k: rounded(v) for k, v in x.items()}
            if isinstance(x, list):
                return [rounded(v) for v in x]
            return x

        common = [
            {
                k: d[k]
                for k in (
                    "variant",
                    "direction",
                    "unit",
                    "sigma_primary",
                    "rho_primary",
                    "sigma_strict",
                    "rho_strict",
                    "rho_gains_only",
                    "rho_sky_only_primary",
                    "sigma_family_marginal",
                    "sigma_primary_raw_weights",
                    "sigma_raw_no_nuisance",
                    "forecast_sigma_1h",
                    "anchored_relative_step_median",
                    "anchored_relative_step_max",
                    "constrainable",
                    "labels",
                )
            }
            for d in rec["directions"]
            if d["family"] == "common"
        ]
        posthoc = (
            rec.get("beam_sampling", "native") != "native"
            or rec.get("gain_slope_post_hoc", False)
            or rec.get("taper_post_hoc") is not None
            or rec["set"].endswith("posthoc")
        )
        if role == "verdict" and posthoc:
            raise ValueError(f"{run} is a post-hoc run and cannot carry the verdict")
        payload["runs"][run.name] = rounded(
            {
                "set": rec["set"],
                "role": role,
                "post_hoc": posthoc or role == "post hoc",
                "beam_sampling": rec.get("beam_sampling", "native"),
                "gain_slope": rec.get("gain_slope_post_hoc", False),
                "variants": rec["variants"],
                "scans": rec["scans"],
                "antennas": rec["antennas"],
                "components": rec["components"],
                "noise": rec["noise"],
                "duration_s": rec["duration_s"],
                "gain_bins": rec["gain_bins"],
                "samples": rec["samples"],
                "parallactic_angle_range_deg": [
                    [min(p), max(p)] for p in rec["parallactic_angle_deg_per_time_bin"]
                ],
                "components_below_ib_floor_per_block": rec[
                    "components_below_ib_floor_per_block"
                ],
                "verdict_rows": rec["verdict_rows"],
                "common_directions": common,
                "native_anchored_summary": rec.get("native_anchored_summary"),
                "wall_seconds": rec["wall_seconds"],
                "peak_rss_mb": rec["peak_rss_mb"],
                "run": str(run.relative_to(ROOT))
                if run.is_relative_to(ROOT)
                else str(run),
            }
        )
    verdict = [r for r in payload["runs"].values() if r["role"] == "verdict"]
    sets = [r["set"] for r in verdict]
    if len(sets) != len(set(sets)):
        raise ValueError("one verdict run per set")
    payload["verdict_sets"] = sorted(sets)
    payload["constrainable"] = [
        {
            "set": r["set"],
            **{k: row[k] for k in ("direction", "unit") if k in row},
            "sigma": row.get("sigma_primary", row.get("sigma_primary_min")),
            "rho": row.get("rho_primary", row.get("rho_primary_max")),
            "labels": row.get("labels", []),
        }
        for r in verdict
        for row in r["verdict_rows"]
        if row["variant"] == VERDICT_VARIANT and row["constrainable"]
    ]
    payload["closes_null"] = not payload["constrainable"]
    write_json(out_json, payload)
    log("archive", out_json, "closes null:", payload["closes_null"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fieldmodel")
    p.add_argument("out")
    p.add_argument("--pilot", required=True)
    p = sub.add_parser("survey")
    p.add_argument(
        "set",
        choices=(
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "S1-posthoc",
            "S3-posthoc",
            "S4-posthoc",
        ),
    )
    p.add_argument("out")
    p.add_argument("--pilot")
    p.add_argument("--track")
    p.add_argument("--field")
    p.add_argument("--beam-sampling", choices=("native", "product"), default="native")
    p.add_argument("--gain-slope", action="store_true", help="post hoc only")
    p.add_argument("--taper-json", help="post hoc only")
    p = sub.add_parser("archive")
    p.add_argument("out_json")
    p.add_argument("--verdict", nargs="+", required=True)
    p.add_argument("--posthoc", nargs="*", default=())
    p.add_argument("--trigger", nargs="*", default=())
    p.add_argument("--fieldmodel")
    args = parser.parse_args(argv)
    if args.command == "fieldmodel":
        beam = beam_holography.HolographyBeam(HOLOGRAPHY)
        field_model(args.pilot, args.out, beam)
    elif args.command == "survey":
        survey_set(
            args.set,
            args.out,
            args.pilot,
            args.track,
            args.field,
            args.beam_sampling,
            args.gain_slope,
            args.taper_json,
        )
    else:
        archive(
            args.out_json, args.verdict, args.posthoc, args.trigger, args.fieldmodel
        )


if __name__ == "__main__":
    sys.exit(main())
