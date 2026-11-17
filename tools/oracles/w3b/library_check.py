# SPDX-License-Identifier: GPL-3.0-or-later
"""Library check (not a gate; research/w3b-chainchunks.md 5.2): chunked solves equal one call.

python library_check.py MS CELLS [pol]
"""

import sys
import time

import numpy as np
from rang import cal_bandpass, cal_chain, cal_delay, cal_gain, cal_pol, core_chunks

ms = sys.argv[1]
cells = int(sys.argv[2]) if len(sys.argv) > 2 else 20000


def tiny(rows=None):
    return core_chunks.ChainBudget(
        chunk_bytes=core_chunks.CHAIN_ROW_BYTES * 200000 + cells * 96,
        fixed_bytes=0,
        limit_gb=None,
        chunk_rows=rows,
    )


def same(a, b, what):
    ta, tb = a[0], b[0]
    ok = cal_chain._sha(ta) == cal_chain._sha(tb)
    print(f"{what}: {'equal' if ok else 'DIFFER'}", flush=True)
    return ok


def run(fn, what, **kw):
    t0 = time.time()
    a = fn(ms, **kw)
    t1 = time.time()
    b = fn(ms, budget=tiny(), **kw)
    t2 = time.time()
    c = fn(ms, budget=tiny(7), **kw)
    t3 = time.time()
    print(f"  {t1 - t0:.1f} s / {t2 - t1:.1f} s / {t3 - t2:.1f} s")
    same(a, b, what + " tiny cells")
    same(a, c, what + " 7 rows")
    for x in (b, c):
        sa, sb = a[1], x[1]
        for k in ("iterations", "converged_fraction"):
            if hasattr(sa, k) and getattr(sa, k) != getattr(sb, k):
                print("   ", k, getattr(sa, k), getattr(sb, k))
    return a


from rang import cal_fluxscale


def model(field, stokes=(1, 0, 0, 0)):
    nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
    return cal_fluxscale.smodel_view(nrow, nchan, stokes)


common = {"field_id": 0, "refant": 0, "weight_column": None, "model": model(0)}
k = run(cal_delay.gaincal, "K inf", solint="inf", **common)
run(cal_delay.gaincal, "K int", solint="int", **common)
g = run(cal_gain.gaincal, "G inf", solint="inf", gaintable=[k[0]], **common)
run(cal_gain.gaincal, "G int p", solint="int", calmode="p", gaintable=[k[0]], **common)
run(
    cal_bandpass.bandpass,
    "B scan",
    combine="scan",
    fillgaps=3,
    gaintable=[k[0], g[0]],
    **common,
)
if len(sys.argv) > 3:
    pol = {
        "field_id": 1,
        "weight_column": None,
        "receptor_angle": -np.pi / 2,
        "model": model(1, (1, 0.05, 0.08, 0.0)),
    }
    run(cal_pol.gpol, "Gpol", solint="60s", refant=0, gaintable=[k[0], g[0]], **pol)
    run(cal_pol.kcross, "KCROSS", gaintable=[k[0], g[0]], **pol)
    run(cal_pol.xf, "Xf", combine="scan", gaintable=[k[0], g[0]], **pol)
    run(
        cal_pol.df,
        "Df",
        field_id=0,
        combine="scan",
        gaintable=[k[0], g[0]],
        weight_column=None,
        receptor_angle=-np.pi / 2,
        min_data_fraction=0.5,
        model=model(0),
    )
