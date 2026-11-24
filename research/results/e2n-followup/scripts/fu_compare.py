"""E2-N's K-downstream rows beside the follow-up's (seen, post hoc; no frozen row rescored).

python fu_compare.py E2N_DIR FU_DIR OUT.json
E2N_DIR holds E2-N's g3b.json, rows.json, row-target.json, leakage-casa.json
(research/results/e2n/score/); FU_DIR the follow-up's (files missing there are "not run").
"""

import json
import sys
from pathlib import Path


def load(d, name):
    p = Path(d) / name
    return json.loads(p.read_text()) if p.is_file() else None


def g3b(g):
    if g is None:
        return None
    t = g["terms"]
    return {
        "K median, p95 ns (n)": [t["K"]["abs_ns"]["median"], t["K"]["abs_ns"]["p95"], t["K"]["abs_ns"]["n"]],
        "K flags differ": t["K"].get("flags_differ"),
        "KCROSS ns": t["Kcross"]["abs_ns"]["median"],
        "Xf median, p95 deg (n)": [t["Xf"]["abs_deg"]["median"], t["Xf"]["abs_deg"]["p95"], t["Xf"]["abs_deg"]["n"]],
        "Df median, p95": [t["Df"]["abs"]["median"], t["Df"]["abs"]["p95"]],
        "Gpol median deg": t["Gpol"]["abs_deg"]["median"],
        "G rel median, p95 (n)": [t["G"]["rel"]["median"], t["G"]["rel"]["p95"], t["G"]["rel"]["n"]],
        "B rel median, p95 (n)": [t["B"]["rel"]["median"], t["B"]["rel"]["p95"], t["B"]["rel"]["n"]],
        "fcal KGB median, p95 (cells, flags differ)": [
            g["composite_fcal_KGB"]["median"], g["composite_fcal_KGB"]["p95"],
            g["composite_fcal_KGB"]["cells"], g["composite_fcal_KGB"]["flags_differ"]],
        "gcal KFB median, p95 (cells, flags differ)": [
            g["composite_gcal_KFB"]["median"], g["composite_gcal_KFB"]["p95"],
            g["composite_gcal_KFB"]["cells"], g["composite_gcal_KFB"]["flags_differ"]],
        "class B per term": {k: v.get("class_b") for k, v in t.items() if "class_b" in v},
    }  # fmt: skip


def rows(r):
    if r is None:
        return None
    out = {}
    for key, v in r.items():
        if not isinstance(v, dict) or "bins" not in v:
            continue
        b = [x for x in v["bins"] if x.get("scored")]
        out[key] = {
            "bins scored": len(b),
            "max |dI| rel": max(
                (abs(x["dI_rel"]) for x in b if x.get("dI_rel") is not None),
                default=None,
            ),
            "max |dp| point": max((abs(x["dp"]) * 100 for x in b), default=None),
            "max |dchi| deg": max((abs(x["dchi_deg"]) for x in b), default=None),
            "frac unflagged rang, casa": [x["frac_unflagged"] for x in v["bins"]],
            "met": all(x.get("met") for x in b) if b else None,
        }
    return out


def target(t):
    if t is None:
        return None
    c = t["compact"]["gated_within_0p7deg"]
    nd = t["noise_dynamic_range"]
    return {"compact n, median, robust scatter": [c["n"], c["median"], c["robust_scatter"]],
            "compact met": c["met"], "rms ratio": nd["rms_ratio"],
            "dynamic range ratio": nd["dynamic_range_ratio"], "noise met": nd["met"]}  # fmt: skip


def leak(x):
    if x is None:
        return None
    return {k: x[k] for k in ("Q_over_I", "U_over_I", "V_over_I", "met")}


e2n, fu, out = sys.argv[1:4]
res = {}
for label, d, tgt in (
    ("e2n", e2n, "row-target.json"),
    ("followup", fu, "row-target.json"),
):
    lk = load(d, "leakage-casa.json") or load(Path(d) / "leakage", "casa.json")
    res[label] = {"3b": g3b(load(d, "g3b.json")), "rows": rows(load(d, "rows.json")),
                  "target": target(load(d, tgt)), "leakage_casa": leak(lk)}  # fmt: skip
Path(out).write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
