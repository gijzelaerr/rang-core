"""E2-A gate 3b's score (research/e2-acceptance.md 6.5; appendix A, E2-A
"Solutions": class B on composite products, K by its limit): rang's tables
(R/rang-run/calibrate) against CASA's (R/casa/tables, e2_casa3b_a.py), with
E2-B's measures (e2_score3b.py, e2avg_common).

Gated: K1 by its limit (|delay difference| median <= 0.01 ns, p95 <= 0.03 ns)
and the fcal composite of the applied tables K1, G1, B1 (relative median
<= 7e-4, p95 <= 3e-3). Reported: G1 and B1 alone, K0, G0, B0 (rang solved
them before the A step) and their composite.

    python e2_score3b_a.py R MS     -> R/g3b-a.json
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply

FCAL = "J1939-6342"
K_LIMIT = {"median": 0.01, "p95": 0.03}


def k_class(d):
    s = d["abs_ns"]
    return bool(s.get("median") is not None and s["median"] <= K_LIMIT["median"]
                and s["p95"] <= K_LIMIT["p95"])  # fmt: skip


def scores(rdir, cdir, ms, step=8):
    names = ("K0", "G0", "B0", "K1", "G1", "B1")
    r = {n: C.table(rdir / n) for n in names}
    c = {n: C.table(cdir / n) for n in names}
    out = {"terms": {}}
    for n in names:
        out["terms"][n] = d = C.term_diff(r[n], c[n], "delay" if n[0] == "K" else "complex")
        if n[0] == "K":
            d["class_b"] = k_class(d)
    fcal = C.field_id(ms, FCAL)
    pooled = [cal_apply.POOLED] * 3
    for tag, ts in (("1", ("K1", "G1", "B1")), ("0", ("K0", "G0", "B0"))):
        a, fa = C.composite(ms, fcal, [r[n] for n in ts], pooled, step=step)
        b, fb = C.composite(ms, fcal, [c[n] for n in ts], pooled, step=step)
        out[f"composite_fcal_KGB{tag}"] = C.rel_stats(a, fa, b, fb)
    gated = {"K1": out["terms"]["K1"]["class_b"],
             "composite_fcal_KGB1": out["composite_fcal_KGB1"]["class_b"]}  # fmt: skip
    out["gated"] = gated
    out["met"] = all(gated.values())
    out["reported_not_gated"] = ["G1", "B1", "K0", "G0", "B0", "composite_fcal_KGB0"]
    return out


def main(argv):
    r, ms = Path(argv[0]), Path(argv[1])
    out = scores(r / "rang-run" / "calibrate", r / "casa" / "tables", ms)
    C.write(r / "g3b-a.json", out)
    print(json.dumps({k: out[k] for k in ("gated", "met")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
