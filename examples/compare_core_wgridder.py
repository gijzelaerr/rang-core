"""Comparators of big-plan task DF1, the exact gridder (research/df1-wgridder.md).

    python examples/compare_core_wgridder.py item0 SLICE_DIR OUT.json
    python examples/compare_core_wgridder.py gates OUT_DIR SYNTH_DIR SLICE_DIR DUCC_SYNTH DUCC_SLICE
    python examples/compare_core_wgridder.py threads OUT.json SYNTH_DIR SLICE_DIR [--threads 1,2,4,8,16]

`item0` attributes the difference between the core's w-stacking image
(`core_grid.invert`, WSClean 3.6-1's gridder) and the direct Fourier
transform on the LUNO slice. The w-stacking image is mapped to the DFT's
pixel grid by the map derived from `grid.rs` (`project`,
`initialize_sqrt_lm`): output pixel `(X, Y)` (FITS order, array `[Y, X]`)
holds `l = (X - W/2) dx`, `m = (H/2 - Y) dy` with the w term of the opposite
sign, i.e. DFT pixel `(ix, iy) = (X, H - Y)` for uvw with w negated. The map
is checked on an asymmetric off-centre point source at large w, then held
fixed (no orientation search). The error is then swept against ducc0 at
epsilon 1e-9 (validated against the DFT on the same slice to 2e-10) over
padding, kernel size, w-layers and w forced to zero, and the aliasing of the
w-stacking grid is predicted from the kernel's Fourier transform and the
true dirty image at the alias positions (ducc0 with `center_x/center_y`
shifts).

`gates` runs the core's new gridder (`core_wgridder`) against the DFT and
ducc0 on every case and epsilon (criteria 1-5 of the protocol) and writes
`gates.json`; `threads` hashes the core's outputs at several thread counts
in fresh processes (criterion 4).
"""

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "examples"))

import oracle_ducc0 as oracle

C_LIGHT = oracle.C_LIGHT
N = oracle.SLICE_NPIX
CELL = oracle.SLICE_CELL
CELL_ARCSEC = 8.0


def maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


# ------------------------------------------------------------------- item 0


def core_to_dft(img):
    """Map a core w-stacking image `[Y, X]` to the DFT layout `[ix, iy]`:
    `(ix, iy) = (X, H - Y)`; row Y = 0 (m = H/2 dy) lies outside the DFT
    grid and is returned as NaN."""
    h, w = img.shape
    out = np.full((w, h), np.nan)
    # out[X, H - Y] = img[Y, X] for Y = 1..H-1
    out[:, h - np.arange(1, h)] = img[1:, :].T
    return out


def masked_metrics(test, ref, inner=False):
    ok = np.isfinite(test)
    if inner:
        sl = np.zeros_like(ok)
        n = ok.shape[0]
        sl[n // 4 : 3 * n // 4, n // 4 : 3 * n // 4] = True
        ok &= sl
    err = np.abs(test - ref)[ok]
    peak = np.abs(ref).max()
    return {
        "linf_rel_peak": float(err.max() / peak),
        "rms_rel_peak": float(np.sqrt(np.mean(err**2)) / peak),
    }


def run_core(uvw, freq, vis, wgt, padding=1.2, kernel=7, layers=64):
    from rangtoy import core_grid

    t0 = time.perf_counter()
    r = core_grid.invert(
        uvw,
        freq,
        vis,
        wgt,
        np.ones_like(wgt),
        N,
        N,
        CELL_ARCSEC,
        w_layers=layers,
        kernel_size=kernel,
        padding=padding,
    )
    r["wall_s"] = time.perf_counter() - t0
    return r


def ducc_truth(uvw, freq, vis, wgt, eps=1e-9, wgrid=True, cx=0.0, cy=0.0, npix=N):
    import ducc0

    return ducc0.wgridder.vis2dirty(
        uvw=uvw,
        freq=freq,
        vis=vis.astype(np.complex128),
        wgt=wgt.astype(np.float64),
        npix_x=npix,
        npix_y=npix,
        pixsize_x=CELL,
        pixsize_y=CELL,
        epsilon=eps,
        do_wgridding=wgrid,
        nthreads=1,
        flip_w=True,
        divide_by_n=False,
        center_x=cx,
        center_y=cy,
    )


def kb_transform(kernel_size, oversampling, positions, period):
    """Fourier transform of WSClean's oversampled 1-D kernel at image
    positions `positions` (pixels of a padded grid of `period` cells), as
    the gridder's taper: sum_i k_i cos(2 pi s_i t / period), s_i in cells."""
    from rangtoy import core_grid

    k = core_grid.kernel(kernel_size, oversampling)
    n = k.size
    s = (np.arange(n) - n // 2) / oversampling
    t = np.asarray(positions, float)
    return np.cos(2 * np.pi * np.outer(t, s) / period) @ k


def cmd_item0(args):
    t_start = time.time()
    d = Path(args.slice)
    uvw, freq, vis, wgt = oracle.slice_arrays(d)
    dft = np.load(d / "dft_dirty.npy")
    dft_psf = np.load(d / "dft_psf.npy")
    dft_n = dft / dft_psf[N // 2, N // 2]
    psf_n = dft_psf / dft_psf[N // 2, N // 2]
    res = {"slice": str(d)}

    # (a) Map check: asymmetric off-centre point at large w (w scaled x100).
    lam = freq[None, :] / C_LIGHT
    l0, m0 = 60 * CELL, 25 * CELL
    n0m1 = np.sqrt(1 - l0**2 - m0**2) - 1
    big = uvw * [1.0, 1.0, 100.0]
    u, v, w = (big[:, i, None] * lam for i in range(3))
    pt = np.exp(-2j * np.pi * (u * l0 + v * m0 + w * n0m1)).astype(np.complex64)
    pt = np.where(wgt > 0, pt, 0).astype(np.complex64)
    mapcheck = {}
    for label, sw in (("w as given", 1.0), ("w negated", -1.0)):
        r = run_core(big * [1.0, 1.0, sw], freq, pt, wgt)
        img = core_to_dft(r["dirty"])
        ix, iy = np.unravel_index(np.nanargmax(img), img.shape)
        mapcheck[label] = {
            "peak": float(np.nanmax(img)),
            "at_ix_iy": [int(ix), int(iy)],
            "expected_ix_iy": [N // 2 + 60, N // 2 + 25],
        }
    res["map_check_point_60_25_w_x100"] = mapcheck

    # (b) Core against the DFT with the fixed map, default and the study's settings.
    sweep_dft = {}
    for pad, kern, layers in ((1.2, 7, 64), (2.0, 7, 64), (2.0, 15, 512)):
        r = run_core(uvw * [1.0, 1.0, -1.0], freq, vis, wgt, pad, kern, layers)
        cd, cp = core_to_dft(r["dirty"]), core_to_dft(r["psf"])
        sweep_dft[f"pad{pad}_k{kern}_L{layers}"] = {
            "dirty": masked_metrics(cd, dft_n),
            "dirty_inner_half": masked_metrics(cd, dft_n, inner=True),
            "psf": masked_metrics(cp, psf_n),
            "psf_inner_half": masked_metrics(cp, psf_n, inner=True),
            "gridded_count": r["stats"]["gridded_count"],
            "nvis": int((wgt > 0).sum()),
            "wall_s": r["wall_s"],
        }
        print(
            "dft",
            pad,
            kern,
            layers,
            json.dumps(sweep_dft[f"pad{pad}_k{kern}_L{layers}"]),
            flush=True,
        )
    res["core_vs_dft_fixed_map"] = sweep_dft

    # (c) Sweep against ducc0 (epsilon 1e-9), w as is and w forced to zero.
    truth = ducc_truth(uvw, freq, vis, wgt)
    truth_psf = ducc_truth(uvw, freq, np.ones_like(vis), wgt)
    tn = truth / truth_psf[N // 2, N // 2]
    pn = truth_psf / truth_psf[N // 2, N // 2]
    res["ducc_vs_dft"] = {
        "dirty": oracle.metrics(tn, dft_n),
        "psf": oracle.metrics(pn, psf_n),
    }
    uvw0 = uvw * [1.0, 1.0, 0.0]
    truth0 = ducc_truth(uvw0, freq, vis, wgt, wgrid=False)
    truth0_psf = ducc_truth(uvw0, freq, np.ones_like(vis), wgt, wgrid=False)
    t0n = truth0 / truth0_psf[N // 2, N // 2]
    p0n = truth0_psf / truth0_psf[N // 2, N // 2]
    sweep = {}
    for pad in (1.2, 1.5, 2.0, 3.0, 4.0):
        for kern in (7, 15):
            for wcase in ("w", "w0"):
                if wcase == "w":
                    r = run_core(uvw * [1.0, 1.0, -1.0], freq, vis, wgt, pad, kern, 64)
                    ref, refp = tn, pn
                else:
                    r = run_core(uvw0, freq, vis, wgt, pad, kern, 1)
                    ref, refp = t0n, p0n
                cd, cp = core_to_dft(r["dirty"]), core_to_dft(r["psf"])
                key = f"pad{pad}_k{kern}_{wcase}"
                sweep[key] = {
                    "dirty": masked_metrics(cd, ref),
                    "dirty_inner_half": masked_metrics(cd, ref, inner=True),
                    "psf": masked_metrics(cp, refp),
                    "padded": [int(np.ceil(N * pad / 4.0 - 1e-9) * 4)],
                }
                print("ducc", key, json.dumps(sweep[key]), flush=True)
    res["core_vs_ducc_sweep"] = sweep

    # (d) Aliasing prediction, w = 0, padding 1.2 and 2, kernel 7: the image
    # the w-stacking FFT forms is sum_j D(x + j P) T(x + j P) / T(x), with T
    # the kernel's transform and P the padded field; D at the alias
    # positions from ducc0 with centre shifts.
    alias = {}
    for pad in (1.2, 2.0):
        r = run_core(uvw0, freq, vis, wgt, pad, 7, 1)
        wp = int(np.ceil(N * pad))
        wp += (4 - wp % 4) % 4
        k = np.arange(N) - N // 2
        tk = kb_transform(7, 1023, k, wp)
        jmax = args.jmax
        pred = np.zeros((N, N))
        predp = np.zeros((N, N))
        for jx in range(-jmax, jmax + 1):
            rx = kb_transform(7, 1023, k + jx * wp, wp) / tk
            for jy in range(-jmax, jmax + 1):
                ry = kb_transform(7, 1023, k + jy * wp, wp) / tk
                cx, cy = jx * wp * CELL, jy * wp * CELL
                dsh = ducc_truth(uvw0, freq, vis, wgt, wgrid=False, cx=cx, cy=cy)
                psh = ducc_truth(
                    uvw0, freq, np.ones_like(vis), wgt, wgrid=False, cx=cx, cy=cy
                )
                f = np.outer(rx, ry)
                pred += dsh * f
                predp += psh * f
        norm = predp[N // 2, N // 2]
        pred_n, predp_n = pred / norm, predp / norm
        cd = core_to_dft(r["dirty"])
        core_psf = core_to_dft(r["psf"])
        alias[f"pad{pad}"] = {
            "padded_cells": wp,
            "jmax": jmax,
            "core_minus_truth": masked_metrics(cd, t0n),
            "prediction_minus_truth": oracle.metrics(pred_n, t0n),
            "core_minus_prediction": masked_metrics(cd, pred_n),
            "psf_core_minus_truth": masked_metrics(core_psf, p0n),
            "psf_prediction_minus_truth": oracle.metrics(predp_n, p0n),
            "psf_core_minus_prediction": masked_metrics(core_psf, predp_n),
        }
        print("alias", pad, json.dumps(alias[f"pad{pad}"]), flush=True)
    res["aliasing_prediction_w0"] = alias
    res["wall_s"] = time.time() - t_start
    res["maxrss_mb"] = maxrss_mb()
    Path(args.out).write_text(json.dumps(res, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("item0")
    a.add_argument("slice")
    a.add_argument("out")
    a.add_argument("--jmax", type=int, default=6)
    a.set_defaults(func=cmd_item0)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
