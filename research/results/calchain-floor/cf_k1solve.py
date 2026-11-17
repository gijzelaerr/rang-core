# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 8 (post hoc): K1 of an arm re-solved
by `rang.cal_delay.gaincal` on the arm's MS (read only) with the arm's G0,
B0 pre-applied, at the chain's stop rule and strict, and from the FFT
start alone; each against the arm's own K1 table and against truth.

    python cf_k1solve.py CASE ARM
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_delay

RULES = {
    "chain (50, 1e-7, 0.99)": {
        "max_iterations": 50,
        "stop_criterion": 1e-7,
        "stop_fraction": 0.99,
    },
    "strict (1000, 1e-12, 1.0)": {
        "max_iterations": 1000,
        "stop_criterion": 1e-12,
        "stop_fraction": 1.0,
    },
    "FFT start only (0 iterations)": {
        "max_iterations": 0,
        "stop_criterion": 1e-7,
        "stop_fraction": 0.99,
    },
}


def main(case, name):
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    interp = "nearest" if name == "near" else "linear"
    truth = S.tab(d / "truth-s0f" / "K")
    arm_k1 = S.tab(A / "K1")
    _, va = S.kvals(arm_k1)
    out = {"case": case, "arm": name}
    for label, rule in RULES.items():
        try:
            table, sol, _ = cal_delay.gaincal(
                ms, field_id=rows.fid, solint="60s", refant=["m022", "m023", "m024"],
                uvrange=">150", gaintable=[S.tab(A / "G0"), S.tab(A / "B0")], interp=interp,
                weight_column=None, **rule,
            )  # fmt: skip
        except Exception as e:  # noqa: BLE001
            out[label] = {"error": repr(e)}
            continue
        _, vp = S.kvals(table)
        same = np.abs(vp - va)
        out[label] = {
            "iterations": sol.iterations,
            "converged_fraction": sol.converged_fraction,
            "vs_arm_K1_max_ns": float(np.nanmax(same))
            if np.isfinite(same).any()
            else None,
            "vs_truth": S.k_error(table, truth, rows.ref),
            "id50_interval7_ns": vp[7, S.ODD].tolist(),
        }
    out["arm K1 id50 interval 7 ns"] = va[7, S.ODD].tolist()
    S.write(S.O / f"score-k1solve-{case}-{name}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
