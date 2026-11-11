"""F4: Stage 1's stop rules and the arms on held-out scans (research/f4-flagger.md,
sections 6-8).

Usage:
  python examples/f4_eval.py stage1 OUT.json --class calibrator|target --flags-from DIR
  python examples/f4_eval.py real OUT.json --set luno:MAIN_0|eso:11 --heldout
         [--arms T,A,N4,N3,Z4,ZE,U4,N] [--cases r1,r2] [--n4 W.npz@TAU] [--n3 W.npz@TAU]
  python examples/f4_eval.py sim OUT.json OBS_DIR --class calibrator|target
         [--arms ...] [--n4 W.npz@TAU] [--n3 W.npz@TAU]
  python examples/f4_eval.py na-delta OUT.json --class calibrator|target
  (real with --arms ...,NA,N4NA --na-delta D adds arm NA, Amendment 1: G1-G3)

stage1: on the class's real validation scan, ZE's recall of F1's antenna-local
injection (seeds 41-43; Stop-E below 0.5), and Z4 against T on F2's injections
(seeds 41-43), added cells (R3 with A from the cache in --flags-from) and on
f2sim-v (S1, S2): Stop-Z4. real: the W3 subset check, added cells (R3, R4),
strong native consensus recall (R5), injection recall per case (R1, R2 with
H1-H3). sim: Q1, Q2, by morphology (S1, S2) and S3 (drifting, or H1 at 10
sigma, seeds 61-63, if the class has fewer than 1,000 drifting cells at A >= 10).
OUT `RUN/x.json` means $RUN_DIR/x.json.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs
from rang import f3flag as f3
from rang import f3net
from rang import f4flag as f4

N3_DEFAULT = {
    "calibrator": "D:/rang/outputs/f3-20261110-17-train-calibrator/seed-3/weights.npz@-2.5",
    "target": "D:/rang/outputs/f3-20261110-15-train-target/seed-1/weights.npz@-4.0",
}
S3_MIN = 1000


def net(spec):
    path, _, tau = spec.partition("@")
    return f3net.flat_weights(f3net.load_params(path)), float(tau or 0.0)


def make_arms(args, klass):
    arms = args.arms.split(",")
    n4 = net(args.n4) if args.n4 else None
    n3 = net(args.n3 or N3_DEFAULT[klass]) if "N3" in arms else None
    u4 = (f3net.flat_weights(f3net.init_params(0, f4.NPLANES)), 0.0)
    if {"NA", "N4NA"} & set(arms) and args.na_delta is None:
        raise SystemExit("NA arms need --na-delta (from `na-delta` on validation)")
    work = Path(os.environ.get("RUN_DIR", ".")) / "aoflag"

    def run(scan, w3, data, tag, autos=None):
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
            elif arm == "Z4":
                out[arm] = f4.z4_flags(scan, w3, data)
            elif arm == "ZE":
                out[arm] = f4.ze_flags(scan, w3, data)
            elif arm == "N4":
                out[arm] = f4.n4_flags(scan, w3, n4[0], n4[1], data)[0]
            elif arm == "U4":
                out[arm] = f4.n4_flags(scan, w3, u4[0], u4[1], data)[0]
            elif arm == "NA":
                out[arm] = f4.na_flags(scan, autos, w3, args.na_delta)
            elif arm == "N4NA":
                n4f = out["N4"] if "N4" in out else f4.n4_flags(scan, w3, *n4, data)[0]
                out[arm] = n4f | f4.na_flags(scan, autos, w3, args.na_delta)
            elif arm == "N3":
                out[arm] = f3.n3_flags(scan, w3, n3[0], n3[1], data)[0]
            else:
                raise ValueError(arm)
            secs[arm] = time.perf_counter() - t
        return out, secs

    return arms, run


def recall(flags, rows, chans):
    return int(flags[rows, chans].sum())


def spectral_fractions(scan, w3, block=128):
    """Reported only: fraction of eligible cells with e^par, e^x >= 3 and >= 5
    on uninjected DATA (how much of the spectral planes is bandpass)."""
    ix = f3.index(scan)
    nbl = len(ix["ubl"])
    counts = {f"{fam}_ge{b}": 0 for fam in ("par", "cross") for b in (3, 5)}
    n = 0
    for s in range(0, nbl, block):
        sel = np.arange(s, min(s + block, nbl))
        x = f4.rust_features(scan, w3, sel)
        ok = x[..., f4.NPLANES - 1] == 0
        n += int(ok.sum())
        for fam, k in (("par", f4.SPEC0), ("cross", f4.SPEC0 + 4)):
            v = np.sinh(x[..., k])[ok]
            for b in (3, 5):
                counts[f"{fam}_ge{b}"] += int((v >= b).sum())
    return {k: v / max(n, 1) for k, v in counts.items()}


def stage1(args, out):
    klass = args.klass
    (spec,) = f4.real_sets(klass, "validation")
    scan = f4.load(spec)
    name = spec.replace(":", "-")
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    cache = Path(args.flags_from) / klass / "flags"
    a_flag = np.load(cache / f"{name}-A.npy")
    t_clean = f3.t_flags(scan)
    z4_clean = f4.z4_flags(scan, w3)
    res = {"set": spec, "class": klass, "eligible": int(eligible.sum())}
    added = {
        "T": int((t_clean & eligible).sum()),
        "A": int((a_flag & eligible).sum()),
        "Z4": int((z4_clean & eligible).sum()),
    }
    res["added"] = added
    res["spectral_clean"] = spectral_fractions(scan, w3)
    hits = {"ZE": [0, 0]}
    r1 = {"T": [0, 0], "Z4": [0, 0]}
    cases = []
    for m in f3.R1_MORPHOLOGIES:
        for s in f4.STOP_SEEDS:
            data, rows, chans = f3.r1_case(scan, eligible, sigma, m, s)
            t = f3.t_flags(scan, data)
            z4 = f4.z4_flags(scan, w3, data)
            c = {"morphology": m, "seed": s, "cells": len(rows)}
            c["T"], c["Z4"] = recall(t, rows, chans), recall(z4, rows, chans)
            for a in ("T", "Z4"):
                r1[a][0] += c[a]
                r1[a][1] += len(rows)
            if m == "antenna-local":
                ze = f4.ze_flags(scan, w3, data)
                c["ZE"] = recall(ze, rows, chans)
                hits["ZE"][0] += c["ZE"]
                hits["ZE"][1] += len(rows)
            cases.append(c)
            print(json.dumps(c), flush=True)
    res["cases"] = cases
    ze_rec = hits["ZE"][0] / max(hits["ZE"][1], 1)
    res["ZE_antenna_local_recall"] = ze_rec
    res["stop_E"] = ze_rec < 0.5
    rt, rz = (r1[a][0] / max(r1[a][1], 1) for a in ("T", "Z4"))
    res["R1"] = {"T": rt, "Z4": rz}
    ratio = added["Z4"] / max(added["T"], 1)
    lower = 0.5 * min(added["T"], added["A"]) / max(added["T"], 1)
    res["R3_Z4"] = {"ratio": ratio, "lower": lower}
    total = {}
    for s in fs.scans_of(f3.F2_VAL, klass):
        sc = f3.load_fsim(s)
        sc["planes"] = ff.Planes(sc["antenna1"], sc["antenna2"], sc["times"])
        w = f3.w3_flags(sc)
        for a, fl in (("T", f3.t_flags(sc)), ("Z4", f4.z4_flags(sc, w))):
            ff.add_counts(
                total.setdefault(a, {}), ff.truth_counts(sc, fl, sc["amp"], w)
            )
    sim = {a: ff.pooled(v) for a, v in total.items()}
    res["sim"] = {a: {"q1": v["q1"], "q2": v["q2"]} for a, v in sim.items()}
    meets = (
        rz >= rt - 0.05
        and lower <= ratio <= 1.5
        and sim["Z4"]["q1"] >= sim["T"]["q1"] - 0.05
        and sim["Z4"]["q2"] <= sim["T"]["q2"] + 0.01
    )
    res["stop_Z4"] = bool(meets)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                k: res[k]
                for k in (
                    "ZE_antenna_local_recall",
                    "stop_E",
                    "R1",
                    "R3_Z4",
                    "sim",
                    "stop_Z4",
                )
            }
        )
    )


def real(args, out):
    scan = f4.load(args.set, heldout=args.heldout)
    klass = scan["klass"]
    arms, run = make_arms(args, klass)
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    s_rows = f4.strength_rows(scan, w3)
    result = {
        "set": args.set,
        "class": klass,
        "rows": len(scan["times"]),
        "cells": int(eligible.size),
        "eligible": int(eligible.sum()),
        "n4": args.n4,
        "n3": args.n3 or N3_DEFAULT[klass],
        "uninjected": {},
        "cases": [],
    }
    autos = f4.load_autos(args.set, scan, args.heldout) if args.na_delta else None
    flags, secs = run(scan, w3, None, "clean", autos)
    if "T" in arms:
        result["w3_not_in_T"] = int((w3 & ~flags["T"]).sum())
        if result["w3_not_in_T"]:
            out.write_text(json.dumps(result, indent=1), encoding="utf-8")
            raise SystemExit("W3 is not a subset of T: stop (section 8, Stage 5)")
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
    if "T" in arms and "A" in arms:
        strong = f4.strong_consensus(flags["T"], flags["A"], eligible, s_rows)
        result["strong_consensus_cells"] = int(strong.sum())
        for a in arms:
            result["uninjected"][a]["R5"] = (
                float((flags[a] & strong).sum() / strong.sum())
                if strong.any()
                else None
            )
    if "A" in secs:
        result["uninjected"]["A"]["container_seconds"] = secs["A_container"]
    if autos is not None:
        result["NA_G2"] = g2(scan, args.set, w3, autos, args.na_delta, args.heldout)
        if "T" in arms and "A" in arms and {"N4", "N4NA"} <= set(arms):
            hit = f4.na_antenna_hits(autos, args.na_delta).any(axis=(1, 2))
            ix = f3.index(scan)
            touched = (hit[scan["antenna1"]] | hit[scan["antenna2"]])[:, None]
            g3 = strong & touched
            result["NA_G3_cells"] = int(g3.sum())
            for a in ("N4", "N4NA"):
                result["uninjected"][a]["G3_recall"] = (
                    float((flags[a] & g3).sum() / g3.sum()) if g3.any() else None
                )
            del ix
    print(json.dumps(result["uninjected"]), flush=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    cases = []
    if "r1" in args.cases:
        for m in f3.R1_MORPHOLOGIES:
            for s in [int(x) for x in args.r1_seeds.split(",")]:
                cases.append(("r1", m, s))
    if "r2" in args.cases:
        for m in f4.HELD_OUT:
            for s in [int(x) for x in args.r2_seeds.split(",")]:
                cases.append(("r2", m, s))
    for kind, m, s in cases:
        if kind == "r1":
            data, rows, chans = f3.r1_case(scan, eligible, sigma, m, s)
        else:
            data, rows, chans = f4.r2_case(scan, eligible, sigma, m, s)
        flags, secs = run(scan, w3, data, f"{kind}-{m}-{s}", autos)
        case = {"kind": kind, "morphology": m, "seed": s, "cells": len(rows)}
        for a in arms:
            case[a] = recall(flags[a], rows, chans)
        result["cases"].append(case)
        print(json.dumps(case), flush=True)
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")


def na_delta(args, out):
    """Amendment 1: delta on the class's real validation scan (smallest delta
    whose added cells are <= T's), and G2 there as a check of the code."""
    (spec,) = f4.real_sets(args.klass, "validation")
    scan = f4.load(spec)
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    autos = f4.load_autos(spec, scan)
    t_added = int((f3.t_flags(scan) & eligible).sum())
    added = {
        d: int((f4.na_flags(scan, autos, w3, d) & eligible).sum()) for d in f4.NA_DELTAS
    }
    ok = [d for d in f4.NA_DELTAS if added[d] <= t_added]
    delta = min(ok) if ok else max(f4.NA_DELTAS)
    res = {"set": spec, "T_added": t_added, "added": added, "delta": delta}
    res["rule"] = "smallest with added <= T" if ok else "none qualifies: largest"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res))


def g2(scan, spec, w3, autos, delta, heldout):
    """G2: NA's antenna-domain recall of F1's antenna-local choice, injected
    into the autos (seeds 19-21)."""
    from rang.core_injection_model import make_injection

    eligible = ~w3
    state = {
        "data": scan["data"],
        "train": eligible,
        "validation": np.zeros_like(eligible),
        "test": np.zeros_like(eligible),
        "original_flags": scan["input_flags"],
        "original_rows": scan["input_flags"].all(axis=(1, 2)),
        "antenna1": scan["antenna1"],
        "antenna2": scan["antenna2"],
        "times": scan["times"],
        "weights": np.ones(scan["data"].shape, np.float32),
        "window": np.ones(eligible.shape[1], bool),
    }
    hits, n = 0, 0
    for seed in f3.R1_SEEDS:
        _, _, meta = make_injection(state, "antenna-local", 1.0, seed)
        chans = np.arange(*meta["channels"])
        inj = f4.auto_inject(autos, chans, meta["antenna"])
        hit = f4.na_antenna_hits(inj, delta)[meta["antenna"]][:, chans]
        hits += int(hit.sum())
        n += hit.size
    return hits / max(n, 1)


def sim(args, out):
    klass = args.klass
    arms, run = make_arms(args, klass)
    total = {}
    per_scan = []
    scans = fs.scans_of(args.obs, klass)
    drifting = 0
    for s in scans:
        scan = f3.load_fsim(s)
        scan["planes"] = ff.Planes(scan["antenna1"], scan["antenna2"], scan["times"])
        w3 = f3.w3_flags(scan)
        drifting += int(((scan["morph"] == 8) & (scan["amp"] >= 10) & ~w3).sum())
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
        "n4": args.n4,
        "arms": {a: ff.pooled(v) for a, v in total.items()},
        "counts": total,
        "scans": per_scan,
        "drifting_cells_ge10": drifting,
    }
    if drifting < S3_MIN:
        # S3 fallback (section 6): H1 at 10 sigma into the class's scans.
        s3 = {a: [0, 0] for a in arms}
        for s in scans:
            scan = f3.load_fsim(s)
            w3 = f3.w3_flags(scan)
            sigma = f3.baseline_sigma(scan, ~w3)
            for seed in f4.S3_SEEDS:
                data, rows, chans = f4.r2_case(scan, ~w3, sigma, "H1", seed)
                flags, _ = run(scan, w3, data, f"s3-{Path(s.path).name}-{seed}")
                for a in arms:
                    s3[a][0] += recall(flags[a], rows, chans)
                    s3[a][1] += len(rows)
        result["S3_fallback"] = {a: v[0] / max(v[1], 1) for a, v in s3.items()}
        result["S3_fallback_cells"] = {a: v[1] for a, v in s3.items()}
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({a: (v["q1"], v["q2"]) for a, v in result["arms"].items()}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("stage1", "real", "sim", "na-delta"))
    parser.add_argument("out")
    parser.add_argument("obs", nargs="?")
    parser.add_argument("--set")
    parser.add_argument("--heldout", action="store_true")
    parser.add_argument("--class", dest="klass", default="calibrator")
    parser.add_argument("--arms", default="T,A,N4,N3,Z4,ZE,U4,N")
    parser.add_argument("--cases", default="r1,r2")
    parser.add_argument("--r1-seeds", default="19,20,21")
    parser.add_argument("--r2-seeds", default="31,32,33")
    parser.add_argument("--n4")
    parser.add_argument("--n3")
    parser.add_argument("--flags-from")
    parser.add_argument("--na-delta", type=float)
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    modes = {"stage1": stage1, "real": real, "sim": sim, "na-delta": na_delta}
    modes[args.mode](args, out)


if __name__ == "__main__":
    main()
