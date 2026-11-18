# SPDX-License-Identifier: MIT
"""Read research/calwt-terms.md section 8's rule (with amendment 10) from
the score files of `calwt_terms.py`, and write the compact receipt.

    python summarise.py OUT.json        (score-*.json from CALWT_OUT)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

O = Path(os.environ.get("CALWT_OUT", r"D:\rang\outputs\calwt-terms-20261118"))
HELD = ("H1", "H2", "H3", "H4")
DEV = ("D1", "dev")
NOISELESS = ("dev", "held", "held4")
SOLVES = {"k": ("K2", "Kg"), "g": ("G2", "Gg"), "gpol": ("Gpol",),
          "kcross": ("Kcross",), "df": ("Df",)}  # fmt: skip
GATING = {"k": ("C_F", "C_G"), "g": ("C_F", "C_G"), "gpol": ("C_X",),
          "kcross": ("C_XH",), "df": ("C_D",)}  # fmt: skip


def load(s):
    p = O / f"score-{s}.json"
    return json.loads(p.read_text()) if p.exists() else None


def oracle(scores, solve):
    off = np.array([sc["S"][solve]["off"]["median"] for sc in scores])
    on = np.array([sc["S"][solve]["on"]["median"] for sc in scores])
    mo, mn = float(np.median(off)), float(np.median(on))
    need = len(scores) - 1
    if mn <= 0.8 * mo and int((on < off).sum()) >= need:
        verdict = "O+"
    elif mo <= 0.8 * mn and int((off < on).sum()) >= need:
        verdict = "O-"
    else:
        verdict = "O0"
    return {"off": off.tolist(), "on": on.tolist(), "median_off": mo, "median_on": mn,
            "ratio_on_off": mn / mo if mo else None, "verdict": verdict}  # fmt: skip


def truth(scores, arm, comp):
    off = np.array([sc["T"]["off"][comp]["median"] for sc in scores])
    on = np.array([sc["T"][arm][comp]["median"] for sc in scores])
    return {"off": off.tolist(), "on": on.tolist(), "mean_off": float(off.mean()),
            "mean_on": float(on.mean()), "ratio_on_off": float(on.mean() / off.mean()),
            "on_below_off": int((on < off).sum()),
            "off_below_on": int((off < on).sum())}  # fmt: skip


def truth_verdict(reads):
    plus = any(r["mean_on"] <= 0.8 * r["mean_off"] and r["on_below_off"] >= 3
               for r in reads.values())  # fmt: skip
    minus = any(r["mean_off"] <= 0.8 * r["mean_on"] and r["off_below_on"] >= 3
                for r in reads.values())  # fmt: skip
    worse_any = any(r["mean_off"] <= 0.8 * r["mean_on"] for r in reads.values())
    if minus:
        return "T-"
    if plus and not worse_any:
        return "T+"
    return "T0"


def outcome(t, os_):
    if t == "T+":
        return "5" if "O-" in os_ else "1"
    if t == "T-":
        return "4"
    if "O+" in os_ and "O-" not in os_:
        return "2"
    return "3"


def controls(scores_all):
    out = {}
    for s, sc in scores_all.items():
        c1_chain = {
            a: {n: v[n] for n in ("G", "B")} for a, v in sc.get("C1", {}).items()
        }
        c1_harness = (
            {n: sc["S"][n]["on_equals_off"] for n in ("G", "B", "B2")}
            if "S" in sc
            else {}
        )
        out[s] = {
            "C1_chain_G_B": all(all(v.values()) for v in c1_chain.values()),
            "C1_harness_G_B_B2": all(c1_harness.values()) if c1_harness else None,
            "C2": sc.get("C2_bit_equal"),
            "C3_gpol_rows": sc.get("C3_gpol_rows"),
        }  # fmt: skip
    return out


def main(argv):
    scores_all = {s: load(s) for s in HELD + DEV + ("held", "held4")}
    scores_all = {s: v for s, v in scores_all.items() if v is not None}
    held = [scores_all[s] for s in HELD]
    res = {"controls": controls(scores_all), "keys": {}}
    for key, solves in SOLVES.items():
        o = {n: oracle(held, n) for n in solves}
        t = {c: truth(held, key, c) for c in GATING[key]}
        tv = truth_verdict(t)
        res["keys"][key] = {"oracle": o, "truth": t, "truth_verdict": tv,
                            "outcome": outcome(tv, [v["verdict"] for v in o.values()])}  # fmt: skip
    # Reported: every composite of every arm (and CASA), mean over H1-H4.
    comps = ("C_F", "C_G", "C_X", "C_XH", "C_XH_fit", "C_D")
    arms = ("off", "k", "g", "gpol", "kcross", "df", "all", "casa")
    res["truth_all"] = {
        a: {c: float(np.mean([sc["T"][a][c]["median"] for sc in held])) for c in comps}
        for a in arms
    }
    res["slope_ns"] = {
        a: [sc["T"][a]["C_XH_fit"]["slope_ns"] for sc in held] for a in arms
    }
    res["S_noiseless"] = {
        s: {n: {k: scores_all[s]["S"][n][k]["median"] for k in ("off", "on")}
            for n in scores_all[s]["S"]}
        for s in NOISELESS if s in scores_all
    }  # fmt: skip
    res["S_dev_D1"] = {n: {k: scores_all["D1"]["S"][n][k]["median"] for k in ("off", "on")}
                       for n in scores_all["D1"]["S"]}  # fmt: skip
    res["chain_vs_casa_mean"] = {
        a: {n: float(np.mean([sc["chain_vs_casa"][a][n]["median"] for sc in held]))
            for n in held[0]["chain_vs_casa"][a]}
        for a in ("off", "all")
    }  # fmt: skip
    Path(argv[0]).write_text(json.dumps(res, indent=1) + "\n")
    for key, v in res["keys"].items():
        os_ = {
            n: (round(x["ratio_on_off"], 3), x["verdict"])
            for n, x in v["oracle"].items()
        }
        ts = {c: round(x["ratio_on_off"], 4) for c, x in v["truth"].items()}
        print(key, os_, ts, v["truth_verdict"], "outcome", v["outcome"])
    print(json.dumps(res["controls"], indent=None))


if __name__ == "__main__":
    main(sys.argv[1:])
