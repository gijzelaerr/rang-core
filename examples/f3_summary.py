"""F3: the frozen gates from f3_eval.py outputs (research/f3-flagger.md, sections 6-7).

Usage: python examples/f3_summary.py OUT.json --real A.json [B.json ...] --sim S.json [--arm N3]
"""

import argparse
import json
from pathlib import Path


def pool(results, kind, arms):
    out = {}
    for r in results:
        for c in r["cases"]:
            if c["kind"] != kind:
                continue
            for a in arms:
                if a not in c:
                    continue
                key = (a, c["morphology"])
                h, n = out.get(key, (0, 0))
                out[key] = (h + c[a], n + c["cells"])
    return out


def frac(h, n):
    return h / n if n else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--real", nargs="*", default=[])
    parser.add_argument("--sim", nargs="*", default=[])
    parser.add_argument("--arm", default="N3")
    args = parser.parse_args()
    real = [json.loads(Path(p).read_text()) for p in args.real]
    arms = sorted({a for r in real for a in r["uninjected"]})
    res = {"arm": args.arm, "arms": arms, "real_sets": [r["set"] for r in real]}
    r1 = pool(real, "r1", arms)
    res["R1"] = {}
    res["R1m"] = {}
    for a in arms:
        h = sum(v[0] for (aa, _), v in r1.items() if aa == a)
        n = sum(v[1] for (aa, _), v in r1.items() if aa == a)
        res["R1"][a] = frac(h, n)
        res["R1m"][a] = {m: frac(*v) for (aa, m), v in r1.items() if aa == a}
    r2 = pool(real, "r2", arms)
    res["R2"] = {a: {m: frac(*v) for (aa, m), v in r2.items() if aa == a} for a in arms}
    res["R3"] = {
        r["set"]: {a: v.get("ratio_T") for a, v in r["uninjected"].items()}
        for r in real
    }
    res["R4"] = {
        r["set"]: {a: v.get("J_T") for a, v in r["uninjected"].items()} for r in real
    }
    res["added"] = {
        r["set"]: {a: v["added"] for a, v in r["uninjected"].items()} for r in real
    }
    sims = [json.loads(Path(p).read_text()) for p in args.sim]
    res["S"] = {}
    for s in sims:
        for a, v in s["arms"].items():
            res["S"][a] = {
                "Q1": v["q1"],
                "Q2": v["q2"],
                "Q1_ge3": v["q1_ge3"],
                "by_morphology": {
                    k: v_
                    for k, v_ in v["by_morphology"].items()
                    if not k.endswith("_n")
                },
            }
    x = args.arm
    gates = {}
    if real and "T" in arms and x in arms:
        gates["R1"] = res["R1"][x] >= res["R1"]["T"] - 0.05
        gates["R1m"] = all(
            (res["R1m"][x].get(m) or 0) >= (res["R1m"]["T"].get(m) or 0) - 0.10
            for m in res["R1m"]["T"]
        )
        if res["R2"].get("T"):
            gates["R2"] = all(
                (res["R2"][x].get(m) or 0) >= (res["R2"]["T"].get(m) or 0) - 0.05
                for m in res["R2"]["T"]
            )
        gates["R3"] = all((res["R3"][s].get(x) or 0) <= 1.5 for s in res["R3"])
        if "A" in arms:
            gates["R4"] = all(
                (res["R4"][s].get(x) or 0) >= (res["R4"][s].get("A") or 0) - 0.05
                for s in res["R4"]
            )
    if sims and x in res["S"] and "T" in res["S"]:
        sx, st = res["S"][x], res["S"]["T"]
        gates["S1"] = sx["Q1"] >= st["Q1"] - 0.05
        gates["S2"] = sx["Q2"] <= st["Q2"] + 0.01
        gates["S3"] = (sx["by_morphology"].get("drifting") or 0) >= (
            st["by_morphology"].get("drifting") or 0
        ) - 0.05
    res["gates"] = gates
    Path(args.out).write_text(json.dumps(res, indent=1))
    print(
        json.dumps(
            {
                "R1": res["R1"],
                "R1m": res["R1m"],
                "R2": res["R2"],
                "R3": res["R3"],
                "R4": res["R4"],
                "S": {
                    a: (v["Q1"], v["Q2"], v["by_morphology"].get("drifting"))
                    for a, v in res["S"].items()
                },
                "gates": gates,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
