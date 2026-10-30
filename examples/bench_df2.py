"""Speed and agreement harness of big-plan task DF2a, the exact gridder at
ducc0's speed (research/df2-wgridder-speed.md).

    python examples/bench_df2.py refs OUT_DIR SYNTH_DIR SLICE_DIR K_INPUTS
        [--hashes threads-final.json]
    python examples/bench_df2.py compare REF_DIR OUT.json SYNTH_DIR SLICE_DIR K_INPUTS
    python examples/bench_df2.py time SET OUT.json --impl wgrid|ducc [--repeats N]
    python examples/bench_df2.py bench SET OUT_DIR [--impls wgrid,ducc]
        [--threads 1,4,16] [--repeats 3]

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
environment (it caps ducc0's pool) and `OPENBLAS_NUM_THREADS=1`.
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
    from rangtoy import core_zarr

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
    from rangtoy import core_wgridder

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
    f64 = [v["linf_rel_peak"] for k, v in res["outputs"].items() if "f64" in k]
    f32 = [v["linf_rel_peak"] for k, v in res["outputs"].items() if "f32" in k]
    res["worst_f64"] = max(f64) if f64 else None
    res["worst_f32"] = max(f32) if f32 else None
    res["pass_tolerance"] = bool(
        (not f64 or max(f64) <= 1e-13) and (not f32 or max(f32) <= 1e-5)
    )
    from rangtoy import core_wgridder

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
        from rangtoy import core_wgridder

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
