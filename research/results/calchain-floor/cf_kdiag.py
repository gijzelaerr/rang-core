# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 12 (post hoc): on the arrays
`cal_delay.gaincal` hands its kernel for an arm's K1 (captured), per
(interval, antenna) the unflagged cells on the baseline to the refant, all
its unflagged cells and its K1 error against truth; and one interval
re-solved from the captured arrays with other starts.

    python cf_kdiag.py CASE ARM INTERVAL ANT
"""

import json
import sys

import cf_kcapture as KC
import cf_score as S
import numpy as np
from rang import cal_delay


def main(case, name, interval, ant):
    interval, ant = int(interval), int(ant)
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    cal_delay.solve = KC.capture
    table, _, _ = cal_delay.gaincal(
        ms, field_id=rows.fid, solint="60s", refant=["m022", "m023", "m024"], uvrange=">150",
        gaintable=[S.tab(A / "G0"), S.tab(A / "B0")], weight_column=None, max_iterations=50,
    )  # fmt: skip
    cal_delay.solve = KC._solve
    (data, model, weights, flag, flag_row, a1, a2, tb), kw = KC.CAPTURED[-1]
    ok = ~(np.asarray(flag).astype(bool).any(-1) | (np.asarray(weights) == 0).any(-1))
    ok &= ~np.asarray(flag_row, bool)[:, None]
    per_row = ok.sum(1)
    truth = S.tab(d / "truth-s0f" / "K")
    _, vt = S.kvals(truth)
    tt = np.unique(np.round(truth.column("TIME"), 3))
    tk_t, va = S.kvals(table)
    ref = rows.ref
    ants = sorted(set(rows.a1) | set(rows.a2))
    out = {"rows": []}
    for i in range(int(tb.max()) + 1):
        tk = vt[np.abs(tt - tk_t[i]).argmin()]
        for a in ants:
            if a == ref:
                continue
            on = (tb == i) & ((a1 == a) | (a2 == a))
            to_ref = on & ((a1 == ref) | (a2 == ref))
            err = np.abs((va[i, a] - va[i, ref]) - (tk[a] - tk[ref]))
            out["rows"].append([i, int(a), int(per_row[to_ref].sum()), int(per_row[on].sum()),
                                float(np.nanmax(err)) if np.isfinite(err).any() else None])  # fmt: skip
    r = [x for x in out["rows"] if x[4] is not None]
    wrong = [x for x in r if x[4] > 1e-3]
    right = [x for x in r if x[4] <= 1e-3]
    out["wrong (>1e-3 ns): [interval, antenna, refant cells, cells, error ns]"] = wrong
    out["right: refant cells min, cells min"] = [
        min(x[2] for x in right),
        min(x[3] for x in right),
    ]
    out["right with refant cells < 100"] = [x for x in right if x[2] < 100]
    one = tb == interval
    args = [np.asarray(x)[one] for x in (data, model, weights, flag, flag_row, a1, a2)]
    base = {k: v for k, v in kw.items() if k not in ("trace",)}
    starts = {
        "chain": {},
        "start at 0, strict": {"initial_estimate": False, "max_iterations": 1000, "stop_criterion": 1e-12, "stop_fraction": 1.0},
        "FFT start, QuartiCal offset start, strict": {"offset_start": False, "max_iterations": 1000,
                                                     "stop_criterion": 1e-12, "stop_fraction": 1.0},
        "FFT start, strict": {"max_iterations": 1000, "stop_criterion": 1e-12, "stop_fraction": 1.0},
    }  # fmt: skip
    tk = vt[np.abs(tt - tk_t[interval]).argmin()]
    out["truth_ns"] = (tk[ant] - tk[ref]).tolist()
    for label, o in starts.items():
        sol = KC._solve(*args, np.zeros(int(one.sum()), int), **{**base, **o})
        out[f"interval {interval} ant {ant}: {label}"] = sol.delays[0, 0, ant].tolist()
    S.write(S.O / f"score-kdiag-{case}-{name}.json", out)
    print(
        json.dumps(
            {k: v for k, v in out.items() if k != "rows"}, indent=1, default=float
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
