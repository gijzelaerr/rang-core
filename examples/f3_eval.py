"""F3: the arms on real and simulated scans (research/f3-flagger.md, section 6).

Usage:
  python examples/f3_eval.py real OUT.json --set luno:MAIN_7|eso:10
         [--arms T,A,N3,Z2,U3,F2,N] [--cases r1,r2] [--r1-seeds 19,20,21]
         [--r2-seeds 31,32,33] [--n3 W.npz@TAU] [--f2 W.npz@TAU]
  python examples/f3_eval.py sim OUT.json OBS_DIR --class calibrator|target
         [--arms ...] [--n3 W.npz@TAU] [--f2 W.npz@TAU]

OUT `RUN/x.json` means $RUN_DIR/x.json. Real: added cells on uninjected DATA
(R3, R4) and injection recall per case (R1, R2). Sim: Q1, Q2, recall by
morphology (S1-S3). A runs AOFlagger in WSL Docker (scratch under $RUN_DIR).
"""

import argparse
import json
import os
import time
from pathlib import Path

from rang import f2flag as ff
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f3net

DEFAULT_F2 = {
    "calibrator": "D:/rang/outputs/f2-20261106-07-train-calibrator/calibrator-sim-1/weights.npz@-3.0",
    "target": "D:/rang/outputs/f2-20261106-08-train-target/target-sim-1/weights.npz@-6.0",
}


def net(spec):
    path, _, tau = spec.partition("@")
    return f3net.flat_weights(f3net.load_params(path)), float(tau or 0.0)


def make_arms(args, klass):
    arms = args.arms.split(",")
    n3 = net(args.n3) if args.n3 else None
    u3 = (f3net.flat_weights(f3net.init_params(0)), 0.0)
    f2 = ff.load_net(args.f2 or DEFAULT_F2[klass])
    f2_shared = ff.shared_strategy(klass)
    work = Path(os.environ.get("RUN_DIR", ".")) / "aoflag"

    def run(scan, w3, data, tag):
        out, secs = {}, {}
        for arm in arms:
            t = time.perf_counter()
            if arm == "T":
                out[arm] = f3.t_flags(scan, data)
            elif arm == "N":
                out[arm] = w3
            elif arm == "A":
                out[arm], rec = f3.a_flags(scan, w3, work / tag, data)
                secs["A_container"] = rec["seconds"]
            elif arm == "Z2":
                out[arm] = f3.z2_flags(scan, w3, data)
            elif arm == "N3":
                out[arm] = f3.n3_flags(scan, w3, n3[0], n3[1], data)[0]
            elif arm == "U3":
                out[arm] = f3.n3_flags(scan, w3, u3[0], u3[1], data)[0]
            elif arm == "F2":
                sc = dict(scan, data=scan["data"] if data is None else data)
                shared = ff.run_strategy(sc, f2_shared, scan["input_flags"])[0]
                out[arm] = ff.network_flags(sc, shared, *f2)[0]
            else:
                raise ValueError(arm)
            secs[arm] = time.perf_counter() - t
        return out, secs

    return arms, run


def load_set(spec):
    kind, _, name = spec.partition(":")
    if kind == "luno":
        return f3.load_luno(name)
    if kind == "eso":
        return f3.load_eso(int(name))
    raise ValueError(spec)


def real(args, out):
    scan = load_set(args.set)
    klass = scan["klass"]
    arms, run = make_arms(args, klass)
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    result = {
        "set": args.set,
        "class": klass,
        "rows": len(scan["times"]),
        "cells": int(eligible.size),
        "input_flagged": float(scan["input_flags"].any(-1).mean()),
        "eligible": int(eligible.sum()),
        "n3": args.n3,
        "f2": args.f2 or DEFAULT_F2[klass],
        "uninjected": {},
        "cases": [],
    }
    flags, secs = run(scan, w3, None, "clean")
    added = {a: flags[a] & eligible for a in arms}
    for a in arms:
        result["uninjected"][a] = {"added": int(added[a].sum()), "seconds": secs[a]}
    if "T" in arms:
        for a in arms:
            if a != "T":
                result["uninjected"][a]["J_T"] = f3.jaccard(added[a], added["T"])
                result["uninjected"][a]["ratio_T"] = int(added[a].sum()) / max(
                    int(added["T"].sum()), 1
                )
    if "A" in secs:
        result["uninjected"]["A"]["container_seconds"] = secs["A_container"]
    print(json.dumps(result["uninjected"]), flush=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    cases = []
    if "r1" in args.cases:
        for m in f3.R1_MORPHOLOGIES:
            for s in [int(x) for x in args.r1_seeds.split(",")]:
                cases.append(("r1", m, s))
    if "r2" in args.cases:
        for m in f3.HELD_OUT:
            for s in [int(x) for x in args.r2_seeds.split(",")]:
                cases.append(("r2", m, s))
    for kind, m, s in cases:
        if kind == "r1":
            data, rows, chans = f3.r1_case(scan, eligible, sigma, m, s)
        else:
            data, rows, chans = f3.r2_case(scan, eligible, sigma, m, s)
        flags, secs = run(scan, w3, data, f"{kind}-{m}-{s}")
        case = {"kind": kind, "morphology": m, "seed": s, "cells": len(rows)}
        for a in arms:
            case[a] = int(flags[a][rows, chans].sum())
        result["cases"].append(case)
        print(json.dumps(case), flush=True)
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")


def sim(args, out):
    klass = args.klass
    arms, run = make_arms(args, klass)
    total = {}
    per_scan = []
    for s in fs.scans_of(args.obs, klass):
        scan = f3.load_fsim(s)
        scan["planes"] = ff.Planes(scan["antenna1"], scan["antenna2"], scan["times"])
        w3 = f3.w3_flags(scan)
        flags, secs = run(scan, w3, None, Path(s.path).name)
        rec = {"scan": str(s.path), "seconds": secs}
        for a in arms:
            c = ff.truth_counts(scan, flags[a], scan["amp"], w3, scan["morph"])
            ff.add_counts(total.setdefault(a, {}), c)
            rec[a] = ff.pooled(c)["q1"]
        per_scan.append(rec)
        print(json.dumps(rec), flush=True)
    result = {
        "obs": str(args.obs),
        "class": klass,
        "n3": args.n3,
        "arms": {a: ff.pooled(v) for a, v in total.items()},
        "counts": total,
        "scans": per_scan,
    }
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({a: (v["q1"], v["q2"]) for a, v in result["arms"].items()}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("real", "sim"))
    parser.add_argument("out")
    parser.add_argument("obs", nargs="?")
    parser.add_argument("--set")
    parser.add_argument("--class", dest="klass", default="calibrator")
    parser.add_argument("--arms", default="T,A,N3,Z2,U3,F2,N")
    parser.add_argument("--cases", default="r1,r2")
    parser.add_argument("--r1-seeds", default="19,20,21")
    parser.add_argument("--r2-seeds", default="31,32,33")
    parser.add_argument("--n3")
    parser.add_argument("--f2")
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    {"real": real, "sim": sim}[args.mode](args, out)


if __name__ == "__main__":
    main()
