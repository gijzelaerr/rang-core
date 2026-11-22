"""Section 5 summary for one split: WSClean ladder arms and network arms on the
same fields, paired against W1 (two-sided recovery, amendment 4) and, for the
anchor, E1 against WA. Usage: summarise.py SPLIT LADDER_DIR OUT_JSON NETSCORE_DIR..."""

import json
import statistics as st
import sys
from pathlib import Path

split, ladder, out_json, nets = (
    sys.argv[1],
    Path(sys.argv[2]),
    Path(sys.argv[3]),
    sys.argv[4:],
)


def load(d, pat):
    recs = []
    for f in sorted(Path(d).glob(pat)):
        recs += json.loads(f.read_text())
    return {(r["seed"], r["flux"]): r for r in recs}


lad = load(ladder, "L*.json")
net = {}
for d in nets:
    for k, r in load(d, "N*.json").items():
        net.setdefault(k, {}).update(
            {a: v for a, v in r.items() if isinstance(v, dict)}
        )
keys = [
    k
    for k, r in lad.items()
    if r["split"] == split and r["W1"]["recovery"] is not None and k in net
]
arms_w = ["Z", "WA", "W1", "W2", "W3", "W4", "W5", "W6", "T"]
arms_n = sorted({a for k in keys for a in net[k]})


def rec(k, a):
    return lad[k][a] if a in lad[k] else net[k][a]


res = {"split": split, "fields": len(keys), "arms": {}}
for a in arms_w + arms_n:
    rows = [rec(k, a) for k in keys]
    inv = [r.get("inversions", r.get("major")) for r in rows]
    x = {
        "median_recovery": st.median(r["recovery"] for r in rows),
        "median_false": st.median(r["false"] for r in rows),
        "mean_false": st.mean(r["false"] for r in rows),
        "median_e1": st.median(r["e1"] for r in rows),
        "median_e2": st.median(r["e2"] for r in rows),
        "median_d_absrec_vs_W1": st.median(
            abs(rec(k, a)["recovery"] - 1) - abs(lad[k]["W1"]["recovery"] - 1)
            for k in keys
        ),
        "median_d_false_vs_W1": st.median(
            rec(k, a)["false"] - lad[k]["W1"]["false"] for k in keys
        ),
        "median_d_e1_vs_WA": st.median(
            rec(k, a)["e1"] - lad[k]["WA"]["e1"] for k in keys
        ),
    }
    x["inside_tolerance"] = (
        x["median_d_absrec_vs_W1"] <= 0.02 and x["median_d_false_vs_W1"] <= 0.01
    )
    if None not in inv:
        x["median_inversions"] = st.median(inv)
    if a in arms_n:
        x["median_passes"] = st.median(r["passes"] for r in rows)
        x["median_infer_s_total"] = st.median(r["infer_s_total"] for r in rows)
        x["per_flux"] = {
            f: {
                "median_recovery": st.median(
                    rec(k, a)["recovery"] for k in keys if k[1] == f
                ),
                "median_false": st.median(
                    rec(k, a)["false"] for k in keys if k[1] == f
                ),
            }
            for f in (10, 100, 1000)
        }
    elif "deconvolution_s" in rows[0]:
        x["median_deconvolution_s"] = st.median(r["deconvolution_s"] for r in rows)
    res["arms"][a] = x
out_json.write_text(json.dumps(res, indent=1))
print("fields", len(keys))
for a, x in res["arms"].items():
    print(
        a.ljust(5),
        " ".join(
            f"{k.replace('median_', '')}={v:.4g}"
            for k, v in x.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ),
        "IN" if x["inside_tolerance"] else "out",
    )
