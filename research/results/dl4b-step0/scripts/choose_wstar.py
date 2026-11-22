"""W* from the validation split only (note section 4, amendment 4's two-sided
recovery), plus the cross-host check of glacier's ladder against nash's.
Usage: choose_wstar.py LADDER_DIR NASH_LADDER_DIR OUT_JSON"""

import json
import statistics as st
import sys
from pathlib import Path

ARMS = ["WA", "W1", "W2", "W3", "W4", "W5", "W6"]


def load(d):
    recs = []
    for f in sorted(Path(d).glob("L*.json")):
        recs += json.loads(f.read_text())
    return {(r["seed"], r["flux"]): r for r in recs}


g, n = load(sys.argv[1]), load(sys.argv[2])
val = [
    k
    for k, r in g.items()
    if r["split"] == "validation" and r["W1"]["recovery"] is not None
]
out = {"n_val_fields": len(val), "arms": {}}
for a in ARMS:
    drec = [abs(g[k][a]["recovery"] - 1) - abs(g[k]["W1"]["recovery"] - 1) for k in val]
    dfal = [g[k][a]["false"] - g[k]["W1"]["false"] for k in val]
    out["arms"][a] = {
        "median_d_absrec": st.median(drec),
        "median_d_false": st.median(dfal),
        "inside_tolerance": st.median(drec) <= 0.02 and st.median(dfal) <= 0.01,
        "median_inversions": st.median(g[k][a]["major"] for k in val),
        "median_deconvolution_s": st.median(
            g[k][a].get("deconvolution_s", float("nan")) for k in val
        ),
        "median_wall_s": st.median(g[k][a]["wall_s"] for k in val),
        "median_recovery": st.median(g[k][a]["recovery"] for k in val),
        "median_false": st.median(g[k][a]["false"] for k in val),
        "median_e1": st.median(g[k][a]["e1"] for k in val),
    }
cands = [a for a in ARMS[1:] if out["arms"][a]["inside_tolerance"]]
wstar = min(
    cands,
    key=lambda a: (
        out["arms"][a]["median_inversions"],
        out["arms"][a]["median_deconvolution_s"],
    ),
)
out["W*"] = wstar
out["candidates"] = cands
# cross-host: same fields, same arms, quality and cycle counts
diffs = {"recovery": 0.0, "false": 0.0, "e1": 0.0}
major_eq = iters_eq = tot = 0
for k in g:
    if k not in n:
        continue
    for a in ARMS:
        for m in list(diffs):
            x, y = g[k][a][m], n[k][a][m]
            if x is not None and y is not None:
                diffs[m] = max(diffs[m], abs(x - y))
        major_eq += g[k][a]["major"] == n[k][a]["major"]
        iters_eq += g[k][a]["iterations"] == n[k][a]["iterations"]
        tot += 1
out["cross_host"] = {
    "fields": sum(k in n for k in g),
    "arm_runs": tot,
    "major_equal": major_eq,
    "iterations_equal": iters_eq,
    "max_abs_diff": diffs,
}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "arms"}, indent=1))
for a in ARMS:
    x = out["arms"][a]
    print(a, {k: round(v, 4) if isinstance(v, float) else v for k, v in x.items()})
