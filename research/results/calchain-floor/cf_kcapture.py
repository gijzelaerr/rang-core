# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 10 (post hoc): the arrays
`cal_delay.gaincal` hands its kernel for an arm's K1 (captured by wrapping
`cal_delay.solve`), checked cell by cell against truth for one antenna in
one interval: |data - model K_T| / |model| on the antenna's baselines, and
the interval re-solved alone from the captured arrays.

    python cf_kcapture.py CASE ARM ANT INTERVAL
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import cal_delay

CAPTURED = []
_solve = cal_delay.solve


def capture(*args, **kwargs):
    if not kwargs.get("trace"):
        CAPTURED.append((args, kwargs))
    return _solve(*args, **kwargs)


def main(case, name, ant, interval):
    ant, interval = int(ant), int(interval)
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    cal_delay.solve = capture
    cal_delay.gaincal(
        ms, field_id=rows.fid, solint="60s", refant=["m022", "m023", "m024"], uvrange=">150",
        gaintable=[S.tab(A / "G0"), S.tab(A / "B0")], weight_column=None, max_iterations=50,
    )  # fmt: skip
    cal_delay.solve = _solve
    (data, model, weights, flag, flag_row, a1, a2, tb), kw = CAPTURED[-1]
    out = {"calls": len(CAPTURED), "rows": len(tb), "bins": int(np.max(tb)) + 1}
    truth = S.tab(d / "truth-s0f" / "K")
    _, vt = S.kvals(truth)
    tk = np.nan_to_num(vt[0])
    freq = np.asarray(kw["chan_freq"], float)
    ph = 2 * np.pi * (freq - truth.k_reference_frequency(0)) * 1e-9
    sel = (tb == interval) & ((a1 == ant) | (a2 == ant)) & ~np.asarray(flag_row, bool)
    out["rows_ant_interval"] = int(sel.sum())
    dd = np.asarray(data)[sel]
    mm = np.asarray(model)[sel]
    ff = np.asarray(flag)[sel].astype(bool) | (np.asarray(weights)[sel] == 0)
    per = []
    for h, c in ((0, 0), (1, 3)):
        k = np.exp(1j * ph[None, :] * (tk[a1[sel], h] - tk[a2[sel], h])[:, None])
        pred = mm[..., c] * k
        ok = ~ff.any(-1) & (np.abs(mm[..., c]) > 0)
        r = np.abs(dd[..., c] - pred) / np.where(
            np.abs(mm[..., c]) > 0, np.abs(mm[..., c]), 1
        )
        per.append({"cells": int(ok.sum()), "median": float(np.median(r[ok])) if ok.any() else None,
                    "max": float(r[ok].max()) if ok.any() else None,
                    "cells_above_1e-3": int((r[ok] > 1e-3).sum())})  # fmt: skip
        if ok.any() and (r[ok] > 1e-3).any():
            bad = np.argwhere(ok & (r > 1e-3))
            out[f"bad_cells_hand{h}_by_baseline"] = {
                f"{int(a1[sel][i])}-{int(a2[sel][i])}": int((bad[:, 0] == i).sum())
                for i in np.unique(bad[:, 0])
            }
            out[f"bad_channels_hand{h}"] = [
                int(np.min(bad[:, 1])),
                int(np.max(bad[:, 1])),
            ]
            out[f"bad_example_hand{h}"] = {
                "data": [float(abs(dd[bad[0][0], bad[0][1], c])), float(np.angle(dd[bad[0][0], bad[0][1], c]))],
                "model_kt": [float(abs(pred[bad[0][0], bad[0][1]])), float(np.angle(pred[bad[0][0], bad[0][1]]))],
            }  # fmt: skip
    out["consistency_with_truth"] = per
    fl = np.asarray(flag)[sel].astype(bool)
    w0 = np.asarray(weights)[sel] == 0
    out["cells_flag_any_corr"] = int(fl.any(-1).sum())
    out["cells_weight0_any_corr_not_flagged"] = int((w0.any(-1) & ~fl.any(-1)).sum())
    ok = ~ff.any(-1)
    ch = np.flatnonzero(ok.any(0))
    out["unflagged_channels"] = (
        [int(ch.min()), int(ch.max()), int(ch.size)] if ch.size else []
    )
    out["unflagged_cells_per_baseline"] = {
        f"{int(x)}-{int(y)}": int(ok[i].sum())
        for i, (x, y) in enumerate(zip(a1[sel], a2[sel]))
        if ok[i].any()
    }
    # the same rows read from the MS: FLAG, then B0 (correct) and G0 (corrupt) flags
    from rang import cal_apply, core_ms

    with core_ms.open_table(ms) as t:
        fr = np.flatnonzero(np.asarray(t.getcol("FIELD_ID")) == rows.fid)  # autocorrelations included
        ma1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        ma2 = np.asarray(t.getcol("ANTENNA2"))[fr]
        tm = np.asarray(t.getcol("TIME"))[fr]
    out["captured_rows_are_field_rows_in_order"] = bool(
        len(ma1) == len(a1) and np.array_equal(ma1, a1) and np.array_equal(ma2, a2)
    )
    if out["captured_rows_are_field_rows_in_order"]:
        idx = fr[sel]
        with core_ms.open_table(ms) as t:
            mf = np.asarray(t.getcol_rows("FLAG", idx))
            mfr = np.asarray(t.getcol_rows("FLAG_ROW", idx))
        ones = np.ones(mf.shape, np.complex64)
        _, fb = cal_apply.apply(ones, mf, tm[sel], a1[sel], a2[sel], freq, [S.tab(A / "B0")],
                                nant=rows.nant, table_fields=[cal_apply.POOLED])  # fmt: skip
        _, fg = cal_apply.apply(ones, mf, tm[sel], a1[sel], a2[sel], freq, [S.tab(A / "G0")],
                                nant=rows.nant, table_fields=[cal_apply.POOLED], direction="corrupt")  # fmt: skip
        cap = np.asarray(flag)[sel].astype(bool)
        out["flagged cells per correlation: captured / MS FLAG / +B0 / +G0"] = [
            cap.sum((0, 1)).tolist(),
            mf.sum((0, 1)).tolist(),
            fb.sum((0, 1)).tolist(),
            fg.sum((0, 1)).tolist(),
        ]
        out["MS FLAG_ROW rows"] = int(mfr.sum())
        extra = cap & ~(fb | fg | mfr[:, None, None])
        out["captured-only flagged cells per correlation"] = extra.sum((0, 1)).tolist()
        out["captured-only flagged rows (any cell)"] = int(extra.any((1, 2)).sum())
        if extra.any():
            ch = np.flatnonzero(extra.any((0, 2)))
            out["captured-only channels"] = [int(ch.min()), int(ch.max()), int(ch.size)]
            out["captured-only by baseline"] = {
                f"{int(x)}-{int(y)}": int(extra[i].sum())
                for i, (x, y) in enumerate(zip(a1[sel], a2[sel]))
                if extra[i].any()
            }
    one = tb == interval
    sol = _solve(np.asarray(data)[one], np.asarray(model)[one], np.asarray(weights)[one],
                 np.asarray(flag)[one], np.asarray(flag_row)[one], a1[one], a2[one],
                 np.zeros(int(one.sum()), int), **{k: v for k, v in kw.items() if k != "trace"})  # fmt: skip
    out["interval alone from captured arrays, ant ns"] = sol.delays[0, 0, ant].tolist()
    S.write(S.O / f"score-kcapture-{case}-{name}-{ant}-{interval}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
