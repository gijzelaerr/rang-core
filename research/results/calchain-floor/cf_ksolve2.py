# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 10 (post hoc): as `cf_ksolve1.py`, but
every K1 interval of field 0 solved jointly on arrays (time bins: the
nearest K1 solution time), and `cal_delay.gaincal` on scan 11 alone and on
both scans; one antenna's delay in one interval against truth.

    python cf_ksolve2.py CASE ARM ANT INTERVAL
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_apply, cal_delay, core_ms


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
    sel = (np.hypot(uvw[:, 0], uvw[:, 1]) > 150) & (a1 != a2)
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
    del v
    mc, fm = cal_apply.apply(m, np.zeros(m.shape, bool), tt, b1, b2, rows.freq, [S.tab(A / "G0")],
                             direction="corrupt", nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
    del m
    w = np.where(sig > 0, 1.0 / sig.astype(float) ** 2, 0.0)
    w = np.broadcast_to(w[:, None, :], vc.shape).astype(np.float32)
    truth = S.tab(d / "truth-s0f" / "K")
    _, vt = S.kvals(truth)
    tk = vt[
        np.abs(np.unique(np.round(truth.column("TIME"), 3)) - t1[interval]).argmin()
    ]
    out = {"truth_ns": (tk[ant] - tk[rows.ref]).tolist(),
           "arm_table_ns": (S.kvals(k1)[1][interval, ant]).tolist()}  # fmt: skip
    for label, opts in (
        ("joint, 1 it", {"max_iterations": 1}),
        ("joint, 50 it", {"max_iterations": 50}),
    ):
        sol = cal_delay.solve(vc, mc, w, fc | fm, frow, b1, b2, iv[sel], nant=rows.nant,
                              chan_freq=rows.freq, refant=rows.ref, **opts)  # fmt: skip
        out[label] = {"iterations": sol.iterations, "converged_fraction": sol.converged_fraction,
                      "ant_ns": sol.delays[interval, 0, ant].tolist()}  # fmt: skip
    del vc, mc
    for label, scan in (
        ("gaincal scan 11, 50 it", [11]),
        ("gaincal scans 9, 11, 50 it", [9, 11]),
    ):
        table, sol, _ = cal_delay.gaincal(
            ms, field_id=rows.fid, solint="60s", refant=["m022", "m023", "m024"], uvrange=">150",
            gaintable=[S.tab(A / "G0"), S.tab(A / "B0")], weight_column=None, scan=scan,
            max_iterations=50,
        )  # fmt: skip
        tl, vl = S.kvals(table)
        j = int(np.abs(tl - t1[interval]).argmin())
        out[label] = {"iterations": sol.iterations, "converged_fraction": sol.converged_fraction,
                      "interval_time_offset_s": float(tl[j] - t1[interval]), "ant_ns": vl[j, ant].tolist(),
                      "intervals": len(tl)}  # fmt: skip
    S.write(S.O / f"score-ksolve2-{case}-{name}-{ant}-{interval}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
