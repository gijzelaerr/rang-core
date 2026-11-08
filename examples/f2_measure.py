"""F2: Q1-Q3 of the arms on F-SIM observations (research/f2-flagger.md, section 5).

Usage: python examples/f2_measure.py OUT.json OBS_DIR [OBS_DIR ...]
           [--class calibrator|target] [--arms T,T-mild,N,Z,R,O]
           [--net LABEL=WEIGHTS.npz[@TAU] ...] [--no-q3]

OUT.json `RUN/name.json` means $RUN_DIR/name.json. Arms are pooled over the
class's scans of all given observations. Network arms run the Rust kernel.
"""

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from rang import f2flag as ff
from rang import f2flag_sim as fs


def load_scan(s):
    m = s.meta
    data = np.array(s.array("data"))
    sigma = m["sigma"]
    scan = {
        "data": data,
        "model": np.array(s.array("model")),
        "weights": np.full(data.shape, 1.0 / sigma**2, np.float32),
        "antenna1": np.array(m["antenna1"], np.int32),
        "antenna2": np.array(m["antenna2"], np.int32),
        "times": np.array(m["times"]),
        "antenna_position": np.array(m["antenna_position"]),
        "chan_freq": np.array(m["chan_freq"]),
        "chan_width": np.array(m["chan_width"]),
        "corr_type": np.array(m["corr_type"], np.int32),
        "nant": m["nant"],
        "sigma": sigma,
    }
    scan["planes"] = ff.Planes(scan["antenna1"], scan["antenna2"], scan["times"])
    rfi = np.array(s.array("rfi"))
    scan["amp"] = (np.abs(rfi).max(-1) / sigma).astype(np.float32)
    scan["rfi"] = rfi
    scan["morph"] = np.array(s.array("morph"))
    return scan


def z_scores(scan, shared, block=64):
    """(row, chan, 4) input z of section 3 (0 on flagged cells)."""
    planes = scan["planes"]
    vis = planes.to_planes(scan["data"], 0)
    fl = planes.to_planes(shared, True)
    z = np.zeros(vis.shape, np.float64)
    for b in range(0, planes.nbl, block):
        z[b : b + block] = ff.features(vis[b : b + block], fl[b : b + block])[1]
    return planes.from_planes(z)


def q3_errors(scan, arm_flags, shared):
    """Per arm: sum ||dP||^2 and sum ||P0||^2 over intervals and baselines
    valid for every arm and the RFI-free reference; intervals lost."""
    clean = (scan["data"] - scan["rfi"]).astype(np.complex64)
    ref, _, _ = ff.solve(scan, shared, data=clean)
    ubl = scan["planes"].ubl
    p0, ok0 = ff.gain_products(ref.gains, ref.flags == 0, ubl[:, 0], ubl[:, 1])
    prods, oks = {}, ok0.copy()
    solver = {"reference": [ref.iterations, ref.converged_fraction]}
    for label, flags in arm_flags.items():
        sol, _, _ = ff.solve(scan, flags)
        p, ok = ff.gain_products(sol.gains, sol.flags == 0, ubl[:, 0], ubl[:, 1])
        prods[label] = p
        oks &= ok
        solver[label] = [sol.iterations, sol.converged_fraction]
    out = {}
    den = float(np.sum(np.abs(p0[oks]) ** 2))
    for label, p in prods.items():
        out[label] = {
            "num": float(np.sum(np.abs(p[oks] - p0[oks]) ** 2)),
            "den": den,
        }
    return out, {"common_valid": int(oks.sum()), "total": int(oks.size)}, solver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("obs", nargs="+", type=Path)
    parser.add_argument("--class", dest="klass", default="calibrator")
    parser.add_argument("--arms", default="T,T-mild,N,Z,R,O")
    parser.add_argument("--net", action="append", default=[])
    parser.add_argument("--no-q3", action="store_true")
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    klass = args.klass
    arms = [a for a in args.arms.split(",") if a]
    if klass == "target" and "T-mild" in arms:
        arms.remove("T-mild")
    nets = dict(item.split("=", 1) for item in args.net)
    weights = {k: ff.load_net(v) for k, v in nets.items()}
    shared_steps = ff.shared_strategy(klass)
    steps = {"T": ff.strategy(ff.STRATEGIES[klass]), "T-mild": ff.strategy(ff.MILD)}
    counts = {}
    q3 = {}
    per_scan = []
    started = time.perf_counter()
    for obs in args.obs:
        for s in fs.scans_of(obs, klass):
            t0 = time.perf_counter()
            scan = load_scan(s)
            shared, _ = ff.run_strategy(scan, shared_steps)
            flags = {}
            seconds = {}
            for arm in arms:
                t = time.perf_counter()
                if arm in ("T", "T-mild"):
                    flags[arm] = ff.run_strategy(scan, steps[arm])[0]
                elif arm == "N":
                    flags[arm] = shared.copy()
                elif arm == "Z":
                    flags[arm] = shared | ff.z_flags(z_scores(scan, shared))
                elif arm == "R":
                    flags[arm] = shared | ff.r_flags(scan, shared)
                elif arm == "O":
                    flags[arm] = shared | (scan["amp"] > 0)
                seconds[arm] = time.perf_counter() - t
            for label, w in weights.items():
                t = time.perf_counter()
                flags[label] = ff.network_flags(scan, shared, *w)[0]
                seconds[label] = time.perf_counter() - t
            record = {
                "observation": s.meta["observation"],
                "scan": s.meta["scan"],
                "field": s.meta["field_name"],
                "seconds_not_timing": seconds,
                "shared_fraction": float(shared.mean()),
                "truth_fraction": float((scan["amp"] > 0).mean()),
                "arms": {},
            }
            for label, f in flags.items():
                c = ff.truth_counts(scan, f, scan["amp"], shared, scan["morph"])
                ff.add_counts(counts.setdefault(label, {}), c)
                record["arms"][label] = {
                    "q1": ff.pooled({"q1": c["q1"]})["q1"],
                    "q2": ff.pooled({"q2": c["q2"]})["q2"],
                    "flagged": float(f.mean()),
                }
            if not args.no_q3:
                errs, support, solver = q3_errors(scan, flags, shared)
                for label, e in errs.items():
                    t = q3.setdefault(label, {"num": 0.0, "den": 0.0})
                    t["num"] += e["num"]
                    t["den"] += e["den"]
                record["q3_support"] = support
                record["solver"] = solver
                record["q3"] = {
                    k: float(np.sqrt(v["num"] / v["den"])) for k, v in errs.items()
                }
            record["wall"] = time.perf_counter() - t0
            per_scan.append(record)
            print(json.dumps(record), flush=True)
    result = {
        "class": klass,
        "observations": [str(o) for o in args.obs],
        "nets": nets,
        "pooled": {k: ff.pooled(v) for k, v in counts.items()},
        "q3": {k: float(np.sqrt(v["num"] / v["den"])) for k, v in q3.items()},
        "q3_sums": q3,
        "counts": counts,
        "per_scan": per_scan,
        "wall": time.perf_counter() - started,
    }
    result["calls"] = calls(result)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["calls"], indent=1))


def call(value, ref, beat, tol, lower_is_better):
    if value is None or ref is None:
        return "undecidable"
    d = value - ref
    if lower_is_better:
        d = -d
    if d >= beat:
        return "beats"
    if d >= -tol:
        return "matches"
    return "worse"


def calls(result):
    """Section 5's calls against T, and 'meets Q'."""
    pooled, q3 = result["pooled"], result["q3"]
    if "T" not in pooled:
        return {}
    t = pooled["T"]
    decidable = bool(q3) and "N" in q3 and q3["N"] >= 1.01 * q3["T"]
    # Amendment 2 (post hoc): Q3 has power if O <= 0.99 N.
    power = bool(q3) and "N" in q3 and "O" in q3 and q3["O"] <= 0.99 * q3["N"]
    out = {"q3_decidable": decidable, "q3_power_posthoc": power}
    for label, p in pooled.items():
        if label == "T":
            continue
        c1 = call(p["q1"], t["q1"], 0.05, 0.05, False)
        c2 = call(p["q2"], t["q2"], 0.01, 0.01, True)
        if q3 and label in q3:
            ratio = q3[label] / q3["T"]
            c3 = (
                "undecidable"
                if not decidable
                else (
                    "beats" if ratio <= 0.99 else "matches" if ratio < 1.01 else "worse"
                )
            )
            c3p = (
                "undecidable"
                if not power
                else (
                    "beats" if ratio <= 0.99 else "matches" if ratio < 1.01 else "worse"
                )
            )
        else:
            ratio, c3, c3p = None, "not run", "not run"
        out[label] = {
            "q1": [p["q1"], t["q1"], c1],
            "q2": [p["q2"], t["q2"], c2],
            "q3_ratio": [ratio, c3],
            "q3_posthoc": c3p,
            "meets_q": c1 in ("beats", "matches")
            and c2 in ("beats", "matches")
            and c3 in ("beats", "matches"),
            "meets_q_posthoc": c1 in ("beats", "matches")
            and c2 in ("beats", "matches")
            and c3p in ("beats", "matches"),
        }
    return out


if __name__ == "__main__":
    main()
