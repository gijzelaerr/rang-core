"""F2 Amendment 3: validation Q1 and Q2 of trained arms against the logit
threshold, and the threshold picked by the amendment's rule
(research/f2-flagger.md).

Usage: python examples/f2_threshold.py OUT.json VAL_OBS VAL_MEASURE.json --class K
           --net LABEL=W.npz ...

VAL_MEASURE.json is `f2_measure.py`'s validation result for the class (T's Q1
and Q2 are read from it). Amendment 3's rule: the largest threshold on the grid
(0 to -6) with Q1 at least T's and Q2 at most T's + 0.01; if none, the one with
the largest Q1 among those with Q2 at most T's + 0.01. Whether the rule applies
at all (the arm fails Q at 0) is read from VAL_MEASURE.json by the caller.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from rang import f2flag as ff
from rang import f2flag_sim as fs

sys.path.insert(0, str(Path(__file__).parent))
from f2_measure import load_scan

GRID = [-0.5 * k for k in range(13)]  # 0 to -6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("obs", type=Path)
    parser.add_argument("measure", type=Path)
    parser.add_argument("--class", dest="klass", required=True)
    parser.add_argument("--net", action="append", default=[])
    args = parser.parse_args()
    out = args.out
    if out.startswith("RUN/"):
        out = Path(os.environ["RUN_DIR"]) / out[4:]
    t = json.loads(args.measure.read_text())["pooled"]["T"]
    nets = dict(item.split("=", 1) for item in args.net)
    weights = {k: ff.flat_weights(ff.load_params(v)) for k, v in nets.items()}
    counts = {k: {tau: {} for tau in GRID} for k in nets}
    for s in fs.scans_of(args.obs, args.klass):
        scan = load_scan(s)
        shared, _ = ff.run_strategy(scan, ff.shared_strategy(args.klass))
        for k, w in weights.items():
            _, logit = ff.network_flags(scan, shared, w)
            for tau in GRID:
                f = shared | (logit > tau)
                c = ff.truth_counts(scan, f, scan["amp"], shared)
                ff.add_counts(counts[k][tau], {"q1": c["q1"], "q2": c["q2"]})
    result = {"class": args.klass, "T": {"q1": t["q1"], "q2": t["q2"]}, "nets": nets}
    for k in nets:
        curve = [
            {"tau": tau, **{m: v for m, v in ff.pooled(counts[k][tau]).items()}}
            for tau in GRID
        ]
        ok = [c for c in curve if c["q1"] >= t["q1"] and c["q2"] <= t["q2"] + 0.01]
        if ok:
            pick = max(ok, key=lambda c: c["tau"])
        else:
            cands = [c for c in curve if c["q2"] <= t["q2"] + 0.01]
            pick = max(cands, key=lambda c: c["q1"])
        result[k] = {"curve": curve, "pick": pick["tau"]}
        print(k, json.dumps(result[k]), flush=True)
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
