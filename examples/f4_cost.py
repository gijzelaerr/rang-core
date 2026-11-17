"""F4 cost (research/f4-flagger.md, section 6): C1 wall and C2 peak working set,
N4 (W3 + the Rust kernel + threshold) against T (`flag_rows`, full YAML).

Usage:
  python examples/f4_cost.py time OUT.json --set luno:MAIN_1|eso:0 --n4 W.npz@TAU|U4 [--repeats 3]
  python examples/f4_cost.py rss OUT.json --set ... --arm T|N4 --n4 W.npz@TAU

`--n4 U4` times the untrained weights (init seed 0, tau 0): Stage 2's C1(U4).

One process per thread count (RAYON_NUM_THREADS). Before each repeat psutil
samples system CPU for 1 s; other processes' share (total minus this
process) above one logical CPU makes the repeat provisional.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import psutil
from rang import f3flag as f3
from rang import f3net
from rang import f4flag as f4


def load(spec):
    return f4.load(spec)


def other_cpu():
    """Logical CPUs busy outside this process over 1 s."""
    me = psutil.Process()
    me.cpu_percent(None)
    total = psutil.cpu_percent(interval=1.0)
    mine = me.cpu_percent(None)  # percent of one CPU
    n = psutil.cpu_count()
    return max(total * n / 100 - mine / 100, 0.0)


def arm(scan, name, weights, tau):
    if name == "T":
        return f3.t_flags(scan)
    w3 = f3.w3_flags(scan)
    return f4.n4_flags(scan, w3, weights, tau)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("time", "rss"))
    parser.add_argument("out")
    parser.add_argument("--set", required=True)
    parser.add_argument("--n4", required=True)
    parser.add_argument("--arm", default="T")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    out = (
        Path(os.environ["RUN_DIR"]) / args.out[4:]
        if args.out.startswith("RUN/")
        else Path(args.out)
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.n4 == "U4":
        weights, tau = f3net.flat_weights(f3net.init_params(0, f4.NPLANES)), 0.0
    else:
        path, _, tau = args.n4.partition("@")
        weights = f3net.flat_weights(f3net.load_params(path))
        tau = float(tau or 0)
    scan = load(args.set)
    if args.mode == "rss":
        before = psutil.Process().memory_info().peak_wset
        t = time.perf_counter()
        f = arm(scan, args.arm, weights, tau)
        res = {
            "arm": args.arm,
            "set": args.set,
            "wall": time.perf_counter() - t,
            "peak_wset_after_decode": before,
            "peak_wset": psutil.Process().memory_info().peak_wset,
            "flagged": float(f.mean()),
        }
        out.write_text(json.dumps(res, indent=1))
        print(json.dumps(res))
        return
    records = {"T": [], "N4": []}
    for k in range(args.repeats):
        for name in ("T", "N4") if k % 2 == 0 else ("N4", "T"):
            busy = other_cpu()
            t = time.perf_counter()
            f = arm(scan, name, weights, tau)
            records[name].append(
                {
                    "wall": time.perf_counter() - t,
                    "other_cpus": busy,
                    "clean": busy <= 1.0,
                    "flagged": float(f.mean()),
                }
            )
            print(name, json.dumps(records[name][-1]), flush=True)
    med = {a: float(np.median([r["wall"] for r in v])) for a, v in records.items()}
    res = {
        "set": args.set,
        "threads": os.environ.get("RAYON_NUM_THREADS"),
        "n4": args.n4,
        "rows": len(scan["times"]),
        "cells": int(scan["data"].shape[0] * scan["data"].shape[1]),
        "records": records,
        "median_wall": med,
        "c1": med["N4"] / med["T"],
        "all_clean": all(r["clean"] for v in records.values() for r in v),
    }
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("median_wall", "c1", "all_clean")}))


if __name__ == "__main__":
    main()
