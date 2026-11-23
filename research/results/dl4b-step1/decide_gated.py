"""Section 5's decision on the gated skies G1-G4: per sky and seed, the tolerance against W1
and the cost clauses against W* = W5 (mean of the two exclusive timings each).
Usage: decide_gated.py SCORE_JSON ARMS_ROOT OUT_JSON  (ARMS_ROOT holds <sky>/arms/*.json)"""

import json
import statistics as st
import sys
from pathlib import Path

score = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
out = {"skies": {}, "seeds": {}}


def wtime(sky, arm):
    t = []
    for tag in ("", "-r2"):
        j = json.loads((root / sky / "arms" / f"{arm}{tag}.json").read_text())
        t.append((j["deconvolution_s"], j["wall_s"]))
    return st.mean(x[0] for x in t), st.mean(x[1] for x in t), t


def ptime(sky, k):
    m, w = [], []
    for r in ("", "r2"):
        steps = json.loads((root / sky / "arms" / f"P-s{k}{r}-t5-K1.json").read_text())[
            "steps"
        ]
        s = steps[-1]
        m.append(s["continue_deconvolution_s"] + s["infer_s"])
        w.append(s["infer_s"] + s["predict_s"] + s["continue_wall_s"])
    return st.mean(m), st.mean(w), list(zip(m, w))


for k in (1, 2, 3):
    rows = []
    for g in ("G1", "G2", "G3", "G4"):
        a = score[g]["arms"]
        w1, p = a["W1"], a[f"P-s{k}-t5-K1"]
        ratio = p["relative_l2"] / w1["relative_l2"]
        inside = ratio <= 1.10 and p["false_flux"] <= w1["false_flux"] + 0.01 and p["extended_failing"] <= w1["extended_failing"]  # fmt: skip
        ws_m, ws_w, ws_t = wtime(g, "W5")
        w1_m, w1_w, _ = wtime(g, "W1")
        pm, pw, pt = ptime(g, k)
        c = pm / ws_m
        cost_ok = c <= 0.5 and not (0.45 <= c <= 0.55) and pw <= ws_w
        rows.append({"sky": g, "rel_l2_over_W1": ratio, "false_minus_W1": p["false_flux"] - w1["false_flux"], "inside": inside, "P_minor_s": pm, "P_total_s": pw, "Wstar_minor_s": ws_m, "Wstar_total_s": ws_w, "W1_minor_s": w1_m, "minor_ratio": c, "cost_ok": cost_ok, "G_clause": inside and cost_ok})  # fmt: skip
    out["seeds"][k] = {"rows": rows, "inside_count": sum(r["inside"] for r in rows), "G_count": sum(r["G_clause"] for r in rows), "cost_fail_count": sum(not r["cost_ok"] for r in rows)}  # fmt: skip
S = out["seeds"]
if all(S[k]["G_count"] >= 3 for k in S):
    o = "G"
elif all(S[k]["inside_count"] >= 3 for k in S):
    o = "N"
elif sum(S[k]["inside_count"] <= 2 for k in S) >= 2:
    o = "F"
else:
    o = "mixed"
out["outcome"] = o
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
for k in S:
    print("seed", k, "inside", S[k]["inside_count"], "of 4; G-clause", S[k]["G_count"])
    for r in S[k]["rows"]:
        print("  ", r["sky"], f"relL2/W1 {r['rel_l2_over_W1']:.2f} dfalse {r['false_minus_W1']:+.4f} inside {r['inside']} | P minor {r['P_minor_s']:.0f} s vs W* {r['Wstar_minor_s']:.0f} s (ratio {r['minor_ratio']:.2f}), P total {r['P_total_s']:.0f} vs W* {r['Wstar_total_s']:.0f}")  # fmt: skip
print("OUTCOME", o)
