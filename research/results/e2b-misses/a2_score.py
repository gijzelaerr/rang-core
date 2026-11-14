"""Arm A2's score (research/e2b-misses.md 9.1): rang's frozen tables
(`R/rang-run/calibrate`) against one set of CASA tables, with gate 3b's
composite code (`e2_score3b.scores`, `e2avg_common`): the primary's K G B
composite (pooled, every 8th time) and the secondary's K F B (table fields
1, 2, 1), class B; per-term K, G, B, Gsec, F (and F_fs) reported.

    python a2_score.py control OUT.json            C0: R/casa/tables
    python a2_score.py case CASE_TABLES OUT.json   one case's tables

Rows and frequencies come from `R/casa/e2b.ms`, read only.
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply

R = Path(r"D:\rang\outputs\e2-20261111-20-e2b")
MS = R / "casa" / "e2b.ms"
FCAL, GCAL = "J1939-6342", "J1833-2103"


def score(cdir):
    rdir = R / "rang-run" / "calibrate"
    names = ["K", "G", "B", "Gsec", "F"]
    r = {n: C.table(rdir / n) for n in names}
    c = {n: C.table(cdir / n) for n in names}
    out = {"casa_tables": str(cdir), "rang_tables": str(rdir), "terms": {}}
    out["terms"]["K"] = C.term_diff(r["K"], c["K"], "delay")
    for n in ("G", "B", "Gsec", "F"):
        out["terms"][n] = C.term_diff(r[n], c[n], "complex")
    if (cdir / "F_fs").exists():
        out["terms"]["F_fs"] = C.term_diff(r["F"], C.table(cdir / "F_fs"), "complex")
    pooled = [cal_apply.POOLED] * 3
    fcal = C.field_id(MS, FCAL)
    t0 = time.perf_counter()
    a, fa = C.composite(MS, fcal, [r[n] for n in ("K", "G", "B")], pooled, step=8)
    b, fb = C.composite(MS, fcal, [c[n] for n in ("K", "G", "B")], pooled, step=8)
    out["composite_fcal_KGB"] = C.rel_stats(a, fa, b, fb)
    gcal = C.field_id(MS, GCAL)
    tf = [fcal, gcal, fcal]
    a, fa = C.composite(MS, gcal, [r[n] for n in ("K", "F", "B")], tf, step=1)
    b, fb = C.composite(MS, gcal, [c[n] for n in ("K", "F", "B")], tf, step=1)
    out["composite_gcal_KFB"] = C.rel_stats(a, fa, b, fb)
    if (cdir / "F_fs").exists():
        b, fb = C.composite(
            MS, gcal, [c["K"], C.table(cdir / "F_fs"), c["B"]], tf, step=1
        )
        out["composite_gcal_KFB_F_fs"] = C.rel_stats(a, fa, b, fb)
    out["composite_seconds"] = time.perf_counter() - t0
    out["class_b_both"] = bool(
        out["composite_fcal_KGB"]["class_b"] and out["composite_gcal_KFB"]["class_b"]
    )
    return out


def main(argv):
    if argv[0] == "control":
        out = score(R / "casa" / "tables")
        ref = json.loads((R / "g3b.json").read_text())
        checks = {}
        for k in ("composite_fcal_KGB", "composite_gcal_KFB"):
            a, b = out[k], ref[k]
            checks[k] = {
                "cells_equal": a["cells"] == b["cells"],
                "median_rel": abs(a["median"] - b["median"]) / b["median"],
                "p95_rel": abs(a["p95"] - b["p95"]) / b["p95"],
                "archived": {
                    x: b[x] for x in ("cells", "median", "p95", "flags_differ")
                },
            }
            checks[k]["met"] = bool(
                checks[k]["cells_equal"]
                and checks[k]["median_rel"] <= 1e-3
                and checks[k]["p95_rel"] <= 1e-3
            )
        out["c0"] = {"checks": checks, "met": all(v["met"] for v in checks.values())}
        dest = Path(argv[1])
    else:
        out = score(Path(argv[1]))
        dest = Path(argv[2])
    C.write(dest, out)
    print(json.dumps({k: v for k, v in out.items() if k != "terms"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
