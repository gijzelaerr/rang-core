"""Post hoc: antenna-based decomposition of the target composite's amplitude
error (run -03), and F's and B's own amplitude errors against the truth."""

import json
import sys

import e1_score as S
import numpy as np

ctx = S.Ctx(sys.argv[1], "full")
K, G, B, F = (ctx.table(n) for n in ("K", "G", "B", "F"))
fid = ctx.fields
rows = ctx.rows(S.TARGET)[: 2016 * 8]
pc, pf = S.composite(
    ctx, rows, [K, F, B], [fid[S.FCAL], fid[S.GCAL], fid[S.FCAL]], ["linear"] * 3
)
pt = S.truth_product(ctx, rows)
la = np.log(np.abs(pc) / np.abs(pt))
la = np.where(pf, np.nan, la)
out = {}
for h in range(2):
    y = np.nanmean(la[..., h], 1)
    good = np.isfinite(y)
    a1, a2 = ctx.a1[rows][good], ctx.a2[rows][good]
    A = np.zeros((good.sum(), ctx.nant))
    A[np.arange(good.sum()), a1] = 1
    A[np.arange(good.sum()), a2] += 1
    sol = np.linalg.lstsq(A, y[good], rcond=None)[0]
    res = y[good] - A @ sol
    out[f"hand{h}_antenna_amp_log_err"] = {
        "median_abs": float(np.median(np.abs(sol))),
        "max_abs": float(np.abs(sol).max()),
        "values": np.round(sol, 5).tolist(),
        "row_residual_rms": float(res.std()),
    }
# F's amplitude per antenna (first gcal scan) against the truth G amplitude
fr = F.column("FIELD_ID") == fid[S.GCAL]
times = np.unique(F.column("TIME")[fr])
k = fr & (F.column("TIME") == times[0])
fa = np.abs(F.params[k, 0, :])
ga = np.abs(ctx.truth["gain"][0, F.column("ANTENNA1")[k], :])
out["F_over_Gtrue_scan1"] = np.round(fa / ga, 5).tolist()
# B amplitude (chain) vs truth, per antenna, normalised by its median over channels
ba = np.abs(B.params.astype(complex))
bt = np.abs(ctx.truth["bandpass"][B.column("ANTENNA1")])
r = ba / bt
r = r / np.median(r, axis=1, keepdims=True)
out["B_shape_err_median_abs"] = float(np.median(np.abs(r - 1)))
out["B_shape_err_p95"] = float(np.percentile(np.abs(r - 1), 95))
out["Asec_flagged"] = None
s = json.loads((ctx.rr / "calibrate" / "summary.json").read_text())
out["steps"] = [
    {k: st.get(k) for k in ("name", "type")}
    | (
        {
            "flagged_before": st["flagged"]["flagged_before"],
            "flagged_after": st["flagged"]["flagged_after"],
        }
        if "flagged" in st
        else {}
    )
    for st in s["steps"]
]
print(json.dumps(out, indent=1))
