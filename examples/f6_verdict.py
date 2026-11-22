"""F6: the decision rule (research/f6-flagger.md 2d, Amendment 2d-1) from the shards of
examples/f6_heldout.py, F5's gates otherwise (examples/f5_verdict.py).

Usage: python examples/f6_verdict.py OUT.json --class calibrator --run RUN
       --sets luno:MAIN_0,sarao:1678312253:0,... [--cost4 C4.json --cost1 C1.json]
       [--c2 RATIO] [--p-holds]

A "set" for the per-set gates (R3, R5) is an F4/F5 set or one SARAO block (its scored
scans of the class pooled: added cells and strong-consensus hits summed). R4, G-perm
and G-drop are per scan. R1, R1m, R2, G-chan and synthetic G-sub pool over all sets.
Real G-sub: blocks 1678312253 and 1674958551; G-obs: 1579022459 (required for shipping).
"""

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f5_verdict", HERE / "f5_verdict.py")
fv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fv)

REAL_GSUB = {"1678312253": "real29", "1674958551": "real32outer"}
GOBS = "1579022459"


def group(s):
    return f"sarao:{s.split(':')[1]}" if s.startswith("sarao:") else s


def pooled_un(uns):
    """R3 and R5 on summed counts over a block's scans."""
    added = {}
    for u in uns:
        for k, v in u["added"].items():
            added[k] = added.get(k, 0) + v
    strong = sum(u.get("strong_cells", 0) for u in uns)
    hits = {}
    for u in uns:
        for k, v in (u.get("R5") or {}).items():
            if v is not None:
                hits[k] = hits.get(k, 0.0) + v * u["strong_cells"]
    r5 = {k: h / strong for k, h in hits.items()} if strong else {}
    return {"added": added, "strong_cells": strong, "R5": r5}


def bars(cases, un):
    m, t = fv.pool(cases, "method"), fv.pool(cases, "T")
    r = fv.r3(un)
    return {"R1_method": m, "R1_T": t, "R3": r, "pass": m >= t - 0.05 and r["pass"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--class", dest="klass", required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--sets", required=True)
    p.add_argument("--cost4", type=Path)
    p.add_argument("--cost1", type=Path)
    p.add_argument("--c2", type=float)
    p.add_argument("--p-holds", action="store_true")
    a = p.parse_args()
    sets = a.sets.split(",")
    res = {"class": a.klass, "sets": sets, "gates": {}, "reported": {}}
    g = res["gates"]
    r1c, r2c, sub, per_scan, groups = [], [], {}, {}, {}
    for s in sets:
        d = a.run / s.replace(":", "-")
        un = json.loads((d / "uninjected.json").read_text())
        cases = [c for x in fv.load(d, "r1-") for c in x["cases"]]
        r2 = [c for x in fv.load(d, "r2-") for c in x["cases"]]
        r1c += cases
        r2c += r2
        groups.setdefault(group(s), {"un": [], "r1": [], "r2": []})
        groups[group(s)]["un"].append(un)
        groups[group(s)]["r1"] += cases
        groups[group(s)]["r2"] += r2
        ja, jm = un["J_T"].get("A"), un["J_T"]["method"]
        ps = {
            "R4": {
                "J": jm,
                "bar": (ja - 0.05) if ja is not None else None,
                "pass": ja is None or (jm is not None and jm >= ja - 0.05),
            },
            "w3_not_in_T": un["w3_not_in_T"],
        }
        gp = fv.load(d, "gperm-")
        ps["G-perm"] = {
            "logit_max_abs": max(x["logit_max_abs"] for x in gp),
            "flag_diff_frac": max(x["flag_diff"] / x["eligible"] for x in gp),
        }
        ps["G-perm"]["pass"] = (
            ps["G-perm"]["logit_max_abs"] <= 1e-4
            and ps["G-perm"]["flag_diff_frac"] <= 1e-6
        )
        gd = fv.load(d, "gdrop-")
        ps["G-drop"] = {
            "fractions": {f"{x['k']}-{x['seed']}": x["change_frac"] for x in gd},
            "pass": all(x["change_frac"] <= fv.GDROP_BAR[x["k"]] for x in gd),
        }
        for nm in ("core16", "outer32"):
            q = d / f"gsub-{nm}.json"
            if q.exists():
                sub.setdefault(nm, []).append(
                    {"un": json.loads(q.read_text()), "full_cases": cases}
                )
        gc = d / "gchan.json"
        if gc.exists():
            x = json.loads(gc.read_text())
            res["reported"].setdefault("G-chan", {})[s] = {
                "R1_method": fv.pool(x["cases"], "method"),
                "R1_T": fv.pool(x["cases"], "T"),
                "R3": fv.r3(x),
            }
        per_scan[s] = ps
    res["per_scan"] = per_scan
    rt, rm = fv.pool(r1c, "T"), fv.pool(r1c, "method")
    g["R1"] = {"method": rm, "T": rt, "pass": rm >= rt - 0.05}
    g["R1m"] = {
        m: {"method": fv.pool(r1c, "method", m), "T": fv.pool(r1c, "T", m)}
        for m in sorted({c["morphology"] for c in r1c})
    }
    for v in g["R1m"].values():
        v["pass"] = v["method"] >= v["T"] - 0.10
    g["R2"] = {
        m: {"method": fv.pool(r2c, "method", m), "T": fv.pool(r2c, "T", m)}
        for m in sorted({c["morphology"] for c in r2c})
    }
    for v in g["R2"].values():
        v["pass"] = v["method"] >= v["T"] - 0.05
    pooled = {k: pooled_un(v["un"]) for k, v in groups.items()}
    g["R3"] = {k: fv.r3(u) for k, u in pooled.items()}
    if a.klass == "calibrator":
        g["R4"] = {s: per_scan[s]["R4"] for s in sets}
    g["R5"] = {
        k: {
            "recall": u["R5"].get("method"),
            "strong_cells": u["strong_cells"],
            "pass": (u["R5"].get("method") or 0) >= 0.80,
        }
        for k, u in pooled.items()
    }
    g["G-perm"] = {s: per_scan[s]["G-perm"] for s in sets}
    g["G-drop"] = {s: per_scan[s]["G-drop"] for s in sets}
    gs = {}
    for name, items in sub.items():
        cs = [c for it in items for c in it["un"]["cases"]]
        full = [c for it in items for c in it["full_cases"]]
        recs = [fv.r3(it["un"]) for it in items]
        ms, ts, mf = fv.pool(cs, "method"), fv.pool(cs, "T"), fv.pool(full, "method")
        gs[name] = {
            "R1_method": ms,
            "R1_T": ts,
            "R1_method_full": mf,
            "R3": recs,
            "pass": ms >= ts - 0.05
            and ms >= mf - 0.05
            and all(r["pass"] for r in recs),
        }
    for cb, name in REAL_GSUB.items():
        k = f"sarao:{cb}"
        if k in groups:
            gs[name] = bars(groups[k]["r1"], pooled[k])
    g["G-sub"] = gs
    gobs = None
    if f"sarao:{GOBS}" in groups:
        k = f"sarao:{GOBS}"
        gobs = bars(groups[k]["r1"], pooled[k])
    res["G-obs"] = gobs
    sim_dir = a.run / f"sim-{a.klass}"
    if sim_dir.exists():
        tot = {}
        for x in fv.load(sim_dir, "scan-"):
            for arm, c in x["counts"].items():
                fv.ff.add_counts(tot.setdefault(arm, {}), c)
        pm = {arm: fv.ff.pooled(v) for arm, v in tot.items()}
        g["S1"] = {"method": pm["method"]["q1"], "T": pm["T"]["q1"]}
        g["S1"]["pass"] = g["S1"]["method"] >= g["S1"]["T"] - 0.05
        g["S2"] = {"method": pm["method"]["q2"], "T": pm["T"]["q2"]}
        g["S2"]["pass"] = g["S2"]["method"] <= g["S2"]["T"] + 0.01
        s3 = fv.load(sim_dir, "s3-")
        if s3:
            cs = [c for x in s3 for c in x["cases"]]
            h = {
                arm: sum(c[arm] for c in cs) / max(sum(c["cells"] for c in cs), 1)
                for arm in ("method", "T")
            }
            g["S3"] = {"source": "H1 fallback", **h}
        else:
            bm = {
                arm: pm[arm]["by_morphology"].get("drifting") for arm in ("method", "T")
            }
            g["S3"] = {"source": "drifting", **bm}
        g["S3"]["pass"] = g["S3"]["method"] >= g["S3"]["T"] - 0.05
    cost = {}
    for k, path in (("4", a.cost4), ("1", a.cost1)):
        if path:
            c = json.loads(path.read_text())
            cost[k] = {x: c.get(x) for x in ("c1", "q25", "q75", "reading")}
    res["cost"] = cost

    def failed(node, path=""):
        out = []
        if isinstance(node, dict):
            if node.get("pass") is False or node.get("pass") is np.False_:
                out.append(path)
            for k, v in node.items():
                if isinstance(v, dict):
                    out += failed(v, f"{path}/{k}" if path else k)
        return out

    res["failed"] = failed(g)
    worse = any(v["reading"] == "worse" for v in cost.values())
    beats = len(cost) == 2 and all(v["reading"] == "beats" for v in cost.values())
    c2_ok = a.c2 is None or a.c2 <= 1.2
    quality_failed = [f for f in res["failed"] if not f.startswith("S2")]  # S2: S-
    if quality_failed or worse:
        out = "F"
    elif not beats:
        out = "H"
    elif g.get("S2", {}).get("pass", True) and a.p_holds and c2_ok:
        out = "S"
    elif c2_ok:
        out = "S-"
    else:
        out = "H"
    res["outcome"] = out if len(cost) == 2 else f"{out} (cost not yet measured)"
    res["ships"] = out in ("S", "S-") and bool(gobs and gobs["pass"])
    a.out.write_text(
        json.dumps(
            res,
            indent=1,
            default=lambda o: float(o) if isinstance(o, np.floating) else str(o),
        )
    )
    print(json.dumps({"outcome": res["outcome"], "failed": res["failed"]}))


if __name__ == "__main__":
    main()
