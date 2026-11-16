"""Task TS-P1 protocol 2: gates T4 (blind false alarms) and T5 (GPU against
CPU) (research/ts-p1.md 13.2 and 13.3).

Usage (worktree venv; T5 in the gpu-build venv):
    python examples/ts_p1_t4t5.py t4 MS LC_DIR OUT_JSON
    python examples/ts_p1_t4t5.py t5 MS OUT_JSON [--field 3 --size 2048 --scale 2]

t4 reads the candidates of a `rang-core lightcurve --candidates 5` run on the
noise-only simulation and compares the positive count at 5 sigma with the
expected Euler characteristic of a Gaussian field whose correlation is the
normalised PSF of interval 0 (made here from unit visibilities and the MS's
own weights), and checks that no positive candidate reaches 7 sigma.

t5 makes the snapshots of intervals 0, 10, ..., 440 with the w-stacking
gridder on the CPU and on the GPU (f64) and compares them; it also reports
the w-stacking against the exact wgridder.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_model, core_ms
from rang import lightcurve as lc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ts_p1_measure as measure

T5_BOUND = 1e-6


def interval_rows(ms, field):
    rows = core_model.selected_rows(ms, field)
    with core_ms.open_table(ms) as t:
        times = t.getcol_rows("TIME", rows)
    unique = np.unique(times)
    return rows, times, unique


def fit_lambda(psf, size):
    """Lambda of ln rho = -x^T Lambda x / 2 over the main lobe (rho > 0.5)
    of the PSF centred at (size/2, size/2), pixel units."""
    c = size // 2
    half = 16
    patch = psf[c - half : c + half + 1, c - half : c + half + 1]
    yy, xx = np.mgrid[-half : half + 1, -half : half + 1]
    # The connected main lobe: pixels above 0.5 reachable from the centre.
    keep = np.zeros_like(patch, bool)
    keep[half, half] = True
    above = patch > 0.5
    for _ in range(2 * half):
        grown = keep.copy()
        grown[1:] |= keep[:-1]
        grown[:-1] |= keep[1:]
        grown[:, 1:] |= keep[:, :-1]
        grown[:, :-1] |= keep[:, 1:]
        grown &= above
        if np.array_equal(grown, keep):
            break
        keep = grown
    x, y, r = xx[keep], yy[keep], np.log(patch[keep])
    # -2 ln rho = a x^2 + 2 b x y + c y^2
    design = np.stack([x * x, 2 * x * y, y * y], axis=1)
    (a, b, cc), *_ = np.linalg.lstsq(design, -2.0 * r, rcond=None)
    return np.array([[a, b], [b, cc]]), int(keep.sum())


def expected_ec(u, area, perimeter, lam):
    det = float(np.linalg.det(lam))
    tail = 0.5 * math.erfc(u / math.sqrt(2.0))
    e2 = area * math.sqrt(det) / (2 * math.pi) ** 1.5 * u * math.exp(-u * u / 2)
    e1 = perimeter / 2 * det**0.25 / (2 * math.pi) * math.exp(-u * u / 2)
    return e2 + e1 + tail


def peak_lambda(psf, size):
    """Amendment 15.2: minus the Hessian of the PSF at its peak, by
    second-order central differences over one pixel."""
    c = size // 2
    dxx = -(psf[c, c + 1] + psf[c, c - 1] - 2.0)
    dyy = -(psf[c + 1, c] + psf[c - 1, c] - 2.0)
    dxy = -(psf[c + 1, c + 1] - psf[c + 1, c - 1] - psf[c - 1, c + 1]
            + psf[c - 1, c - 1]) / 4.0  # fmt: skip
    return np.array([[dxx, dxy], [dxy, dyy]])


def expected_grid(u, area, perimeter, lam, n=41):
    """Amendment 15.2: the continuous EC expectation at u / rho(delta),
    averaged over the pixel offset delta of the highest pixel, uniform in
    [-1/2, 1/2]^2 (n x n points)."""
    d = (np.arange(n) + 0.5) / n - 0.5
    total = 0.0
    for dx in d:
        for dy in d:
            q = lam[0, 0] * dx * dx + 2 * lam[0, 1] * dx * dy + lam[1, 1] * dy * dy
            total += expected_ec(u / math.exp(-0.5 * q), area, perimeter, lam)
    return total / (n * n)


def t4(ms, lc_dir, out, psf_ms=None):
    started = time.perf_counter()
    res_lc = json.loads((Path(lc_dir) / "lightcurve.json").read_text(encoding="utf-8"))
    s = res_lc["settings"]
    size, scale = s["size"], s["scale_arcsec"]
    field = res_lc["field"]["id"]
    ms = psf_ms or ms  # the PSF needs only UVW and weights (15.2)
    rows, times, unique = interval_rows(ms, field)
    freq, _, _ = core_model.band(ms, field)
    with core_ms.open_table(ms) as t:
        sel = np.sort(rows[times == unique[0]])
        uvw, _, weight = measure.read_interval(t, sel)
    ones = np.ones(weight.shape, np.complex64)
    psf = lc.snapshot(uvw, freq, ones, weight, size, scale, s["epsilon"])
    psf = psf / psf[size // 2, size // 2]
    lam, npix = fit_lambda(psf, size)
    n = res_lc["intervals"]
    area, perimeter = float(size * size), float(4 * size)
    e5 = n * expected_ec(5.0, area, perimeter, lam)
    e7 = n * expected_ec(7.0, area, perimeter, lam)
    cands = res_lc["candidates"]
    pos5 = sum(1 for c in cands if c["sign"] > 0 and c["snr"] >= 5.0)
    neg5 = sum(1 for c in cands if c["sign"] < 0 and -c["snr"] >= 5.0)
    pos7 = sum(1 for c in cands if c["sign"] > 0 and c["snr"] >= 7.0)
    neg7 = sum(1 for c in cands if c["sign"] < 0 and -c["snr"] >= 7.0)
    fwhm = 2 * math.sqrt(2 * math.log(2)) / np.sqrt(np.linalg.eigvalsh(lam))
    lam_peak = peak_lambda(psf, size)
    a5 = n * expected_grid(5.0, area, perimeter, lam_peak)
    a7 = n * expected_grid(7.0, area, perimeter, lam_peak)
    res = {
        "case": res_lc["ms"],
        "intervals": n,
        "lambda_pixels": lam.tolist(),
        "lobe_pixels_fitted": npix,
        "correlation_fwhm_arcsec": (fwhm * scale).tolist(),
        "expected_5": e5,
        "expected_7": e7,
        "positive_5": pos5,
        "negative_5": neg5,
        "positive_7": pos7,
        "negative_7": neg7,
        "deviation_5_in_poisson_sigma": (pos5 - e5) / math.sqrt(e5),
        "amended_15_2": {
            "lambda_peak_pixels": lam_peak.tolist(),
            "expected_5": a5,
            "expected_7": a7,
            "deviation_5_in_poisson_sigma": (pos5 - a5) / math.sqrt(a5),
            "pass": bool(pos7 == 0 and abs(pos5 - a5) <= 3 * math.sqrt(a5)),
        },
        "pass_7": pos7 == 0,
        "pass_5": abs(pos5 - e5) <= 3 * math.sqrt(e5),
        "seconds": time.perf_counter() - started,
    }
    res["pass"] = bool(res["pass_7"] and res["pass_5"])
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("expected_5", "positive_5", "negative_5",
                                         "positive_7", "pass")}))  # fmt: skip
    print(json.dumps({"amended_15_2": res["amended_15_2"]}))
    return 0 if res["pass"] else 1


def t5(ms, out, field, size, scale):
    started = time.perf_counter()
    rows, times, unique = interval_rows(ms, field)
    freq, _, _ = core_model.band(ms, field)
    column, model, weights = lc._columns(ms, None, "MODEL_DATA")
    records = []
    with core_ms.open_table(ms) as t:
        for k in range(0, len(unique), 10):
            sel = np.sort(rows[times == unique[k]])
            uvw, vis, weight = lc._residual(t, sel, column, model, weights, len(freq))
            t0 = time.perf_counter()
            cpu = lc.snapshot(
                uvw, freq, vis, weight, size, scale, 1e-6, "wstack", "cpu"
            )
            t1 = time.perf_counter()
            gpu = lc.snapshot(
                uvw, freq, vis, weight, size, scale, 1e-6, "wstack", "gpu"
            )
            t2 = time.perf_counter()
            exact = lc.snapshot(uvw, freq, vis, weight, size, scale, 1e-6)
            peak = float(np.max(np.abs(cpu)))
            records.append(
                {
                    "interval": k,
                    "gpu_vs_cpu": float(np.max(np.abs(gpu - cpu)) / peak),
                    "wstack_vs_wgrid": float(
                        np.max(np.abs(cpu - exact)) / np.max(np.abs(exact))
                    ),
                    "cpu_s": t1 - t0,
                    "gpu_s": t2 - t1,
                }
            )
            print(json.dumps(records[-1]), flush=True)
    worst = max(r["gpu_vs_cpu"] for r in records)
    res = {
        "case": "tsp1-held2",
        "column": column,
        "intervals": [r["interval"] for r in records],
        "max_gpu_vs_cpu": worst,
        "max_wstack_vs_wgrid": max(r["wstack_vs_wgrid"] for r in records),
        "median_cpu_s": float(np.median([r["cpu_s"] for r in records])),
        "median_gpu_s": float(np.median([r["gpu_s"] for r in records])),
        "records": records,
        "pass": bool(worst <= T5_BOUND),
        "seconds": time.perf_counter() - started,
    }
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("max_gpu_vs_cpu", "max_wstack_vs_wgrid",
                                         "pass")}))  # fmt: skip
    return 0 if res["pass"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="gate", required=True)
    a = sub.add_parser("t4")
    a.add_argument("ms")
    a.add_argument("lc_dir")
    a.add_argument("out")
    a.add_argument("--psf-ms", help="take the PSF from this MS (same UVW, weights)")
    b = sub.add_parser("t5")
    b.add_argument("ms")
    b.add_argument("out")
    b.add_argument("--field", type=int, default=3)
    b.add_argument("--size", type=int, default=2048)
    b.add_argument("--scale", type=float, default=2.0)
    args = p.parse_args(argv)
    if args.gate == "t4":
        return t4(args.ms, args.lc_dir, args.out, args.psf_ms)
    return t5(args.ms, args.out, args.field, args.size, args.scale)


if __name__ == "__main__":
    sys.exit(main())
