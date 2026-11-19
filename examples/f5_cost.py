"""F5 cost (research/f5-flagger.md, sections 2e and 10): paired, alternating
repeats of T (`flag_rows`, full first-pass YAML) and the F5 arm (W3 +
`f5flag_logits` + threshold, OR W4 if given), rows in memory to flags in
memory, other processes' CPU measured over each repeat.

Usage:
  python examples/f5_cost.py pairs OUT.json --set luno:MAIN_1 --arm U5|W.npz@TAU
         [--level 0] [--degree 2] [--kappa K] [--pairs 5] [--gate]
  python examples/f5_cost.py rss OUT.json --set ... --which T|F5 --arm ...

One process per thread count (RAYON_NUM_THREADS). A pair is clean if both
repeats saw at most one other logical CPU on average. C1 is the median of the
paired ratios over the clean pairs if at least 3 are clean, else over all
(provisional). `--gate` first samples 10 s of CPU and exits 4 if other
processes use more than one logical CPU (the caller retries later).
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import psutil
from rang import f3flag as f3
from rang import f5flag as f5
from rang import f5net


def busy_seconds():
    t = psutil.cpu_times()
    return sum(t) - t.idle - getattr(t, "iowait", 0.0)


def own_seconds(me):
    t = me.cpu_times()
    return t.user + t.system


def other_cpus(fn):
    """Run fn; return (result, wall, other logical CPUs on average)."""
    me = psutil.Process()
    b0, o0, t0 = busy_seconds(), own_seconds(me), time.perf_counter()
    r = fn()
    wall = time.perf_counter() - t0
    b1, o1 = busy_seconds(), own_seconds(me)
    return r, wall, max((b1 - b0) - (o1 - o0), 0.0) / max(wall, 1e-9)


def arm_weights(spec, level):
    if spec == "U5":
        return f5net.flat_from_arrays(
            f5net.init_arrays(0, f5.nplanes(level), True)
        ), 0.0
    path, _, tau = spec.partition("@")
    z = np.load(path)
    return np.asarray(z["flat"], np.float32), float(tau or 0.0)


def make_arm(args):
    w, tau = arm_weights(args.arm, args.level)

    def run(scan):
        w3 = f3.w3_flags(scan)
        return f5.method_flags(scan, w3, w, tau, args.kappa, args.level, args.degree)

    return run


def pairs(args, out):
    if args.gate:
        _, _, other = other_cpus(lambda: time.sleep(10.0))
        if other > 1.0:
            out.write_text(json.dumps({"gate_other_cpus": other, "skipped": True}))
            raise SystemExit(4)
    scan = f5.load(args.set)
    run = make_arm(args)
    rec = {
        "set": args.set,
        "threads": os.environ.get("RAYON_NUM_THREADS"),
        "arm": args.arm,
        "level": args.level,
        "degree": args.degree,
        "kappa": args.kappa,
        "rows": len(scan["times"]),
        "cells": int(scan["data"].shape[0] * scan["data"].shape[1]),
        "pairs": [],
    }
    for k in range(args.pairs):
        pr = {}
        for name, fn in (("T", lambda: f3.t_flags(scan)), ("F5", lambda: run(scan))):
            flags, wall, other = other_cpus(fn)
            pr[name] = {
                "wall": wall,
                "other_cpus": other,
                "clean": other <= 1.0,
                "flagged": float(flags.mean()),
            }
        pr["ratio"] = pr["F5"]["wall"] / pr["T"]["wall"]
        pr["clean"] = pr["T"]["clean"] and pr["F5"]["clean"]
        rec["pairs"].append(pr)
        print(json.dumps({"pair": k, **pr}), flush=True)
        out.write_text(json.dumps(rec, indent=1))
    clean = [p["ratio"] for p in rec["pairs"] if p["clean"]]
    used = clean if len(clean) >= 3 else [p["ratio"] for p in rec["pairs"]]
    q25, med, q75 = (float(x) for x in np.quantile(used, [0.25, 0.5, 0.75]))
    rec.update(
        clean_pairs=len(clean),
        provisional=len(clean) < 3,
        c1=med,
        q25=q25,
        q75=q75,
        reading=(
            "beats"
            if q75 <= 0.5
            else "at the bar"
            if med <= 0.5
            else "matches"
            if med <= 1.1
            else "worse"
        ),
    )
    out.write_text(json.dumps(rec, indent=1))
    print(
        json.dumps({k: rec[k] for k in ("c1", "q25", "q75", "clean_pairs", "reading")})
    )


def rss(args, out):
    scan = f5.load(args.set)
    if args.which == "T":
        f3.t_flags(scan)
    else:
        make_arm(args)(scan)
    info = psutil.Process().memory_info()
    peak = getattr(info, "peak_wset", None) or getattr(info, "rss", 0)
    out.write_text(
        json.dumps({"set": args.set, "which": args.which, "peak_bytes": peak})
    )
    print(peak)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("pairs", "rss"))
    p.add_argument("out")
    p.add_argument("--set", required=True)
    p.add_argument("--arm", default="U5")
    p.add_argument("--level", type=int, default=0)
    p.add_argument("--degree", type=int, default=2)
    p.add_argument("--kappa", type=float)
    p.add_argument("--pairs", type=int, default=5)
    p.add_argument("--gate", action="store_true")
    p.add_argument("--which", default="T")
    args = p.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    {"pairs": pairs, "rss": rss}[args.mode](args, out)


if __name__ == "__main__":
    main()
