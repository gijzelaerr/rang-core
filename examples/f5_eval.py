"""F5: Stage 2's checks on validation (research/f5-flagger.md, sections 2c and
10), on nash.

Usage:
  python examples/f5_eval.py degree OUT.json --class calibrator|target --level L
  python examples/f5_eval.py stage2 OUT.json --class ... --level L --degree D --flags-from DIR

degree: the fit degree d from {1, 2, 3} (section 2c step 3): recall at |z| > 5
of F1's antenna-local injection (seeds 41-43) and of a 10 sigma T6 event 0.4
nchan wide (seed 20265501), among the d whose clean (antenna, block) pairs
with |z| > 5 are <= 1 %; ties to the lower d; none: d = 1.
stage2: ZE5's recall of F1's antenna-local injection (Stop-E below 0.5) and
Z5 against T on F2's injections (R1), added cells (R3, A from the cache) and
f2sim-v (S1, S2): Stop-Z.
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
from rang import f4flag as f4
from rang import f5flag as f5

Z_BAR = 5.0
DEGREE_SEEDS = (41, 42, 43)
T6_WIDE_SEED = 20265501


def zmag_cells(scan, ant):
    """(row, chan) largest |z| of the row's two antennas over both families."""
    ix = f3.index(scan)
    nt, nc = ix["nt"], scan["data"].shape[1]
    g = f5.grid(nt, nc)
    zabs = np.nanmax(np.abs(ant["z"]), axis=2)  # (nta, nja, nant)
    zabs = np.where(np.isfinite(zabs), zabs, 0.0)
    ta = g["ta"][ix["t"]]
    p = ix["ant1"][ix["bl"]]
    q = ix["ant2"][ix["bl"]]
    m = np.maximum(zabs[ta, :, p], zabs[ta, :, q])  # (row, nja)
    return np.repeat(m, f5.AMP_DF, axis=1)[:, :nc]


def wide_t6(scan, eligible, sigma, seed):
    inj = f5.Injector(
        scan, eligible, sigma, np.random.default_rng(seed), fixed=f3.STRENGTH
    )
    rng = inj.rng
    k = int(rng.choice(inj._live_antennas()))
    bsel = (inj.ix["ant1"] == k) | (inj.ix["ant2"] == k)
    w = int(0.4 * inj.nc)
    c0 = int(rng.integers(0, inj.nc - w + 1))
    inj.add("T6", bsel, inj._all_times(), np.arange(c0, c0 + w))
    rows, chans = np.nonzero(inj.amp > 0)
    return inj.data, rows, chans


def degree(a, out):
    (spec,) = f5.real_sets(a.klass, "validation")
    scan = f5.load(spec)
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    cases = [
        ("antenna-local", s, *f3.r1_case(scan, eligible, sigma, "antenna-local", s))
        for s in DEGREE_SEEDS
    ]
    cases.append(
        ("T6-0.4", T6_WIDE_SEED, *wide_t6(scan, eligible, sigma, T6_WIDE_SEED))
    )
    res = {"set": spec, "class": a.klass, "level": a.level, "per_degree": {}}
    for d in (1, 2, 3):
        t0 = time.perf_counter()
        clean = f5.rust_antenna(scan, w3, a.level, d)
        z = np.abs(clean["z"])
        fin = np.isfinite(z)
        frac = float((z[fin] > Z_BAR).mean()) if fin.any() else 1.0
        hit, n, per = 0, 0, []
        for name, s, data, rows, chans in cases:
            zc = zmag_cells(scan, f5.rust_antenna(scan, w3, a.level, d, data))
            h = int((zc[rows, chans] > Z_BAR).sum())
            per.append({"case": name, "seed": s, "cells": len(rows), "hit": h})
            hit += h
            n += len(rows)
        res["per_degree"][d] = {
            "clean_pairs_over_5": frac,
            "recall": hit / max(n, 1),
            "cases": per,
            "seconds": time.perf_counter() - t0,
        }
        print(json.dumps({"d": d, **res["per_degree"][d]}), flush=True)
    ok = [d for d in (1, 2, 3) if res["per_degree"][d]["clean_pairs_over_5"] <= 0.01]
    if ok:
        best = max(res["per_degree"][d]["recall"] for d in ok)
        res["degree"] = min(d for d in ok if res["per_degree"][d]["recall"] == best)
        res["rule"] = "largest recall among d with clean |z|>5 <= 1 %, ties to lower d"
    else:
        res["degree"] = 1
        res["rule"] = "none qualifies: d = 1"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({"degree": res["degree"], "rule": res["rule"]}))


def ze5_flags(scan, w3, level, d, data=None):
    zc = zmag_cells(scan, f5.rust_antenna(scan, w3, level, d, data))
    fl = w3 | (zc > Z_BAR)
    if level <= 1:
        fl |= f4.ze_flags(scan, w3, data)
    return fl


def z5_flags(scan, w3, level, d, data=None):
    return ze5_flags(scan, w3, level, d, data) | f3.z2_flags(scan, w3, data)


def stage2(a, out):
    klass = a.klass
    (spec,) = f5.real_sets(klass, "validation")
    scan = f5.load(spec)
    name = spec.replace(":", "-")
    w3 = f3.w3_flags(scan)
    eligible = ~w3
    sigma = f3.baseline_sigma(scan, eligible)
    a_flag = np.load(Path(a.flags_from) / klass / "flags" / f"{name}-A.npy")
    t_clean = f3.t_flags(scan)
    z5_clean = z5_flags(scan, w3, a.level, a.degree)
    added = {
        "T": int((t_clean & eligible).sum()),
        "A": int((a_flag & eligible).sum()),
        "Z5": int((z5_clean & eligible).sum()),
    }
    res = {
        "set": spec,
        "class": klass,
        "level": a.level,
        "degree": a.degree,
        "added": added,
    }
    r1 = {"T": [0, 0], "Z5": [0, 0]}
    ze = [0, 0]
    cases = []
    for m in f3.R1_MORPHOLOGIES:
        for s in f4.STOP_SEEDS:
            data, rows, chans = f3.r1_case(scan, eligible, sigma, m, s)
            t = f3.t_flags(scan, data)
            z5 = z5_flags(scan, w3, a.level, a.degree, data)
            c = {"morphology": m, "seed": s, "cells": len(rows)}
            c["T"], c["Z5"] = int(t[rows, chans].sum()), int(z5[rows, chans].sum())
            for k, acc in r1.items():
                acc[0] += c[k]
                acc[1] += len(rows)
            if m == "antenna-local":
                e5 = ze5_flags(scan, w3, a.level, a.degree, data)
                c["ZE5"] = int(e5[rows, chans].sum())
                ze[0] += c["ZE5"]
                ze[1] += len(rows)
            cases.append(c)
            print(json.dumps(c), flush=True)
    res["cases"] = cases
    res["ZE5_antenna_local_recall"] = ze[0] / max(ze[1], 1)
    res["stop_E"] = res["ZE5_antenna_local_recall"] < 0.5
    rt, rz = (r1[k][0] / max(r1[k][1], 1) for k in ("T", "Z5"))
    res["R1"] = {"T": rt, "Z5": rz}
    ratio = added["Z5"] / max(added["T"], 1)
    lower = 0.5 * min(added["T"], added["A"]) / max(added["T"], 1)
    res["R3_Z5"] = {"ratio": ratio, "lower": lower}
    total = {}
    for s in fs.scans_of(f3.F2_VAL, klass):
        sc = f3.load_fsim(s)
        sc["planes"] = ff.Planes(sc["antenna1"], sc["antenna2"], sc["times"])
        w = f3.w3_flags(sc)
        for k, fl in (
            ("T", f3.t_flags(sc)),
            ("Z5", z5_flags(sc, w, a.level, a.degree)),
        ):
            ff.add_counts(
                total.setdefault(k, {}), ff.truth_counts(sc, fl, sc["amp"], w)
            )
    sim = {k: ff.pooled(v) for k, v in total.items()}
    res["sim"] = {k: {"q1": v["q1"], "q2": v["q2"]} for k, v in sim.items()}
    res["stop_Z"] = bool(
        rz >= rt - 0.05
        and lower <= ratio <= 1.5
        and sim["Z5"]["q1"] >= sim["T"]["q1"] - 0.05
        and sim["Z5"]["q2"] <= sim["T"]["q2"] + 0.01
    )
    out.write_text(json.dumps(res, indent=1))
    keys = ("ZE5_antenna_local_recall", "stop_E", "R1", "R3_Z5", "sim", "stop_Z")
    print(json.dumps({k: res[k] for k in keys}))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("degree", "stage2"))
    p.add_argument("out")
    p.add_argument("--class", dest="klass", default="calibrator")
    p.add_argument("--level", type=int, default=0)
    p.add_argument("--degree", type=int, default=2)
    p.add_argument("--flags-from")
    p.add_argument("--data-root")
    a = p.parse_args()
    if a.data_root:
        f5.use_data_root(a.data_root)
    out = a.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    {"degree": degree, "stage2": stage2}[a.mode](a, out)


if __name__ == "__main__":
    main()
