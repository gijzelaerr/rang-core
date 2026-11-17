# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 14 (post hoc): K1 of e2a-3b-k's real
subset (`rang-u.ms`, read only) re-solved by `cal_delay.gaincal` with that
run's G0 and B0 pre-applied, `zero_start` off and on.

    python cf_kreal.py
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_delay


def main():
    ms = S.K / "rang-u.ms"
    A = S.K / "rang-u.ms.rang-run" / "calibrate"
    rows = S.Rows(ms)
    out = {}
    vals = {}
    for zs in (False, True):
        table, sol, _ = cal_delay.gaincal(
            ms, field_id=rows.fid, solint="60s", refant=["m022", "m023", "m024"], uvrange=">150",
            gaintable=[S.tab(A / "G0"), S.tab(A / "B0")], weight_column=None, max_iterations=50,
            zero_start=zs,
        )  # fmt: skip
        _, v = S.kvals(table)
        vals[zs] = v
        out[f"zero_start={zs}"] = {
            "id50_ns": np.round(v[:, S.ODD], 4).tolist(),
            "zero_start_intervals": sol.settings.get("zero_start_intervals"),
            "iterations": sol.iterations,
            "converged_fraction": sol.converged_fraction,
        }
    _, arch = S.kvals(S.tab(A / "K1"))
    out["key off vs the run's own K1, max ns"] = float(
        np.nanmax(np.abs(vals[False] - arch))
    )
    d = np.abs(vals[True] - vals[False])
    moved = np.argwhere(d > 1e-3)
    out["solutions moved > 1e-3 ns by the key: [interval, antenna, hand, off, on]"] = [
        [
            int(i),
            int(a),
            int(h),
            float(vals[False][i, a, h]),
            float(vals[True][i, a, h]),
        ]
        for i, a, h in moved
    ]
    S.write(S.O / "score-kreal.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
