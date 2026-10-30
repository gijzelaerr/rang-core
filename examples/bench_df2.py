"""Speed and agreement harness of big-plan task DF2a, the exact gridder at
ducc0's speed (research/df2-wgridder-speed.md).

    python examples/bench_df2.py refs OUT_DIR SYNTH_DIR SLICE_DIR K_INPUTS
        [--hashes threads-final.json]
    python examples/bench_df2.py compare REF_DIR OUT.json SYNTH_DIR SLICE_DIR K_INPUTS
    python examples/bench_df2.py time SET OUT.json --impl wgrid|ducc [--repeats N]
    python examples/bench_df2.py bench SET OUT_DIR [--impls wgrid,ducc]
        [--threads 1,4,16] [--repeats 3]
    python examples/bench_df2.py edge SYNTH_DIR OUT.json
    python examples/bench_df2.py summary RUN_STEPS RUN_FINAL OUT.json

SET names an input set: `k` (the six K arms of P2's dumped gridder inputs,
`--k-inputs`), `k41` (K `original` tiled 41 times) or `array` (the
whole-array synthetic case, generated in the process from the MeerKAT
antenna positions, seed 2030). One image is a dirty image and its PSF as in
`bench_df1.py` (`one_image`, unchanged): `core_wgridder.fits_image` for the
core, two ducc0 `vis2dirty` calls with `nthreads` = `RAYON_NUM_THREADS`.

`refs` saves the gridder's outputs (DF1's gated calls exactly as
`compare_core_wgridder.py hashes` makes them, plus `fits_image` on the K
arms, K x 41 and the array case) and checks the gated outputs' SHA256
against DF1's archive; `compare` recomputes them with the current code and
reports bit-identity and L-infinity over the reference peak per output.
`bench` runs `time` in a fresh process per (repeat, threads, impl), the
implementations interleaved, with `OMP_NUM_THREADS` removed from the
environment (it caps ducc0's pool) and `OPENBLAS_NUM_THREADS=1`. `edge`
is the experiment on the edge-pixel difference from ducc0 (protocol item
f); `summary` compiles the compact result archive.
"""

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "examples"))

C_LIGHT = 299792458.0
K_INPUTS = ROOT / "outputs" / "p2-gridder-20261030-01" / "inputs-k"
ANTENNA_POSITION = (
    ROOT
    / "outputs"
    / "luno-solve-20261029-02"
    / "inputs"
    / "ANTENNA"
    / "ANTENNA_0"
    / "POSITION"
    / "0.0"
)
# The whole-array case (protocol, input 4).
ARRAY = {
    "seed": 2030,
    "stations": 53,
    "integrations": 30,
    "integration_s": 8.0,
    "hour_angle_start_h": -0.5,
    "declination_deg": -63.71,
    "longitude_deg": 21.443,
    "nchan": 640,
    "freq_lo_hz": 1.070e9,
    "freq_hi_hz": 1.498e9,
    "zero_weight_fraction": 0.10,
    "width": 1024,
    "height": 1024,
    "scale_arcsec": 1.5,
}
OMEGA_EARTH = 7.2921159e-5


def sha256(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def maxrss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


# ------------------------------------------------------------------ inputs


def antenna_positions():
    from rang import core_zarr

    raw = core_zarr.read_chunk(ANTENNA_POSITION)
    return np.frombuffer(bytes(raw), "<f8").reshape(-1, 3).copy()


def array_case():
    """The whole-array synthetic input in P2's gridder-input layout."""
    a = ARRAY
    pos = antenna_positions()[: a["stations"]]
    i1, i2 = np.triu_indices(a["stations"], 1)
    b = pos[i2] - pos[i1]
    t = np.arange(a["integrations"]) * a["integration_s"]
    ha = (
        np.deg2rad(a["hour_angle_start_h"] * 15.0 + a["longitude_deg"])
        + OMEGA_EARTH * t
    )
    dec = np.deg2rad(a["declination_deg"])
    sh, ch = np.sin(ha)[:, None], np.cos(ha)[:, None]
    x, y, z = b[None, :, 0], b[None, :, 1], b[None, :, 2]
    uvw = np.stack(
        [
            sh * x + ch * y,
            -np.sin(dec) * ch * x + np.sin(dec) * sh * y + np.cos(dec) * z,
            np.cos(dec) * ch * x - np.cos(dec) * sh * y + np.sin(dec) * z,
        ],
        axis=-1,
    ).reshape(-1, 3)
    freq = np.linspace(a["freq_lo_hz"], a["freq_hi_hz"], a["nchan"])
    rng = np.random.default_rng(a["seed"])
    shape = (uvw.shape[0], a["nchan"])
    data = (1.0 + rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
        np.complex64
    )
    weights = rng.uniform(0.5, 1.5, shape).astype(np.float32)
    weights[rng.random(shape) < a["zero_weight_fraction"]] = 0.0
    inputs = {
        "uvw": uvw,
        "frequencies": freq,
        "data": data,
        "weights": weights,
        "imaging_weights": np.ones(shape, np.float32),
    }
    settings = {
        "width": a["width"],
        "height": a["height"],
        "scale_arcsec": a["scale_arcsec"],
    }
    return [("array", inputs, settings)]


def load_set(name, k_inputs=K_INPUTS):
    import bench_p2_gridder as p2

    if name == "k":
        return p2._load_inputs(str(k_inputs))
    if name == "k41":
        return p2._load_inputs(str(k_inputs), ["k-original"], 41)
    if name == "array":
        return array_case()
    raise SystemExit(f"unknown input set {name}")


# ------------------------------------------------------- reference outputs


def gate_outputs(synth, slice_dir):
    """DF1's gated outputs, as `compare_core_wgridder.py hashes` makes them."""
    import compare_core_wgridder as ccw

    for case in ccw.all_cases(synth, slice_dir):
        name = case["name"]
        for prec, eps in ccw.GATED:
            key = f"{name}_{prec}_eps{eps:g}"
            img, _, _ = ccw.core_v2d(case, prec, eps)
            yield f"{key}_dirty", img
            if "image" in case:
                vis, _, _ = ccw.core_d2v(case, prec, eps)
                yield f"{key}_vis", vis
            if "dft_psf" in case:
                psf, _, _ = ccw.core_v2d(
                    case, prec, eps, vis=np.ones(case["vis"].shape)
                )
                yield f"{key}_psf", psf


def image_outputs(k_inputs):
    """`fits_image` dirty and PSF on the K arms (f64 1e-6 and f32 1e-4), K x 41
    and the array case (f64 1e-6)."""
    import bench_df1

    runs = [("k", 1e-6, False), ("k", 1e-4, True), ("k41", 1e-6, False)]
    runs.append(("array", 1e-6, False))
    for set_name, eps, single in runs:
        for label, inputs, settings in load_set(set_name, k_inputs):
            dirty, psf = bench_df1.one_image("wgrid", inputs, settings, eps, single)
            tag = f"{set_name}_{label}_{'f32' if single else 'f64'}_eps{eps:g}"
            yield f"{tag}_dirty", dirty
            yield f"{tag}_psf", psf
            if set_name in ("k", "array") and not single:
                yield (
                    f"{tag}_zero_data_nonzero_weight",
                    np.array(
                        int(
                            np.count_nonzero(
                                (inputs["data"] == 0)
                                & (inputs["weights"] * inputs["imaging_weights"] != 0)
                            )
                        )
                    ),
                )


def cmd_refs(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    t0 = time.perf_counter()
    archived = None
    if args.hashes:
        archived = json.loads(Path(args.hashes).read_text())["threads"]["1"]["hashes"]
    rec = {"outputs": {}, "hash_mismatches": []}
    for key, arr in gate_outputs(args.synth, args.slice):
        np.save(out / f"{key}.npy", arr)
        h = sha256(arr)
        rec["outputs"][key] = h
        if archived is not None and archived.get(key) != h:
            rec["hash_mismatches"].append(key)
        print(key, h[:12], flush=True)
    if archived is not None:
        rec["archived_outputs_checked"] = len(archived)
        rec["missing"] = sorted(set(archived) - set(rec["outputs"]))
    for key, arr in image_outputs(args.k_inputs):
        np.save(out / f"{key}.npy", arr)
        rec["outputs"][key] = sha256(arr)
        print(key, rec["outputs"][key][:12], flush=True)
    from rang import core_wgridder

    rec["library"] = str(core_wgridder.library_path())
    rec["wall_s"] = time.perf_counter() - t0
    rec["maxrss_mb"] = maxrss_mb()
    (out / "refs.json").write_text(json.dumps(rec, indent=1))
    print("hash mismatches against DF1's archive:", rec["hash_mismatches"])


def cmd_compare(args):
    ref = Path(args.ref)
    t0 = time.perf_counter()
    res = {"outputs": {}}
    gen = list(gate_outputs(args.synth, args.slice))
    if not args.gates_only:
        gen += list(image_outputs(args.k_inputs))
    for key, arr in gen:
        r = np.load(ref / f"{key}.npy")
        if key.endswith("_zero_data_nonzero_weight"):
            res["outputs"][key] = {"value": int(arr), "reference": int(r)}
            continue
        peak = float(np.abs(r).max())
        diff = float(np.abs(arr.astype(r.dtype) - r).max())
        e = {
            "identical": bool(arr.dtype == r.dtype and np.array_equal(arr, r)),
            "linf_rel_peak": diff / peak if peak else diff,
            "sha256": sha256(arr),
        }
        res["outputs"][key] = e
        print(
            f"{key:60s} {'identical' if e['identical'] else 'differs'} "
            f"{e['linf_rel_peak']:.2e}",
            flush=True,
        )
    vals = [v for v in res["outputs"].values() if "identical" in v]
    res["all_identical"] = all(v["identical"] for v in vals)
    errs = {
        k: v["linf_rel_peak"] for k, v in res["outputs"].items() if "identical" in v
    }
    f64 = [e for k, e in errs.items() if "f64" in k]
    f32 = [e for k, e in errs.items() if "f32" in k]
    res["worst_f64"] = max(f64) if f64 else None
    res["worst_f32"] = max(f32) if f32 else None
    res["pass_tolerance"] = bool(
        (not f64 or max(f64) <= 1e-13) and (not f32 or max(f32) <= 1e-5)
    )
    from rang import core_wgridder

    res["library"] = str(core_wgridder.library_path())
    res["rayon_num_threads"] = os.environ.get("RAYON_NUM_THREADS")
    res["wall_s"] = time.perf_counter() - t0
    res["maxrss_mb"] = maxrss_mb()
    Path(args.out).write_text(json.dumps(res, indent=1))
    print(
        "all identical:",
        res["all_identical"],
        "worst f64",
        res["worst_f64"],
        "worst f32",
        res["worst_f32"],
        "within tolerance:",
        res["pass_tolerance"],
    )


# --------------------------------------------- the edge difference (item f)


def correction(info, nx, ny, dx, dy):
    """The gridder's correction factor per pixel (u, v and w correction
    functions, ducc0's `GLFullCorrection`), relative to the image centre,
    from the kernel row and plan in `info` (no l/m shift)."""
    from rang import core_wgridder

    w, _, _, beta, e0, _, _ = core_wgridder.kernel_row(info["kernel_index"])
    beta *= w
    p = int(1.5 * w) + 2
    x, wt = np.polynomial.legendre.leggauss(2 * p)
    phi = np.exp(beta * ((1.0 - x * x) ** e0 - 1.0))

    def corfunc(v):
        v = np.asarray(v, float)[..., None]
        return 1.0 / np.sum(wt * phi * w * 0.5 * np.cos(np.pi * w * x * v), axis=-1)

    i = np.arange(nx) - nx // 2
    j = np.arange(ny) - ny // 2
    cu = corfunc(np.abs(i) / info["nu"])
    cv = corfunc(np.abs(j) / info["nv"])
    lx, my = np.meshgrid(i * dx, j * dy, indexing="ij")
    r2 = lx**2 + my**2
    nm1 = -r2 / (np.sqrt(1.0 - r2) + 1.0)
    cw = corfunc((nm1 + info["nshift"]) * info["dw"])
    c = cu[:, None] * cv[None, :] * cw
    return c / c[nx // 2, ny // 2]


def cmd_edge(args):
    """Is the port's difference from ducc0 in the outermost pixels a defect
    of the port? Per case and epsilon (f64): the port and ducc0 against the
    DFT, against each other, and each against itself with the rows of the
    input permuted (the same algorithm, only the summation order changed),
    in the border (outer two pixels) and the interior (eight pixels in),
    and the differences divided by the correction factor."""
    import ducc0
    import oracle_ducc0 as oracle
    from rang import core_wgridder

    t0 = time.perf_counter()
    res = {"ducc0": ducc0.__version__, "seed": args.seed, "cases": {}}
    for name in args.cases.split(","):
        case = oracle.load_case(Path(args.synth) / f"{name}.npz")
        nx, ny, dx, dy = case["nx"], case["ny"], case["dx"], case["dy"]
        perm = np.random.default_rng(args.seed).permutation(case["uvw"].shape[0])
        dft = case["dft_dirty"]
        peak = float(np.abs(dft).max())
        border = np.zeros((nx, ny), bool)
        border[:2] = border[-2:] = True
        border[:, :2] = border[:, -2:] = True
        interior = np.zeros((nx, ny), bool)
        interior[8:-8, 8:-8] = True
        common = {"npix_x": nx, "npix_y": ny, "pixsize_x": dx, "pixsize_y": dy}
        recs = {}
        for eps in (float(x) for x in args.epsilons.split(",")):
            out = {}
            for tag, rows in (("", slice(None)), ("_perm", perm)):
                kw = dict(
                    uvw=case["uvw"][rows],
                    freq=case["freq"],
                    vis=case["vis"][rows],
                    wgt=case["wgt"][rows],
                    epsilon=eps,
                    **common,
                )
                out["port" + tag], info = core_wgridder.vis2dirty(
                    return_info=True, **kw
                )
                out["ducc" + tag] = ducc0.wgridder.vis2dirty(
                    nthreads=1, do_wgridding=True, flip_w=True, divide_by_n=False, **kw
                )
            corr = correction(info, nx, ny, dx, dy)

            def lin(a, b, mask, corr=corr, peak=peak):
                return float(np.abs(a - b)[mask].max() / peak)

            def lin_corr(a, b, mask, corr=corr, peak=peak):
                return float((np.abs(a - b) / corr)[mask].max() / peak)

            pairs = {
                "port-dft": ("port", None),
                "ducc0-dft": ("ducc", None),
                "port-ducc0": ("port", "ducc"),
                "port-port_permuted": ("port", "port_perm"),
                "ducc0-ducc0_permuted": ("ducc", "ducc_perm"),
            }
            rec = {
                "plan": info,
                "correction_max_border": float(corr[border].max()),
                "correction_max_interior": float(corr[interior].max()),
            }
            for key, (a, b) in pairs.items():
                ref = dft if b is None else out[b]
                rec[key] = {
                    "border": lin(out[a], ref, border),
                    "interior": lin(out[a], ref, interior),
                    "border_over_correction": lin_corr(out[a], ref, border),
                    "interior_over_correction": lin_corr(out[a], ref, interior),
                }
            closer = np.abs(out["port"] - dft) <= np.abs(out["ducc"] - dft)
            rec["port_closer_to_dft_fraction_border"] = float(closer[border].mean())
            recs[f"{eps:g}"] = rec
            print(
                name,
                f"eps {eps:g}",
                " ".join(
                    f"{k} {rec[k]['border']:.1e}/{rec[k]['interior']:.1e}"
                    for k in pairs
                ),
                f"corr {rec['correction_max_border']:.1e}",
                f"closer {rec['port_closer_to_dft_fraction_border']:.2f}",
                flush=True,
            )
        res["cases"][name] = recs
    res["library"] = str(core_wgridder.library_path())
    res["wall_s"] = time.perf_counter() - t0
    res["maxrss_mb"] = maxrss_mb()
    Path(args.out).write_text(json.dumps(res, indent=1))


# ------------------------------------------------------------------ summary

# Speed and memory targets of the protocol (gated sets).
GATED_SETS = ("k41", "array")
TARGET = {1: 1.5, 16: 2.0}
MEMORY_FACTOR = 1.2


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _table(path):
    rows = json.loads(Path(path).read_text())
    return {(r["impl"], r["threads"]): r for r in rows if "threads" in r}, {
        r["impl"]: r["hashes_identical_across_runs"] for r in rows if "threads" not in r
    }


def _compare_rows(table):
    out = []
    for threads in sorted({t for _, t in table}):
        w, d = table.get(("wgrid", threads)), table.get(("ducc", threads))
        if not (w and d):
            continue
        out.append(
            {
                "threads": threads,
                "core_wall_per_image": w["wall_per_image_median"],
                "core_wall_range": w["wall_total_range"],
                "ducc0_wall_per_image": d["wall_per_image_median"],
                "ducc0_wall_range": d["wall_total_range"],
                "ratio": w["wall_total_median"] / d["wall_total_median"],
                "core_ns_per_visibility": w["ns_per_gridded_visibility_per_image"],
                "ducc0_ns_per_visibility": d["ns_per_gridded_visibility_per_image"],
                "core_max_rss_mb": w["max_rss_mb"],
                "ducc0_max_rss_mb": d["max_rss_mb"],
                "rss_ratio": w["max_rss_mb"] / d["max_rss_mb"],
                "core_rss_over_inputs_mb": w["max_rss_mb"]
                - w["rss_mb_after_loading_inputs"],
                "ducc0_rss_over_inputs_mb": d["max_rss_mb"]
                - d["rss_mb_after_loading_inputs"],
            }
        )
    return out


def cmd_summary(args):
    steps, final = Path(args.steps), Path(args.final)
    res = {"task": "DF2a", "runs": [_rel(steps), _rel(final)], "sets": {}}
    for name in ("k", "k41", "array", "k-f32"):
        entry = {}
        base = steps / f"bench-df1-{name}" / "table.json"
        if base.is_file():
            table, ident = _table(base)
            entry["df1_baseline"] = _compare_rows(table)
            entry["df1_hashes_identical_across_runs"] = ident
        for key, suffix in (("final", ""), ("final_repeat_labelled", "-repeat")):
            fin = final / f"bench-{name}{suffix}" / "table.json"
            if not fin.is_file():
                continue
            table, ident = _table(fin)
            rows = _compare_rows(table)
            for r in rows:
                if name in GATED_SETS and r["threads"] in TARGET:
                    r["speed_target"] = TARGET[r["threads"]]
                    r["speed_pass"] = bool(r["ratio"] <= TARGET[r["threads"]])
                if name in GATED_SETS or name == "k":
                    r["memory_pass"] = bool(r["rss_ratio"] <= MEMORY_FACTOR)
            entry[key] = rows
            entry[key + "_hashes_identical_across_runs_and_threads"] = ident
        res["sets"][name] = entry
    res["steps"] = []
    for path in sorted(steps.glob("quick-*/summary.json")):
        tag, _, set_name = path.parent.name.removeprefix("quick-").rpartition("-")
        for r in json.loads(path.read_text()):
            res["steps"].append(
                {
                    "step": tag,
                    "set": set_name,
                    "threads": r["threads"],
                    "core_wall_total": r["wall_total"],
                    "max_rss_mb": r["max_rss_mb"],
                    "load_before": r["loadavg_before_after"][0][0],
                }
            )
    for key, name in (
        ("edge", "edge.json"),
        ("f32_probe", "f32-probe.json"),
    ):
        if (steps / name).is_file():
            res[key] = json.loads((steps / name).read_text())
    groups = steps / "logs" / "a-groups.log"
    if groups.is_file():
        res["plane_groups"] = groups.read_text().splitlines()
    gates = final / "gates-final" / "gates.json"
    if gates.is_file():
        g = json.loads(gates.read_text())
        res["gates"] = {
            "failures": g["failures"],
            "pass_criteria_1_2_3_5": g["pass_criteria_1_2_3_5"],
            "kernel_table": g.get("kernel_table"),
            "single_visibility": g["single_visibility"],
            "cases": {
                case: {
                    key: (
                        [a["rel"] for a in e]
                        if key == "adjointness"
                        else {
                            d: {
                                "vs_dft": e[d]["vs_dft"]["linf_rel_peak"],
                                "vs_ducc0": e[d]["vs_ducc0"]["linf_rel_peak"],
                                "plan_equal": e[d]["plan"]["equal"],
                            }
                            for d in ("vis2dirty", "psf", "dirty2vis")
                            if d in e
                        }
                    )
                    for key, e in rec.items()
                }
                for case, rec in g["cases"].items()
            },
        }
    threads = final / "threads-final.json"
    if threads.is_file():
        t = json.loads(threads.read_text())
        res["threads"] = {"identical": t["identical"], "outputs": t["outputs"]}
    comp = final / "compare-final.json"
    if comp.is_file():
        c = json.loads(comp.read_text())
        res["agreement_with_df1"] = {
            "worst_f64": c["worst_f64"],
            "worst_f32": c["worst_f32"],
            "pass_tolerance": c["pass_tolerance"],
            "outputs": {
                k: {kk: v[kk] for kk in ("identical", "linf_rel_peak") if kk in v}
                for k, v in c["outputs"].items()
            },
        }
    simd = sorted((final / "simd-final").glob("*.txt"))
    if simd:
        lines = {p.stem: p.read_text().splitlines()[0] for p in simd}
        res["simd_levels_identical"] = len(set(lines.values())) == 1
    Path(args.out).write_text(json.dumps(res, indent=1) + "\n")
    print("wrote", args.out)


# ------------------------------------------------------------------- timing


def cmd_time(args):
    import bench_df1

    load_before = os.getloadavg()
    items = load_set(args.set, args.k_inputs)
    loaded = maxrss_mb()
    gridded = {
        label: int(np.count_nonzero(inp["weights"] * inp["imaging_weights"]))
        for label, inp, _ in items
    }
    records = []
    for repeat in range(args.repeats):
        for label, inputs, settings in items:
            w0, c0 = time.perf_counter(), time.process_time()
            dirty, psf = bench_df1.one_image(
                args.impl, inputs, settings, args.epsilon, args.single
            )
            wall = time.perf_counter() - w0
            records.append(
                {
                    "repeat": repeat,
                    "label": label,
                    "cells": int(inputs["data"].size),
                    "gridded": gridded[label],
                    "wall": wall,
                    "cpu": time.process_time() - c0,
                    "dirty_sha256": sha256(dirty),
                    "psf_sha256": sha256(psf),
                }
            )
            print(f"{args.impl} {label:28s} r{repeat} {wall:8.3f} s", flush=True)
    result = {
        "impl": args.impl,
        "set": args.set,
        "epsilon": args.epsilon,
        "single": args.single,
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "records": records,
        "max_rss_mb": maxrss_mb(),
        "rss_mb_after_loading_inputs": loaded,
        "loadavg_before_after": [load_before, os.getloadavg()],
    }
    if args.impl == "ducc":
        import ducc0

        result["ducc0"] = ducc0.__version__
        result["ducc0_pool"] = ducc0.misc.thread_pool_size()
    else:
        from rang import core_wgridder

        result["library"] = str(core_wgridder.library_path())
    Path(args.out).write_text(json.dumps(result, indent=1))


def cmd_bench(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    summary = []
    env0 = {k: v for k, v in os.environ.items() if k != "OMP_NUM_THREADS"}
    for repeat in range(args.repeats):
        for threads in args.threads.split(","):
            for impl in args.impls.split(","):
                env = dict(env0, RAYON_NUM_THREADS=threads, OPENBLAS_NUM_THREADS="1")
                path = out / f"{impl}-t{threads}-r{repeat}.json"
                cmd = [sys.executable, __file__, "time", args.set, str(path)]
                cmd += ["--impl", impl, "--epsilon", str(args.epsilon)]
                cmd += ["--k-inputs", str(args.k_inputs)]
                if args.single:
                    cmd.append("--single")
                subprocess.run(cmd, env=env, check=True)
                rec = json.loads(path.read_text())
                walls = [r["wall"] for r in rec["records"]]
                summary.append(
                    {
                        "impl": impl,
                        "threads": int(threads),
                        "repeat": repeat,
                        "images": len(walls),
                        "wall_per_image_median": float(np.median(walls)),
                        "wall_total": float(np.sum(walls)),
                        "cpu_total": float(sum(r["cpu"] for r in rec["records"])),
                        "gridded_total": int(sum(r["gridded"] for r in rec["records"])),
                        "max_rss_mb": rec["max_rss_mb"],
                        "rss_mb_after_loading_inputs": rec[
                            "rss_mb_after_loading_inputs"
                        ],
                        "loadavg_before_after": rec["loadavg_before_after"],
                        "hashes": [
                            [r["label"], r["dirty_sha256"], r["psf_sha256"]]
                            for r in rec["records"]
                        ],
                    }
                )
                s = summary[-1]
                print(
                    f"{impl:6s} t{threads:>2s} r{repeat} total {s['wall_total']:8.3f} s "
                    f"rss {s['max_rss_mb']:7.0f} MB load {rec['loadavg_before_after'][0][0]:.1f}",
                    flush=True,
                )
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    table = aggregate(summary)
    (out / "table.json").write_text(json.dumps(table, indent=1))
    for row in table:
        print(json.dumps(row))


def aggregate(summary):
    """Per (impl, threads): median and range of the per-repeat totals, peak
    RSS, and whether the output hashes agree across repeats and threads."""
    rows = []
    keys = sorted({(s["impl"], s["threads"]) for s in summary})
    for impl, threads in keys:
        sel = [s for s in summary if s["impl"] == impl and s["threads"] == threads]
        tot = [s["wall_total"] for s in sel]
        rows.append(
            {
                "impl": impl,
                "threads": threads,
                "repeats": len(sel),
                "images": sel[0]["images"],
                "gridded_total": sel[0]["gridded_total"],
                "wall_total_median": float(np.median(tot)),
                "wall_total_range": [float(min(tot)), float(max(tot))],
                "wall_per_image_median": float(np.median(tot)) / sel[0]["images"],
                "ns_per_gridded_visibility_per_image": 1e9
                * float(np.median(tot))
                / sel[0]["gridded_total"],
                "max_rss_mb": float(max(s["max_rss_mb"] for s in sel)),
                "rss_mb_after_loading_inputs": float(
                    max(s["rss_mb_after_loading_inputs"] for s in sel)
                ),
            }
        )
    for impl in sorted({s["impl"] for s in summary}):
        hs = {json.dumps(s["hashes"]) for s in summary if s["impl"] == impl}
        rows.append({"impl": impl, "hashes_identical_across_runs": len(hs) == 1})
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refs")
    r.add_argument("out")
    r.add_argument("synth")
    r.add_argument("slice")
    r.add_argument("k_inputs")
    r.add_argument("--hashes", default=None, help="DF1's threads-final.json")
    r.set_defaults(func=cmd_refs)
    c = sub.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("out")
    c.add_argument("synth")
    c.add_argument("slice")
    c.add_argument("k_inputs")
    c.add_argument("--gates-only", action="store_true")
    c.set_defaults(func=cmd_compare)
    e = sub.add_parser("edge")
    e.add_argument("synth")
    e.add_argument("out")
    e.add_argument("--cases", default="wide-0p3rad,wide-0p3rad-rect")
    e.add_argument("--epsilons", default="1e-5,1e-7,1e-9,1e-11")
    e.add_argument("--seed", type=int, default=7)
    e.set_defaults(func=cmd_edge)
    m = sub.add_parser("summary")
    m.add_argument("steps")
    m.add_argument("final")
    m.add_argument("out")
    m.set_defaults(func=cmd_summary)
    for name, func in (("time", cmd_time), ("bench", cmd_bench)):
        q = sub.add_parser(name)
        q.add_argument("set", choices=("k", "k41", "array"))
        q.add_argument("out")
        q.add_argument("--k-inputs", default=str(K_INPUTS))
        q.add_argument("--epsilon", type=float, default=1e-6)
        q.add_argument("--single", action="store_true")
        q.add_argument("--repeats", type=int, default=1 if name == "time" else 3)
        if name == "time":
            q.add_argument("--impl", choices=("wgrid", "ducc"), required=True)
        else:
            q.add_argument("--impls", default="wgrid,ducc")
            q.add_argument("--threads", default="1,4,16")
        q.set_defaults(func=func)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
