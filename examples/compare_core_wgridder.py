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


# -------------------------------------------------------------------- gates

GATED = (("f32", 1e-4), ("f64", 1e-7))


def all_cases(synth, slice_dir, subset=None):
    paths = sorted(Path(synth).glob("*.npz")) + [Path(slice_dir)]
    cases = [oracle.load_case(p) for p in paths]
    if subset:
        keep = set(subset.split(","))
        cases = [c for c in cases if c["name"] in keep]
    return cases


def core_v2d(case, prec, eps, vis=None):
    from rangtoy import core_wgridder

    cdt, rdt = (
        (np.complex64, np.float32) if prec == "f32" else (np.complex128, np.float64)
    )
    if vis is None:
        vis = case["vis_c64"] if prec == "f32" and "vis_c64" in case else case["vis"]
    t0 = time.perf_counter()
    img, info = core_wgridder.vis2dirty(
        uvw=case["uvw"],
        freq=case["freq"],
        vis=np.asarray(vis, cdt),
        wgt=np.asarray(case["wgt"], rdt),
        npix_x=case["nx"],
        npix_y=case["ny"],
        pixsize_x=case["dx"],
        pixsize_y=case["dy"],
        epsilon=eps,
        return_info=True,
    )
    return img, info, time.perf_counter() - t0


def core_d2v(case, prec, eps, image=None):
    from rangtoy import core_wgridder

    rdt = np.float32 if prec == "f32" else np.float64
    image = case["image"] if image is None else image
    t0 = time.perf_counter()
    vis, info = core_wgridder.dirty2vis(
        uvw=case["uvw"],
        freq=case["freq"],
        dirty=np.asarray(image, rdt),
        wgt=np.asarray(case["wgt"], rdt),
        pixsize_x=case["dx"],
        pixsize_y=case["dy"],
        epsilon=eps,
        return_info=True,
    )
    return vis, info, time.perf_counter() - t0


def plan_matches(info, report):
    keys = ("supp", "nu", "nv", "nplanes")
    core = {k: info[k] for k in keys}
    ducc = {k: report[k] for k in keys}
    return {"core": core, "ducc0": ducc, "equal": core == ducc}


def kernel_check(rows_path):
    from rangtoy import core_wgridder

    res = {"rows_txt": str(rows_path)}
    text = Path(rows_path).read_text()
    ref = []
    for line in text.splitlines():
        f = [x.strip() for x in line.strip()[1:-1].split(",")]
        ref.append(
            (
                int(f[0]),
                float(f[1]),
                float(f[2]),
                float(f[3]),
                float(f[4]),
                int(f[5]),
                f[6] == "true",
            )
        )
    table = core_wgridder.kernel_table()
    res["rows_core"] = len(table)
    res["rows_ducc0"] = len(ref)
    res["values_equal"] = table == ref
    src = (ROOT / "core" / "src" / "wgridder.rs").read_text().splitlines()
    a = src.index("// KERNEL_ROWS_BEGIN")
    b = src.index("// KERNEL_ROWS_END")
    rust_text = "\n".join(line.rstrip(",") for line in src[a + 1 : b]) + "\n"
    res["sha256_rust_rows_text"] = oracle.hashlib.sha256(rust_text.encode()).hexdigest()
    res["sha256_extracted_rows_text"] = oracle.hashlib.sha256(text.encode()).hexdigest()
    res["text_equal"] = rust_text == text
    res["pass"] = bool(res["values_equal"] and res["text_equal"])
    return res


def single_vis_check():
    """One visibility at many sub-cell offsets, w = 0 and w != 0, against
    ducc0 (f64, epsilon 1e-7): the kernel values directly (reported)."""
    import ducc0
    from rangtoy import core_wgridder

    nx, dx = 64, 1e-3
    freq = np.array([C_LIGHT])  # uvw in metres = wavelengths
    worst = {"w0": 0.0, "w": 0.0}
    for wcase in ("w0", "w"):
        for k in range(40):
            frac = k / 40.0
            uvw = np.array(
                [
                    [
                        (3 + frac) / (nx * 1.7 * dx),
                        (-5 - 0.37 * frac) / (nx * 1.7 * dx),
                        0.0,
                    ]
                ]
            )
            if wcase == "w":
                uvw[0, 2] = 200.0 * (frac - 0.5)
                uvw = np.vstack([uvw, [[0.0, 0.0, 120.0]], [[0.0, 0.0, -80.0]]])
            vis = np.ones((uvw.shape[0], 1), np.complex128)
            vis[1:] = 0.0
            vis[1:, 0] = 1e-30  # keep the w range active without signal
            a = core_wgridder.vis2dirty(
                uvw=uvw,
                freq=freq,
                vis=vis,
                npix_x=nx,
                npix_y=nx,
                pixsize_x=dx,
                pixsize_y=dx,
                epsilon=1e-7,
            )
            b = ducc0.wgridder.vis2dirty(
                uvw=uvw,
                freq=freq,
                vis=vis,
                npix_x=nx,
                npix_y=nx,
                pixsize_x=dx,
                pixsize_y=dx,
                epsilon=1e-7,
                do_wgridding=True,
                nthreads=1,
                flip_w=True,
                divide_by_n=False,
            )
            worst[wcase] = max(
                worst[wcase], float(np.abs(a - b).max() / np.abs(b).max())
            )
    return {"linf_rel_peak_worst": worst, "offsets": 40}


def adjointness(case, eps, seed):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((case["nx"], case["ny"]))
    y = rng.standard_normal(case["vis"].shape) + 1j * rng.standard_normal(
        case["vis"].shape
    )
    ax, _, _ = core_d2v(case, "f64", eps, image=x)
    aty, _, _ = core_v2d(case, "f64", eps, vis=y)
    lhs = float(np.real(np.vdot(ax, y)))
    rhs = float(np.sum(x * aty))
    scale = float(np.linalg.norm(ax) * np.linalg.norm(y))
    return {
        "lhs": lhs,
        "rhs": rhs,
        "rel": abs(lhs - rhs) / scale,
        "seed": seed,
        "epsilon": eps,
    }


def cmd_gates(args):
    import ducc0

    t_start = time.time()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    dsynth = json.loads((Path(args.ducc_synth) / "ducc.json").read_text())
    dslice = json.loads((Path(args.ducc_slice) / "ducc.json").read_text())
    reports = {**dsynth["cases"], **dslice["cases"]}
    res = {"ducc0": ducc0.__version__, "cases": {}, "pass": {}}
    fails = []
    for case in all_cases(args.synth, args.slice, args.cases):
        name = case["name"]
        ddir = Path(args.ducc_slice if name == "luno-slice" else args.ducc_synth)
        rec = {}
        for prec, eps in oracle.EPSILONS:
            key = f"{prec}_eps{eps:g}"
            gated = (prec, eps) in GATED
            rep = reports[name][key]["report"]
            img, info, wall = core_v2d(case, prec, eps)
            ducc_img = np.load(ddir / f"{name}_{key}_dirty.npy")
            e = {
                "gated": gated,
                "vis2dirty": {
                    "wall_s": wall,
                    "sha256": oracle.sha256(img),
                    "vs_dft": oracle.metrics(img, case["dft_dirty"]),
                    "vs_ducc0": oracle.metrics(img, ducc_img),
                    "plan": plan_matches(info, rep[0]),
                },
            }
            checks = [
                (
                    "vis2dirty vs DFT",
                    e["vis2dirty"]["vs_dft"]["linf_rel_peak"],
                    10 * eps,
                ),
                (
                    "vis2dirty vs ducc0",
                    e["vis2dirty"]["vs_ducc0"]["linf_rel_peak"],
                    eps,
                ),
            ]
            plans_equal = [e["vis2dirty"]["plan"]["equal"]]
            if args.save_images:
                np.save(out / f"{name}_{key}_dirty.npy", img)
            if "dft_psf" in case:
                ones = np.ones(case["vis"].shape, np.complex128)
                psf, pinfo, wall = core_v2d(case, prec, eps, vis=ones)
                ducc_psf = np.load(ddir / f"{name}_{key}_psf.npy")
                e["psf"] = {
                    "wall_s": wall,
                    "sha256": oracle.sha256(psf),
                    "vs_dft": oracle.metrics(psf, case["dft_psf"]),
                    "vs_ducc0": oracle.metrics(psf, ducc_psf),
                    "plan": plan_matches(pinfo, rep[1]),
                }
                checks += [
                    ("psf vs DFT", e["psf"]["vs_dft"]["linf_rel_peak"], 10 * eps),
                    ("psf vs ducc0", e["psf"]["vs_ducc0"]["linf_rel_peak"], eps),
                ]
                plans_equal.append(e["psf"]["plan"]["equal"])
            if "image" in case:
                vis, vinfo, wall = core_d2v(case, prec, eps)
                ducc_vis = np.load(ddir / f"{name}_{key}_vis.npy")
                e["dirty2vis"] = {
                    "wall_s": wall,
                    "sha256": oracle.sha256(vis),
                    "vs_dft": oracle.metrics(vis, case["dft_vis"]),
                    "vs_ducc0": oracle.metrics(vis, ducc_vis),
                    "plan": plan_matches(vinfo, rep[1]),
                }
                checks += [
                    (
                        "dirty2vis vs DFT",
                        e["dirty2vis"]["vs_dft"]["linf_rel_peak"],
                        10 * eps,
                    ),
                    (
                        "dirty2vis vs ducc0",
                        e["dirty2vis"]["vs_ducc0"]["linf_rel_peak"],
                        eps,
                    ),
                ]
                plans_equal.append(e["dirty2vis"]["plan"]["equal"])
            e["checks"] = [
                {"what": w, "value": v, "limit": lim, "pass": bool(v <= lim)}
                for w, v, lim in checks
            ]
            e["plans_equal"] = all(plans_equal)
            if gated:
                fails += [
                    f"{name} {key} {c['what']}" for c in e["checks"] if not c["pass"]
                ]
            if not e["plans_equal"]:
                fails.append(f"{name} {key} plan")
            rec[key] = e
            print(
                name,
                key,
                "gated" if gated else "reported",
                " ".join(f"{c['what']}={c['value']:.2e}" for c in e["checks"]),
                "plan",
                e["plans_equal"],
                flush=True,
            )
        if "image" in case:
            rec["adjointness"] = [
                adjointness(case, eps, 1000 + i) for i, eps in enumerate((1e-7, 1e-9))
            ]
            for a in rec["adjointness"]:
                print(name, "adjoint", a["epsilon"], f"{a['rel']:.2e}", flush=True)
                if a["rel"] > 1e-12:
                    fails.append(f"{name} adjoint {a['epsilon']}")
        res["cases"][name] = rec
    if args.rows:
        res["kernel_table"] = kernel_check(args.rows)
        print("kernel table", json.dumps(res["kernel_table"]), flush=True)
        if not res["kernel_table"]["pass"]:
            fails.append("kernel table")
    res["single_visibility"] = single_vis_check()
    print("single visibility", json.dumps(res["single_visibility"]), flush=True)
    res["failures"] = fails
    res["pass_criteria_1_2_3_5"] = not fails
    res["library"] = str(
        __import__("rangtoy.core_wgridder").core_wgridder.library_path()
    )
    res["wall_s"] = time.time() - t_start
    res["maxrss_mb"] = maxrss_mb()
    (out / "gates.json").write_text(json.dumps(res, indent=1))
    print("FAILURES" if fails else "ALL GATED CHECKS PASS", fails, flush=True)


def cmd_hashes(args):
    """SHA256 of every gated output in this process (for `threads`)."""
    res = {}
    for case in all_cases(args.synth, args.slice):
        name = case["name"]
        for prec, eps in GATED:
            key = f"{name}_{prec}_eps{eps:g}"
            img, _, _ = core_v2d(case, prec, eps)
            res[f"{key}_dirty"] = oracle.sha256(img)
            if "image" in case:
                vis, _, _ = core_d2v(case, prec, eps)
                res[f"{key}_vis"] = oracle.sha256(vis)
            if "dft_psf" in case:
                psf, _, _ = core_v2d(case, prec, eps, vis=np.ones(case["vis"].shape))
                res[f"{key}_psf"] = oracle.sha256(psf)
    print(json.dumps(res))


def cmd_threads(args):
    import os
    import subprocess

    res = {"threads": {}, "library": None}
    for n in (int(x) for x in args.threads.split(",")):
        env = dict(os.environ, RAYON_NUM_THREADS=str(n), OPENBLAS_NUM_THREADS="1")
        t0 = time.time()
        out = subprocess.run(
            [sys.executable, __file__, "hashes", args.synth, args.slice],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        res["threads"][str(n)] = {
            "hashes": json.loads(out.strip().splitlines()[-1]),
            "wall_s": time.time() - t0,
        }
        print(n, "threads", round(time.time() - t0, 2), "s", flush=True)
    sets = [json.dumps(v["hashes"], sort_keys=True) for v in res["threads"].values()]
    res["identical"] = len(set(sets)) == 1
    res["outputs"] = len(json.loads(sets[0]))
    Path(args.out).write_text(json.dumps(res, indent=1))
    print(
        "identical at every thread count:", res["identical"], "outputs:", res["outputs"]
    )


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
    g = sub.add_parser("gates")
    g.add_argument("out")
    g.add_argument("synth")
    g.add_argument("slice")
    g.add_argument("ducc_synth")
    g.add_argument("ducc_slice")
    g.add_argument("--rows", default=None, help="extracted KernelDB rows.txt")
    g.add_argument("--cases", default=None, help="comma-separated subset (smoke)")
    g.add_argument("--save-images", action="store_true")
    g.set_defaults(func=cmd_gates)
    t = sub.add_parser("threads")
    t.add_argument("out")
    t.add_argument("synth")
    t.add_argument("slice")
    t.add_argument("--threads", default="1,2,4,8,16")
    t.set_defaults(func=cmd_threads)
    h = sub.add_parser("hashes")
    h.add_argument("synth")
    h.add_argument("slice")
    h.set_defaults(func=cmd_hashes)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
