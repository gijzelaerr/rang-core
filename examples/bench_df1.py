"""Cost of big-plan task DF1's exact gridder against P2's w-stacking and ducc0
(research/df1-wgridder.md).

    python examples/bench_df1.py time INPUTS OUT.json --impl wstack|wgrid|ducc
        [--tile N] [--labels A,B] [--epsilon 1e-6] [--single] [--repeats N]
    python examples/bench_df1.py bench INPUTS OUT_DIR [--impls wstack,wgrid,ducc]
        [--threads 1,4,16] [--tile N] [--labels ...] [--repeats N]

INPUTS holds P2's gridder input files (`bench_p2_gridder.py c-inputs`,
`k-replay --dump-inputs`). One image is a dirty image and its PSF: one
`core_grid.invert` call for w-stacking (it forms both in one pass), two
`vis2dirty` calls for the exact gridder (`core_wgridder.fits_image`, f64
unless `--single`) and for ducc0 (`nthreads` = `RAYON_NUM_THREADS`). `time`
measures every input in this process (wall, process CPU, peak RSS, output
SHA256, load); `bench` runs `time` in a fresh process per (implementation,
thread count) with `RAYON_NUM_THREADS` and `OPENBLAS_NUM_THREADS=1`.
"""

import argparse
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

import bench_p2_gridder as p2


def one_image(impl, inputs, settings, epsilon, single):
    if impl == "wstack":
        from rang import core_grid

        r = core_grid.invert(**inputs, **settings)
        return r["dirty"], r["psf"]
    weights = inputs["weights"] * inputs["imaging_weights"]
    if impl == "wgrid":
        from rang import core_wgridder

        r = core_wgridder.fits_image(
            inputs["uvw"],
            inputs["frequencies"],
            inputs["data"],
            weights,
            settings["width"],
            settings["height"],
            settings["scale_arcsec"],
            epsilon=epsilon,
            single=single,
        )
        return r["dirty"], r["psf"]
    import ducc0

    cdt = np.complex64 if single else np.complex128
    rdt = np.float32 if single else np.float64
    cell = settings["scale_arcsec"] * np.pi / 648000.0
    common = {
        "uvw": inputs["uvw"],
        "freq": inputs["frequencies"],
        "wgt": weights.astype(rdt),
        "npix_x": settings["width"],
        "npix_y": settings["height"],
        "pixsize_x": cell,
        "pixsize_y": cell,
        "epsilon": epsilon,
        "do_wgridding": True,
        "nthreads": int(os.environ.get("RAYON_NUM_THREADS", "1")),
        "flip_v": True,
        "divide_by_n": False,
    }
    d = ducc0.wgridder.vis2dirty(vis=inputs["data"].astype(cdt), **common)
    p = ducc0.wgridder.vis2dirty(vis=np.ones(inputs["data"].shape, cdt), **common)
    c = p[settings["width"] // 2, settings["height"] // 2]
    return d.T / c, p.T / c


def cmd_time(args):
    load_before = os.getloadavg()
    labels = args.labels.split(",") if args.labels else None
    items = p2._load_inputs(args.inputs, labels, args.tile)
    loaded = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    records = []
    for repeat in range(args.repeats):
        for label, inputs, settings in items:
            w0, c0 = time.perf_counter(), time.process_time()
            dirty, psf = one_image(
                args.impl, inputs, settings, args.epsilon, args.single
            )
            wall = time.perf_counter() - w0
            records.append(
                {
                    "repeat": repeat,
                    "label": label,
                    "cells": int(inputs["data"].size),
                    "wall": wall,
                    "cpu": time.process_time() - c0,
                    "dirty_sha256": p2.sha256_array(np.ascontiguousarray(dirty)),
                    "psf_sha256": p2.sha256_array(np.ascontiguousarray(psf)),
                }
            )
            print(f"{args.impl} {label:32s} r{repeat} wall {wall:7.3f}s", flush=True)
    result = {
        "impl": args.impl,
        "epsilon": args.epsilon,
        "single": args.single,
        "rayon_num_threads": os.environ.get("RAYON_NUM_THREADS"),
        "tile": args.tile,
        "records": records,
        "max_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "rss_mb_after_loading_inputs": loaded,
        "loadavg_before_after": [load_before, os.getloadavg()],
    }
    Path(args.out).write_text(json.dumps(result, indent=1))


def cmd_bench(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    summary = []
    for repeat in range(args.repeats):
        for threads in args.threads.split(","):
            for impl in args.impls.split(","):
                env = dict(
                    os.environ, RAYON_NUM_THREADS=threads, OPENBLAS_NUM_THREADS="1"
                )
                path = out / f"{impl}-t{threads}-r{repeat}.json"
                cmd = [
                    sys.executable,
                    __file__,
                    "time",
                    args.inputs,
                    str(path),
                    "--impl",
                    impl,
                ]
                cmd += ["--tile", str(args.tile), "--epsilon", str(args.epsilon)]
                if args.labels:
                    cmd += ["--labels", args.labels]
                if args.single:
                    cmd.append("--single")
                subprocess.run(cmd, env=env, check=True)
                rec = json.loads(path.read_text())
                walls = [r["wall"] for r in rec["records"]]
                cpus = [r["cpu"] for r in rec["records"]]
                summary.append(
                    {
                        "impl": impl,
                        "threads": int(threads),
                        "repeat": repeat,
                        "images": len(walls),
                        "wall_per_image_median": float(np.median(walls)),
                        "wall_per_image_min": float(np.min(walls)),
                        "cpu_per_image_median": float(np.median(cpus)),
                        "max_rss_mb": rec["max_rss_mb"],
                        "rss_mb_after_loading_inputs": rec[
                            "rss_mb_after_loading_inputs"
                        ],
                        "loadavg_before_after": rec["loadavg_before_after"],
                    }
                )
                print(json.dumps(summary[-1]), flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("time")
    t.add_argument("inputs")
    t.add_argument("out")
    t.add_argument("--impl", choices=("wstack", "wgrid", "ducc"), required=True)
    for q in (t,):
        q.add_argument("--tile", type=int, default=1)
        q.add_argument("--labels", default=None)
        q.add_argument("--epsilon", type=float, default=1e-6)
        q.add_argument("--single", action="store_true")
        q.add_argument("--repeats", type=int, default=1)
    t.set_defaults(func=cmd_time)
    b = sub.add_parser("bench")
    b.add_argument("inputs")
    b.add_argument("out")
    b.add_argument("--impls", default="wstack,wgrid,ducc")
    b.add_argument("--threads", default="1,4,16")
    b.add_argument("--tile", type=int, default=1)
    b.add_argument("--labels", default=None)
    b.add_argument("--epsilon", type=float, default=1e-6)
    b.add_argument("--single", action="store_true")
    b.add_argument("--repeats", type=int, default=1)
    b.set_defaults(func=cmd_bench)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
