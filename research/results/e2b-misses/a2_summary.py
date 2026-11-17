"""Arm A2's controls and rule (research/e2b-misses.md 9.1) from the scores
`a2_score.py` wrote: C1 on (after, spec), then the frozen rule on
(match, ones), the other cases as attribution.

    python a2_summary.py OUT_DIR     reads OUT_DIR/c0.json, <case>/score.json -> OUT_DIR/a2.json
"""

import json
import sys
from pathlib import Path

R = Path(r"D:\rang\outputs\e2-20261111-20-e2b")
COMPOSITES = ("composite_fcal_KGB", "composite_gcal_KFB")


def rel(a, b):
    return abs(a - b) / abs(b)


def main(out):
    out = Path(out)
    ref = json.loads((R / "g3b.json").read_text())
    c0 = json.loads((out / "c0.json").read_text())["c0"]
    cases = {}
    for n in json.loads((out / "cases.json").read_text()):
        p = out / n / "score.json"
        if p.exists():
            cases[n] = json.loads(p.read_text())
    res = {"c0": c0, "cases": {}}
    for n, s in cases.items():
        res["cases"][n] = {k: {x: s[k][x] for x in ("cells", "median", "p95", "class_b")}
                           for k in COMPOSITES + ("composite_gcal_KFB_F_fs",) if k in s}  # fmt: skip
        res["cases"][n]["B_flags_differ"] = s["terms"]["B"]["flags_differ"]
        res["cases"][n]["K_abs_ns"] = s["terms"]["K"]["abs_ns"]
        res["cases"][n]["B_rel"] = s["terms"]["B"]["rel"]
    a = cases.get("after-spec")
    c1 = {"present": a is not None}
    if a:
        for k in COMPOSITES:
            c1[k] = {"median_rel": rel(a[k]["median"], ref[k]["median"]),
                     "p95_rel": rel(a[k]["p95"], ref[k]["p95"])}  # fmt: skip
        c1["B_flags_differ"] = [
            a["terms"]["B"]["flags_differ"],
            ref["terms"]["B"]["flags_differ"],
        ]
        c1["met"] = bool(
            all(
                c1[k]["median_rel"] <= 0.01 and c1[k]["p95_rel"] <= 0.01
                for k in COMPOSITES
            )
            and rel(c1["B_flags_differ"][0], c1["B_flags_differ"][1]) <= 0.01
        )
    res["c1"] = c1
    m = cases.get("match-ones")
    if not (c0["met"] and c1.get("met")):
        outcome = "void: control C0 or C1 not met"
    elif m is None:
        outcome = "incomplete: matched case missing"
    else:
        p, s = m[COMPOSITES[0]]["class_b"], m[COMPOSITES[1]]["class_b"]
        outcome = {
            (True, True): "both met: oracle input error, 3b composites closed as such",
            (
                False,
                False,
            ): "both missed: estimator difference in B (K not excluded); B task under C2c",
            (True, False): "primary met, secondary missed: difference in F; F task",
            (
                False,
                True,
            ): "primary missed, secondary met: difference in the primary's G; G task under C2c",
        }[(p, s)]
    res["outcome"] = outcome
    (out / "a2.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("c1", "outcome")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
