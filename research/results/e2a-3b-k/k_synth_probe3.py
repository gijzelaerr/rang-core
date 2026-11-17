"""Step 5, third part (post hoc, after k_synth_probe2.py): where the unaveraged
kernel's B differs from the least-squares minimum on the synthetic, and
whether the kernel run on the per-baseline weighted means of the same prepared
rows (the exact normal-equation equivalent for a unit model) gives the minimum.

    pytest -q -s -p no:cacheprovider research/results/e2a-3b-k/k_synth_probe3.py   (K_OUT=OUT.json)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))

from k_synth_probe import chi2
from rang import cal_bandpass, cal_gain, core_ms
from test_e2_average_time import cal_ms, prepared, unit  # noqa: F401
from test_e2a_bandpass_model_divided import exact  # noqa: F401

STRICT = {"max_iterations": 1000, "stop_criterion": 1e-12, "stop_fraction": 1.0}


def collapse(arr, a1, a2, skip):
    """Per baseline, weighted means of data and model over the unskipped,
    unflagged rows (one row per baseline)."""
    keys = sorted(
        {(int(p), int(q)) for p, q, s in zip(a1, a2, skip) if p != q and not s}
    )
    shape = arr["data"].shape
    w_all = np.broadcast_to(arr["weights"], shape).astype(float)
    m_all = np.broadcast_to(arr["model"], shape)
    f_all = np.broadcast_to(arr["flag"], shape)
    out = {k: np.zeros((len(keys), *shape[1:]), t) for k, t in
           (("data", np.complex64), ("model", np.complex64), ("weights", np.float32))}  # fmt: skip
    out["flag"] = np.ones((len(keys), *shape[1:]), bool)
    for i, (p, q) in enumerate(keys):
        rows = np.flatnonzero((a1 == p) & (a2 == q) & ~skip)
        w = np.where(f_all[rows], 0, w_all[rows])
        sw = w.sum(0)
        ok = sw > 0
        out["data"][i] = np.where(
            ok, (w * arr["data"][rows]).sum(0) / np.where(ok, sw, 1), 0
        )
        out["model"][i] = np.where(
            ok, (w * m_all[rows]).sum(0) / np.where(ok, sw, 1), 0
        )
        out["weights"][i] = sw
        out["flag"][i] = ~ok
    return out, np.array([k[0] for k in keys]), np.array([k[1] for k in keys])


def test_probe3(exact):  # noqa: F811
    ms, model, _, _ = exact
    with core_ms.open_table(ms / "ANTENNA") as t:
        positions = t.getcol("POSITION")
    fld, arr, _ = prepared(
        ms, 0, "B", model=model, weight_column="WEIGHT", gaintable=[]
    )
    a1, a2 = np.asarray(fld.meta["ANTENNA1"]), np.asarray(fld.meta["ANTENNA2"])
    skip = np.asarray(fld.flag_row | fld.auto, bool)
    nchan = arr["data"].shape[1]
    kw = {"nant": 4, "freq_bin": np.arange(nchan), "refant": 0, "minblperant": 2,
          "positions": positions, **STRICT}  # fmt: skip
    full = cal_gain.solve(arr["data"], arr["model"], arr["weights"], arr["flag"], skip, a1, a2,
                          np.zeros(len(a1), np.int64), **kw)  # fmt: skip
    col, c1, c2 = collapse(arr, a1, a2, skip)
    one = cal_gain.solve(col["data"], col["model"], col["weights"], col["flag"],
                         np.zeros(len(c1), bool), c1, c2, np.zeros(len(c1), np.int64), **kw)  # fmt: skip
    # the same unaveraged rows, every row's weight doubled (the minimum cannot move)
    dbl = cal_gain.solve(arr["data"], arr["model"], 2 * np.asarray(arr["weights"]), arr["flag"],
                         skip, a1, a2, np.zeros(len(a1), np.int64), **kw)  # fmt: skip
    # the rows in reversed order
    rev = np.arange(len(a1))[::-1]
    rv = cal_gain.solve(arr["data"][rev], np.broadcast_to(arr["model"], arr["data"].shape)[rev],
                        np.broadcast_to(arr["weights"], arr["data"].shape)[rev],
                        np.broadcast_to(arr["flag"], arr["data"].shape)[rev], skip[rev],
                        a1[rev], a2[rev], np.zeros(len(a1), np.int64), **kw)  # fmt: skip
    # QuartiCal's cell rule (core/src/solve.rs data_flags): a cell with any
    # correlation flagged is dropped; collapse after OR-ing the flags over the
    # four correlations
    f = np.broadcast_to(arr["flag"], arr["data"].shape)
    anyf = np.broadcast_to(f.any(-1, keepdims=True), f.shape)
    col_any, d1, d2 = collapse(dict(arr, flag=anyf), a1, a2, skip)
    one_any = cal_gain.solve(col_any["data"], col_any["model"], col_any["weights"],
                             np.broadcast_to(col_any["flag"].any(-1, keepdims=True),
                                             col_any["flag"].shape),
                             np.zeros(len(d1), bool), d1, d2, np.zeros(len(d1), np.int64), **kw)  # fmt: skip
    cross = (a1 != a2) & ~skip
    pf = f[cross]
    res_flags = {
        "cells": int(pf[..., 0].size),
        "any_flagged": int(pf.any(-1).sum()),
        "all_flagged": int(pf.all(-1).sum()),
        "parallel_differ": int((pf[..., 0] != pf[..., 3]).sum()),
        "cross_only": int((pf[..., 1] | pf[..., 2])[~pf[..., 0] & ~pf[..., 3]].sum()),
    }
    _, div, _ = cal_bandpass.bandpass(ms, field_id=0, refant=0, combine="scan", minblperant=2,
                                      model=model, weight_column="WEIGHT", average_time=True,
                                      model_divided=True, **STRICT)  # fmt: skip
    g = {n: np.asarray(s.gains)[0] for n, s in
         (("full", full), ("collapsed", one), ("doubled", dbl), ("reversed", rv), ("div", div),
          ("collapsed_any_flag", one_any))}  # fmt: skip
    res = {}
    for n, x in g.items():
        res[n] = {"chi2": chi2(arr, a1, a2, x, skip),
                  "median_abs_vs_div": float(np.median(np.abs(x - g["div"]))),
                  "iterations": int(np.max(np.asarray(
                      {"full": full, "collapsed": one, "doubled": dbl, "reversed": rv,
                       "div": div, "collapsed_any_flag": one_any}[n].iterations)))}  # fmt: skip
    d = np.abs(g["full"] - g["div"])  # (chan, ant, hand)
    res["full_vs_div_per_channel_max"] = d.max(axis=(1, 2)).tolist()
    res["full_vs_div_per_antenna_max"] = d.max(axis=(0, 2)).tolist()
    res["full_vs_collapsed_any_flag_max"] = float(
        np.max(np.abs(g["full"] - g["collapsed_any_flag"]))
    )
    res["flags"] = res_flags
    res["rows"] = len(a1)
    res["rows_per_baseline"] = sorted({int(((a1 == p) & (a2 == q) & ~skip).sum())
                                      for p, q in zip(c1, c2)})  # fmt: skip
    Path(os.environ.get("K_OUT", "k-synth3.json")).write_text(
        json.dumps(res, indent=1) + "\n"
    )
    print(json.dumps(res, indent=1))
