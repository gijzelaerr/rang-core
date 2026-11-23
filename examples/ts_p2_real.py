"""Task TS-P2: the real track on E2-A's field (research/ts-p2.md 4.2 and 5).

Usage (worktree venv):
    python examples/ts_p2_real.py inject MS MFS_IMAGE TRUTH_JSON
    python examples/ts_p2_real.py score-p1 MS TRUTH_JSON LC_DIR WSCLEAN_DIR OUT_JSON
    python examples/ts_p2_real.py t4 LC_DIR OUT_JSON

`inject` (4.2, "Injections"): on `scan10-512.ms` (DATA = E2-A's averaged
final CORRECTED_DATA, MODEL_DATA = E2-A's final model predicted), the flux
unit u = the median sigma_meas of intervals 0-9 of DATA - MODEL_DATA (the
product's own snapshot, 2048^2 at 2 arcsec), then the layout from seed
`tsp2-real` by ts-p2.md 4.1's held-out rule with radii 0.05-0.25 deg on the
2 arcsec grid, a position angle redrawn while E2-A's final MFS image has a
pixel above 10 x its robust rms within 30 arcsec; then INJECTED_DATA = DATA
+ the injected points (XX and YY), and RESIDUAL_DATA = INJECTED_DATA -
MODEL_DATA in complex64 (for WSClean only). Writes the truth JSON (the keys
ts_p2_measure.py reads).

`score-p1`: P1's T1, T2c (and their FLAG_ROW-ignored readings) on the real
track with sigma_meas, from ts_p1_measure.py's comparison functions.
`t4`: candidate counts at 5 and 7 sigma_meas, positive and negative.
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
from rang import core_model, core_ms, core_writeback
from rang import lightcurve as lc
from rang import simtruth as st

HERE = Path(__file__).parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p1 = _load("ts_p1_sim")
p2 = _load("ts_p2_sim")
p1m = _load("ts_p1_measure")

CASE = "tsp2-real"
FIELD = 0  # ESO137-001 is the only field after the split
RADII_DEG = (0.05, 0.15, 0.25, 0.15, 0.2, 0.1)
SCALE_ARCSEC, SIZE = 2.0, 2048
AVOID_ARCSEC, AVOID_RMS = 30.0, 10.0
UNIT_INTERVALS = 10


class _Design:
    def __init__(self, dt):
        self.seeds = dict(st.SEEDS[CASE])
        self.dt = dt


def _rows_by_time(ms):
    rows = core_model.selected_rows(ms, FIELD)
    with core_ms.open_table(ms) as t:
        times = t.getcol_rows("TIME", rows)
    return rows, times


def flux_unit(ms):
    """Median sigma_meas of intervals 0-9 of DATA - MODEL_DATA."""
    freq, _, _ = core_model.band(ms, FIELD)
    rows, times = _rows_by_time(ms)
    out = []
    with core_ms.open_table(ms) as t:
        for when in np.unique(times)[:UNIT_INTERVALS]:
            sel = np.sort(rows[times == when])
            uvw, vis, w = lc._residual(
                t, sel, "DATA", "MODEL_DATA", "WEIGHT_SPECTRUM", len(freq)
            )
            image = lc.snapshot(uvw, freq, vis, w, SIZE, SCALE_ARCSEC)
            out.append(lc.robust_sigma(image))
    return float(np.median(out)), out


def avoid_mask(mfs_image):
    """(wcs, image, threshold) of E2-A's final MFS image."""
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(mfs_image) as h:
        image = np.asarray(h[0].data[0, 0], np.float64)
        wcs = WCS(h[0].header).celestial
        step = abs(float(h[0].header["CDELT1"])) * 3600.0
    return wcs, image, AVOID_RMS * lc.robust_sigma(image), step


def near_bright(ra, dec, mask):
    wcs, image, thr, step = mask
    x, y = wcs.world_to_pixel_values(ra, dec)
    r = math.ceil(AVOID_ARCSEC / step)
    x0, y0 = round(float(x)), round(float(y))
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    inside = (xx**2 + yy**2) * step**2 <= AVOID_ARCSEC**2
    cut = image[y0 - r : y0 + r + 1, x0 - r : x0 + r + 1]
    return bool(np.any(cut[inside] > thr))


def layout(d, ntime, centre, mask):
    """ts-p2.md 4.1's held-out rule with the real track's radii and the
    redraw rule of 4.2; the spectra drawn after, from the same seed."""
    rng = np.random.default_rng(d.seeds["layout"])
    step = SCALE_ARCSEC * st.ARCSEC
    out, redraws = {}, {}
    for role, radius in zip(p2.ROLES, RADII_DEG, strict=True):
        redraws[role] = 0
        while True:
            angle = rng.uniform(0.0, 2 * math.pi)
            r = radius * st.DEG / step
            px = (round(r * math.cos(angle)), round(r * math.sin(angle)))
            ra, dec = st.radec(-px[0] * step, px[1] * step, *centre)
            if not near_bright(math.degrees(ra), math.degrees(dec), mask):
                break
            redraws[role] += 1
        out[role] = {"pixel": px}

    def amp(lo, hi):
        return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))

    first_d = float(rng.integers(0, int(p1.PERIOD_D)))
    out["D"]["periodic"] = {"first_s": first_d, "amplitude": amp(7.0, 50.0)}
    out["E"]["variable"] = {"mean": amp(5.0, 20.0)}
    busy = set()
    for k in range(int(ntime * d.dt // p1.PERIOD_D) + 1):
        s0 = first_d + k * p1.PERIOD_D
        busy |= set(range(int(s0 // d.dt), int((s0 + p1.LENGTH_D) // d.dt) + 1))
    for role, lengths in (("A", (1, 1)), ("B", (2,)), ("C", (8,))):
        pulses = []
        for n in lengths:
            while True:
                start = int(rng.integers(10, ntime - 10 - n))
                span = set(range(start, start + n))
                if not span & busy:
                    break
            busy |= span
            pulses.append((start, n, amp(7.0, 50.0)))
        out[role]["pulses"] = pulses
    spectra = {
        "A": {"kind": "powerlaw", "alpha": float(rng.uniform(-2.0, 0.0))},
        "B": {
            "kind": "gaussian",
            "centre_hz": float(rng.uniform(1.0e9, 1.5e9)),
            "fwhm_hz": 200e6,
        },
        "C": {"kind": "scintillation", "phase": float(rng.uniform(0.0, 2 * math.pi))},
        "D": {"kind": "flat"},
        "E": {"kind": "powerlaw", "alpha": 1.0},
        "F": {"kind": "flat"},
    }
    return out, spectra, redraws


def inject(ms, mfs_image, truth_path):
    started = time.perf_counter()
    ms = Path(ms)
    freq, _, centre = core_model.band(ms, FIELD)
    with core_ms.open_table(ms) as t:
        times_all = t.getcol("TIME")
        interval = float(np.median(t.getcol("INTERVAL")))
        names = t.colnames()
    for col in ("INJECTED_DATA", "RESIDUAL_DATA"):
        if col in names:
            raise SystemExit(f"{ms} already has {col}")
    unique = np.unique(times_all)
    ntime = len(unique)
    unit, unit_sigmas = flux_unit(ms)
    d = _Design(interval)
    mask = avoid_mask(mfs_image)
    lay, spectra, redraws = layout(d, ntime, centre, mask)
    step = SCALE_ARCSEC * st.ARCSEC
    srcs = []
    for role in p2.ROLES:
        dx, dy = lay[role]["pixel"]
        east, north = -dx * step, dy * step
        ra, dec = st.radec(east, north, *centre)
        srcs.append({"name": role, "pixel": [dx, dy], "l": east, "m": north,
                     "ra_deg": math.degrees(ra), "dec_deg": math.degrees(dec)})  # fmt: skip
    amp = p1.truth_flux(lay, d, ntime, unit)  # (ntime, nsrc), Jy
    spec = np.array([p2.spectrum(spectra[r], freq) for r in p2.ROLES])
    points = p1.unit_points(srcs)
    arrays = [st._component_arrays([p]) for p in points]
    with core_writeback.WriteBack(
        ms, flag_backup="tsp2_inject", stage="tsp2-inject"
    ) as w:
        w.ensure_column("INJECTED_DATA", init="data")
        w.ensure_column("RESIDUAL_DATA", init="data")
        for start, n in w.chunks():
            data = np.asarray(w.read("DATA", start, n))
            model = np.asarray(w.read("MODEL_DATA", start, n))
            uvw = np.asarray(w.read("UVW", start, n), np.float64)
            tix = np.searchsorted(unique, np.asarray(w.read("TIME", start, n)))
            stokes = np.zeros(data.shape[:2], np.complex128)
            for s, arr in enumerate(arrays):
                a = amp[tix, s]
                on = np.flatnonzero(a)
                if on.size:
                    v = st._predict(uvw[on], freq, arr)
                    stokes[on] += v * a[on, None] * spec[s][None, :]
            out = data.astype(np.complex128)
            out[..., 0] += stokes
            out[..., 3] += stokes
            injected = out.astype(np.complex64)
            w.write("INJECTED_DATA", start, injected)
            w.write("RESIDUAL_DATA", start, (injected - model).astype(np.complex64))
    truth = {
        "case": CASE,
        "field_id": FIELD,
        "scale_arcsec": SCALE_ARCSEC,
        "unit_jy": unit,
        "unit_sigma_meas_jy": unit_sigmas,
        "groups": None,
        "nchan": len(freq),
        "freq_hz": [float(f) for f in freq],
        "time_mjd_s": unique.tolist(),
        "interval_s": interval,
        "layout": lay,
        "redraws": redraws,
        "avoid": {
            "arcsec": AVOID_ARCSEC,
            "rms_factor": AVOID_RMS,
            "threshold_jy": mask[2],
            "image": str(mfs_image),
        },
        "spectra": spectra,
        "spectrum": spec.tolist(),
        "sources": srcs,
        "amplitude_jy": amp.tolist(),
        "seconds": time.perf_counter() - started,
        "git": __import__("rang.simtruth_ms", fromlist=["git_facts"]).git_facts(),
    }
    st.write_json(Path(truth_path), truth)
    print(json.dumps({"unit_jy": unit, "redraws": redraws, "ntime": ntime}))
    return truth


def score_p1(ms, truth_path, lc_dir, wsclean, out):
    lcj = json.loads((Path(lc_dir) / "lightcurve.json").read_text(encoding="utf-8"))
    n = lcj["intervals"]
    flux = np.array(lcj["flux_jy"], np.float64)
    sig = np.array(lcj["sigma_meas_jy"], np.float64)
    res = p1m.compare_wsclean(wsclean, ms, lc_dir, lcj, flux, sig, n)
    with core_ms.open_table(ms) as t:
        rows = core_model.selected_rows(ms, FIELD)
        fr = np.asarray(t.getcol_rows("FLAG_ROW", rows), bool)
    res["flag_row_rows"] = int(fr.sum())
    if fr.any():
        res.update(p1m.compare_wsclean_flag_row_ignored(wsclean, ms, lcj, sig, n))
    res["outside_grid_total"] = lcj.get("outside_grid_total")
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v.get("pass") for k, v in res.items() if isinstance(v, dict)}))


def t4(lc_dir, out):
    counts = {}
    with open(Path(lc_dir) / "candidates.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for u in (5.0, 7.0):
        for sign in (1, -1):
            counts[f"{'pos' if sign > 0 else 'neg'}_{u:g}sigma"] = sum(
                1
                for r in rows
                if int(r["sign"]) == sign and float(r["snr"]) * sign >= u
            )
    Path(out).write_text(json.dumps(counts, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(counts))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inject")
    a.add_argument("ms")
    a.add_argument("mfs_image")
    a.add_argument("truth")
    b = sub.add_parser("score-p1")
    for k in ("ms", "truth", "lc_dir", "wsclean", "out"):
        b.add_argument(k)
    c = sub.add_parser("t4")
    c.add_argument("lc_dir")
    c.add_argument("out")
    args = p.parse_args(argv)
    if args.cmd == "inject":
        inject(args.ms, args.mfs_image, args.truth)
    elif args.cmd == "score-p1":
        score_p1(args.ms, args.truth, args.lc_dir, args.wsclean, args.out)
    else:
        t4(args.lc_dir, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
