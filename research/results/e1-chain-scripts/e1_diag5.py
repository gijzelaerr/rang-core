"""Post hoc: where the twin's target composite exceeds 1e-5 (4.1 noise-free tier)."""

import json
import sys

import e1_score as S
import numpy as np

ctx = S.Ctx(sys.argv[1], "small")
K, F, B = (ctx.table(n) for n in ("K", "F", "B"))
fid = ctx.fields
rows = ctx.rows(S.TARGET)
pc, pf = S.composite(
    ctx, rows, [K, F, B], [fid[S.FCAL], fid[S.GCAL], fid[S.FCAL]], ["linear"] * 3
)
pt = S.truth_product(ctx, rows)
e = np.where(pf, np.nan, np.abs(pc / pt - 1))
out = {
    "amp": float(np.nanmedian(np.abs(np.abs(pc / pt) - 1))),
    "phase": float(np.nanmedian(np.abs(np.angle(pc / pt)))),
}
out["by_chan_max"] = np.nanmax(e, axis=(0, 2))[::4].tolist()
t = ctx.c["TIME"][rows]
ut = np.unique(t)
out["by_time_max"] = [float(np.nanmax(e[t == x])) for x in ut]
out["by_ant_max"] = [
    float(np.nanmax(e[(ctx.a1[rows] == a) | (ctx.a2[rows] == a)]))
    for a in range(ctx.nant)
]
print(json.dumps(out, indent=1))
