"""Arm A5's M0 (research/e2b-misses.md 9.18): GeMClean's auto-mask noise per
major iteration and finishing iteration against WSClean 3.7's on G9's P1.

    a5_m0.py OUT_JSON
"""

import json
import sys
from pathlib import Path

from a5_score import sigmas_rang, sigmas_wsclean

P = Path("D:/rang/outputs/gemclean-iquv-mask-20261115/m0")
g = sigmas_rang(P / "rang.out")
w = sigmas_wsclean(P / "wsclean.out")
t = (P / "rang.out").read_text(encoding="utf-8", errors="replace")
g["majors"] = len(g["sigma"])
upto = min(
    len(g["sigma"]), len(w["sigma"]), max(g["finishing"] or 0, w["finishing"] or 0)
)
rel = [abs(a / b - 1) for a, b in zip(g["sigma"][:upto], w["sigma"][:upto])]
rec = {
    "gemclean": g,
    "wsclean": w,
    "sigma_rel_diff": rel,
    "sigma_met": bool(rel) and max(rel) <= 0.01,
    "finishing_met": g["finishing"] is not None and g["finishing"] == w["finishing"],
    "majors_met": abs(g["majors"] - w["majors"]) <= 1,
}
rec["met"] = rec["sigma_met"] and rec["finishing_met"] and rec["majors_met"]
Path(sys.argv[1]).write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
print(json.dumps(rec, indent=1))
