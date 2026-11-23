import sys, json
sys.path.insert(0, r"C:/Users/gijsm/Worktrees/rang/dd4-eso137/tools/oracles/dd4")
import numpy as np, dd4
from pathlib import Path
run = Path(r"D:/rang/outputs/dd4-20261123/run-02")
ctx = dd4.context(run); c = ctx["c"]
g = np.load(run / "O/cycle-0/gains.npz"); gains = np.array(g["gains"], complex)
gains[np.broadcast_to(g["flags"][..., None] != 0, gains.shape)] = 1.0
theirs = dd4.dd2.read_fits(run / "C1/c1-image-pb.fits")
flag = c["FLAG"].astype(bool) | c["FLAG_ROW"].astype(bool)[:, None, None]
w = c["WEIGHT_SPECTRUM"].astype(np.float64); ok = ~flag[..., 0] & ~flag[..., 3]
a = np.where(ok, w[..., 0], 0); b = np.where(ok, w[..., 3], 0)
with np.errstate(divide="ignore", invalid="ignore"):
    cands = {"min": np.minimum(a, b), "harmonic": np.where(ok, 4 / (1 / a + 1 / b), 0), "sum": a + b, "xx": a, "yy": b}
r = c["DATA"].astype(np.complex128); out = {}
for k, wi in cands.items():
    ctx["c"]["w_I"] = wi
    mine = dd4.facet_image(ctx, r, gains)
    sc = [float((theirs[s] * mine[s]).sum() / (mine[s] ** 2).sum()) for s in [ctx["interior"] & (ctx["idx"] == f) for f in range(4)]]
    out[k] = {"rel_diff": float(np.abs(mine - theirs)[ctx["interior"]].max() / np.abs(theirs).max()), "scale": sc}
    print(k, out[k], flush=True)
(run / "C1/c1-weight-candidates.json").write_text(json.dumps(out, indent=1))
