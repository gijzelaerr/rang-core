"""K and tau from validation (section 3): the pair inside the tolerance on every validation
sky for every seed, lowest median cost; if none, the pair of lowest median relative L2 over
W1's (median over 3 seeds x 4 skies). Usage: choose_ktau.py SCORE_DIR OUT_JSON"""

import json
import statistics as st
import sys
from pathlib import Path

d = Path(sys.argv[1])
sc = {k: json.loads((d / f"score-val-P-s{k}.json").read_text()) for k in (1, 2, 3)}
lad = json.loads((d / "score-val-ladder.json").read_text())
out = {"pairs": {}}
for tau in (3, 5):
    for K in (1, 2, 3):
        ratios, inside, cost, wall = [], [], [], []
        for k in (1, 2, 3):
            for v in ("V1", "V2", "V3", "V4"):
                p = sc[k][v]["arms"][f"P-s{k}-t{tau}-K{K}"]
                w1 = sc[k][v]["arms"]["W1"]
                r = p["relative_l2"] / w1["relative_l2"]
                ratios.append(r)
                inside.append(r <= 1.10 and p["false_flux"] <= w1["false_flux"] + 0.01 and p["extended_failing"] <= w1["extended_failing"])  # fmt: skip
                steps = p["steps"]
                cost.append(steps[-1]["continue_deconvolution_s"] + sum(s["infer_s"] for s in steps))  # fmt: skip
                wall.append(sum(s["infer_s"] + s["predict_s"] + s.get("residual_s", 0) for s in steps[:-1]) + steps[-1]["infer_s"] + steps[-1]["predict_s"] + steps[-1]["continue_wall_s"])  # fmt: skip
        out["pairs"][f"K{K}-t{tau}"] = {
            "median_rel_l2_over_W1": st.median(ratios),
            "inside_count": sum(inside),
            "inside_all": all(inside),
            "median_minor_cycle_s": st.median(cost),
            "median_total_wall_s": st.median(wall),
        }
ok = [p for p, x in out["pairs"].items() if x["inside_all"]]
if ok:
    out["choice"] = min(ok, key=lambda p: out["pairs"][p]["median_minor_cycle_s"])
    out["rule"] = "inside for every seed on every validation sky; lowest median cost"
else:
    out["choice"] = min(out["pairs"], key=lambda p: out["pairs"][p]["median_rel_l2_over_W1"])
    out["rule"] = "no pair inside for every seed: lowest median relative L2 over W1's; outcome F expected"
out["W1_median_deconvolution_s"] = st.median(lad[v]["arms"]["W1"]["deconvolution_s"] for v in ("V1", "V2", "V3", "V4"))  # fmt: skip
out["W5_median_deconvolution_s"] = st.median(lad[v]["arms"]["W5"]["deconvolution_s"] for v in ("V1", "V2", "V3", "V4"))  # fmt: skip
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
for p, x in out["pairs"].items():
    print(p, {k: round(v, 3) if isinstance(v, float) else v for k, v in x.items()})
print("choice", out["choice"], "|", out["rule"], "| W1/W5 median deconvolution", out["W1_median_deconvolution_s"], out["W5_median_deconvolution_s"])  # fmt: skip
