# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 7 (post hoc): where an arm's pass-1
floor sits. Per K1 solution the error against truth (ns, referenced to
m022); each pass-1 term swapped alone into truth (composite, primary cells).

    python cf_pass1.py CASE ARM
"""

import json
import sys

import cf_score as S
import numpy as np


def main(case, name):
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    interp = "nearest" if name == "near" else "linear"
    T = [S.tab(d / "truth-s0f" / n) for n in ("K", "G", "B")]
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    prim = rows.flag(S.K / "src.ms")
    tc, tf = rows.composite(T)
    out = {"case": case, "arm": name}
    k1 = S.tab(A / "K1")
    ta, va = S.kvals(k1)
    tt, vt = S.kvals(T[0])
    near = np.abs(tt[None, :] - ta[:, None]).argmin(1)
    vt = vt[near]
    e = np.abs(
        (va - va[:, rows.ref : rows.ref + 1]) - (vt - vt[:, rows.ref : rows.ref + 1])
    )
    big = np.argwhere(e > 1e-3)
    out[
        "K1 solutions off by > 1e-3 ns (interval, antenna, hand, error ns, truth ns)"
    ] = [
        [int(i), int(a), int(h), float(e[i, a, h]), float(vt[i, a, h])]
        for i, a, h in big
    ]
    out["K1 truth |tau| max per antenna"] = {
        int(a): float(np.nanmax(np.abs(vt[:, a])))
        for a in sorted(set(rows.a1) | set(rows.a2))
    }
    for n, i in (("K1", 0), ("G1", 1), ("B1", 2)):
        tl = list(T)
        tl[i] = S.tab(A / n)
        a, fa = rows.composite(tl, interp)
        out[f"truth_with_arm_{n}"] = S.rel(a, fa, tc, tf, prim, rows)
    # B1 per antenna against truth (1): median |B1 - 1| over unflagged channels
    b1 = S.tab(A / "B1")
    p, f = b1.params, b1.flags
    ant = b1.column("ANTENNA1")
    out["B1 |b-1| median per antenna"] = {
        int(a): float(np.median(np.abs(p[ant == a][0] - 1)[~f[ant == a][0]]))
        for a in sorted(set(rows.a1) | set(rows.a2))
        if (~f[ant == a][0]).any()
    }
    S.write(S.O / f"score-pass1-{case}-{name}.json", out)
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
