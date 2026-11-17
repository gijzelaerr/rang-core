# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 10 (post hoc): one K1 interval of an
arm solved alone by `rang.cal_delay.solve` on arrays (the interval's
field-0 rows on baselines > 150 m, B0 correcting the data, G0 corrupting
the model, weights 1 / SIGMA^2, the arm's FLAG), with the FFT start or
from 0, QuartiCal's or rang's offset start, 1 or 50 or 1000 iterations;
one antenna's delays (referenced to m022) against truth.

    python cf_ksolve1.py CASE ARM ANT INTERVAL
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_apply, cal_delay, core_ms

ARMS = {
    "FFT start, rang offset start, 50 it": {"initial_estimate": True, "offset_start": True, "max_iterations": 50},
    "FFT start, rang offset start, 1 it": {"initial_estimate": True, "offset_start": True, "max_iterations": 1},
    "FFT start, rang offset start, 1000 it strict": {"initial_estimate": True, "offset_start": True,
                                                     "max_iterations": 1000, "stop_criterion": 1e-12,
                                                     "stop_fraction": 1.0},
    "FFT start, QuartiCal offset start (0), 50 it": {"initial_estimate": True, "offset_start": False,
                                                     "max_iterations": 50},
    "start at 0, 50 it": {"initial_estimate": False, "max_iterations": 50},
    "start at 0, 1000 it strict": {"initial_estimate": False, "max_iterations": 1000,
                                   "stop_criterion": 1e-12, "stop_fraction": 1.0},
}  # fmt: skip


def main(case, name, ant, interval):
    ant, interval = int(ant), int(interval)
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    k1 = S.tab(A / "K1")
    t1 = np.unique(np.round(k1.column("TIME"), 3))
    fr = rows.field_rows
    with core_ms.open_table(ms) as t:
        tm = np.asarray(t.getcol("TIME"))[fr]
        a1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        a2 = np.asarray(t.getcol("ANTENNA2"))[fr]
        uvw = np.asarray(t.getcol("UVW"))[fr]
    iv = np.abs(tm[:, None] - t1[None, :]).argmin(1)
    long_ = (np.hypot(uvw[:, 0], uvw[:, 1]) > 150) & (a1 != a2)
    sel = (iv == interval) & long_
    idx = fr[sel]
    with core_ms.open_table(ms) as t:
        v = np.asarray(t.getcol_rows("DATA", idx))
        m = np.asarray(t.getcol_rows("MODEL_DATA", idx))
        f = np.asarray(t.getcol_rows("FLAG", idx))
        frow = np.asarray(t.getcol_rows("FLAG_ROW", idx))
        sig = np.asarray(t.getcol_rows("SIGMA", idx))
    b1, b2, tt = a1[sel], a2[sel], tm[sel]
    vc, fc = cal_apply.apply(v, f, tt, b1, b2, rows.freq, [S.tab(A / "B0")], direction="correct",
                             nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
    mc, fm = cal_apply.apply(m, np.zeros(m.shape, bool), tt, b1, b2, rows.freq, [S.tab(A / "G0")],
                             direction="corrupt", nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
    w = np.where(sig > 0, 1.0 / sig.astype(float) ** 2, 0.0)
    w = np.broadcast_to(w[:, None, :], v.shape).astype(np.float32)
    truth = S.tab(d / "truth-s0f" / "K")
    _, vt = S.kvals(truth)
    tk = vt[
        np.abs(np.unique(np.round(truth.column("TIME"), 3)) - t1[interval]).argmin()
    ]
    out = {"case": case, "arm": name, "antenna": ant, "interval": interval, "rows": int(sel.sum()),
           "truth_ns": (tk[ant] - tk[rows.ref]).tolist(),
           "arm_table_ns": (S.kvals(k1)[1][interval, ant]).tolist()}  # fmt: skip
    for label, opts in ARMS.items():
        sol = cal_delay.solve(vc, mc, w, fc | fm, frow, b1, b2, np.zeros(len(b1), int), nant=rows.nant,
                              chan_freq=rows.freq, refant=rows.ref, **opts)  # fmt: skip
        tau = sol.delays[0, 0]
        e = np.abs(tau - (tk - tk[rows.ref]))
        e[rows.ref] = np.nan
        out[label] = {"iterations": sol.iterations, "converged_fraction": sol.converged_fraction,
                      "ant_ns": tau[ant].tolist(), "flagged": sol.flags[0, 0, ant].tolist(),
                      "max_err_other_antennas_ns": float(np.nanmax(np.delete(e, ant, 0)))}  # fmt: skip
    S.write(S.O / f"score-ksolve1-{case}-{name}-{ant}-{interval}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
