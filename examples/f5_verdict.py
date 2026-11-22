"""F5: the frozen decision rule (research/f5-flagger.md, sections 8, 10, 11)
from Stage 5's shards, Stage 2's checks and Stage 6's cost.

Usage: python examples/f5_verdict.py OUT.json --class calibrator --run RUN
       --sets luno:MAIN_0,luno:MAIN_12,luno:MAIN_14 [--stage2 S2.json]
       [--cost4 C4.json --cost1 C1.json] [--c2 RATIO] [--p-holds]

Reads RUN/<set>/*.json (f5_heldout.py real) and RUN/sim-<class>/ (sim).
Gates use "method" against T; the other arms are reported.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from rang import f2flag as ff

GDROP_BAR = {1: 0.05, 4: 0.20, 8: 0.25}


def load(d, prefix):
    return [json.loads(p.read_text()) for p in sorted(Path(d).glob(f"{prefix}*.json"))]


def pool(cases, arm, morph=None):
    h = n = 0
    for c in cases:
        if morph is None or c["morphology"] == morph:
            h += c.get(arm, 0)
            n += c["cells"]
    return h / n if n else None


def r3(rec, arm="method"):
    ad = rec["added"]
    t = max(ad["T"], 1)
    lower = 0.5 * min(ad["T"], ad.get("A", ad["T"])) / t
    ratio = ad[arm] / t
    return {"ratio": ratio, "lower": lower, "pass": lower <= ratio <= 1.5}


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
    r1c, r2c, sub = [], [], {}
    per_set = {}
    for s in sets:
        d = a.run / s.replace(":", "-")
        un = json.loads((d / "uninjected.json").read_text())
        cases = [c for x in load(d, "r1-") for c in x["cases"]]
        r1c += cases
        r2c += [c for x in load(d, "r2-") for c in x["cases"]]
        ps = {
            "R3": r3(un),
            "J_T": un["J_T"],
            "R5": un.get("R5", {}),
            "w3_not_in_T": un["w3_not_in_T"],
        }
        ja = un["J_T"].get("A")
        ps["R4"] = {
            "J": un["J_T"]["method"],
            "bar": (ja - 0.05) if ja is not None else None,
            "pass": (ja is None)
            or un["J_T"]["method"] is not None
            and un["J_T"]["method"] >= ja - 0.05,
        }
        gp = load(d, "gperm-")
        ps["G-perm"] = {
            "logit_max_abs": max(x["logit_max_abs"] for x in gp),
            "flag_diff_frac": max(x["flag_diff"] / x["eligible"] for x in gp),
        }
        ps["G-perm"]["pass"] = (
            ps["G-perm"]["logit_max_abs"] <= 1e-4
            and ps["G-perm"]["flag_diff_frac"] <= 1e-6
        )
        gd = load(d, "gdrop-")
        ps["G-drop"] = {f"{x['k']}-{x['seed']}": x["change_frac"] for x in gd}
        ps["G-drop_pass"] = all(x["change_frac"] <= GDROP_BAR[x["k"]] for x in gd)
        for x in load(d, "gsub-"):
            name = None
            for nm in ("core16", "outer32"):
                if (d / f"gsub-{nm}.json").exists() and json.loads(
                    (d / f"gsub-{nm}.json").read_text()
                ) == x:
                    name = nm
            sub.setdefault(name, []).append({"un": x, "full_cases": cases})
        gc = d / "gchan.json"
        if gc.exists():
            x = json.loads(gc.read_text())
            res["reported"].setdefault("G-chan", {})[s] = {
                "R1_method": pool(x["cases"], "method"),
                "R1_T": pool(x["cases"], "T"),
                "R3": r3(x),
            }
        per_set[s] = ps
    res["per_set"] = per_set
    rt, rm = pool(r1c, "T"), pool(r1c, "method")
    g["R1"] = {"method": rm, "T": rt, "pass": rm >= rt - 0.05}
    morphs = sorted({c["morphology"] for c in r1c})
    g["R1m"] = {
        m: {"method": pool(r1c, "method", m), "T": pool(r1c, "T", m)} for m in morphs
    }
    for v in g["R1m"].values():
        v["pass"] = v["method"] >= v["T"] - 0.10
    hm = sorted({c["morphology"] for c in r2c})
    g["R2"] = {
        m: {"method": pool(r2c, "method", m), "T": pool(r2c, "T", m)} for m in hm
    }
    for v in g["R2"].values():
        v["pass"] = v["method"] >= v["T"] - 0.05
    g["R3"] = {s: per_set[s]["R3"] for s in sets}
    if a.klass == "calibrator":
        g["R4"] = {s: per_set[s]["R4"] for s in sets}
    g["R5"] = {
        s: {
            "recall": per_set[s]["R5"].get("method"),
            "pass": (per_set[s]["R5"].get("method") or 0) >= 0.80,
        }
        for s in sets
    }
    g["G-perm"] = {s: per_set[s]["G-perm"] for s in sets}
    g["G-drop"] = {
        s: {"fractions": per_set[s]["G-drop"], "pass": per_set[s]["G-drop_pass"]}
        for s in sets
    }
    gs = {}
    for name, items in sub.items():
        cs = [c for it in items for c in it["un"]["cases"]]
        full = [c for it in items for c in it["full_cases"]]
        recs = [r3(it["un"]) for it in items]
        ms, ts, mf = pool(cs, "method"), pool(cs, "T"), pool(full, "method")
        gs[name] = {
            "R1_method": ms,
            "R1_T": ts,
            "R1_method_full": mf,
            "R3": recs,
            "pass": ms >= ts - 0.05
            and ms >= mf - 0.05
            and all(r["pass"] for r in recs),
        }
    g["G-sub"] = gs
    sim_dir = a.run / f"sim-{a.klass}"
    if sim_dir.exists():
        tot = {}
        for x in load(sim_dir, "scan-"):
            for arm, c in x["counts"].items():
                ff.add_counts(tot.setdefault(arm, {}), c)
        pm = {arm: ff.pooled(v) for arm, v in tot.items()}
        g["S1"] = {"method": pm["method"]["q1"], "T": pm["T"]["q1"]}
        g["S1"]["pass"] = g["S1"]["method"] >= g["S1"]["T"] - 0.05
        g["S2"] = {"method": pm["method"]["q2"], "T": pm["T"]["q2"]}
        g["S2"]["pass"] = g["S2"]["method"] <= g["S2"]["T"] + 0.01
        s3 = load(sim_dir, "s3-")
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
        res["reported"]["sim_arms"] = {
            arm: {"q1": v["q1"], "q2": v["q2"]} for arm, v in pm.items()
        }
    cost = {}
    for k, path in (("4", a.cost4), ("1", a.cost1)):
        if path:
            c = json.loads(path.read_text())
            cost[k] = {
                x: c[x]
                for x in ("c1", "q25", "q75", "clean_pairs", "provisional", "reading")
            }
    res["cost"] = cost
    quality = [
        g["R1"]["pass"],
        *(v["pass"] for v in g["R1m"].values()),
        *(v["pass"] for v in g["R2"].values()),
        *(v["pass"] for v in g["R3"].values()),
        *((v["pass"] for v in g["R4"].values()) if "R4" in g else ()),
        *(v["pass"] for v in g["R5"].values()),
        *(v["pass"] for v in g["G-perm"].values()),
        *(v["pass"] for v in g["G-drop"].values()),
        *(v["pass"] for v in g["G-sub"].values()),
    ]
    if "S1" in g:
        quality += [g["S1"]["pass"], g["S3"]["pass"]]
    worse = any(v["reading"] == "worse" for v in cost.values())
    beats = len(cost) == 2 and all(v["reading"] == "beats" for v in cost.values())
    c2_ok = a.c2 is None or a.c2 <= 1.2
    if not all(quality) or worse:
        out = "F"
    elif not beats:
        out = "H"
    elif g.get("S2", {}).get("pass", True) and a.p_holds and c2_ok:
        out = "S"
    elif c2_ok:
        out = "S-"
    else:
        out = "H"
    res["outcome"] = (
        out if len(cost) == 2 else f"{out} (cost not yet measured: provisional)"
    )

    def failed(name, v):
        if isinstance(v, dict):
            if "pass" in v and not bool(v["pass"]):
                return [name]
            return [f for k, x in v.items() for f in failed(f"{name}/{k}", x)]
        return []

    res["failed"] = [f for k, v in g.items() for f in failed(k, v)]
    a.out.write_text(
        json.dumps(
            res,
            indent=1,
            default=lambda o: float(o) if isinstance(o, np.floating) else str(o),
        )
    )
    print(json.dumps({"outcome": res["outcome"], "R1": g["R1"]}))


if __name__ == "__main__":
    main()
