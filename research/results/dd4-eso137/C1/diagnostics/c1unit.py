import sys, json
sys.path.insert(0, r"C:/Users/gijsm/Worktrees/rang/dd4-eso137/tools/oracles/dd4")
import numpy as np, dd4
from pathlib import Path
run = Path(r"D:/rang/outputs/dd4-20261123/run-02"); out = run / "C1-unit"; out.mkdir(exist_ok=True)
ctx = dd4.context(run); c = ctx["c"]
g = np.load(run / "O/cycle-0/gains.npz"); gains = np.ones(g["gains"].shape, complex)
dd4.dd2.write_h5(out / "unit.h5", gains, None, c, ctx["centres_t"], ctx["centres"])
dd4.run_wsl("step4_c1.sh", dd4.dd3.to_wsl(ctx["st"]["subms"]), "/home/gijsm/Build/tmp/20261123-dd4-c1u",
            dd4.dd3.to_wsl(out / "w"), dd4.dd3.to_wsl(out / "unit.h5"), dd4.dd3.to_wsl(run / "facets.reg"))
mine = dd4.facet_image(ctx, c["DATA"].astype(np.complex128), gains)
rec = {}
for k, f in (("C1_unit", "c1-image-pb.fits"), ("C1_unit_diagonal", "c1d-image-pb.fits")):
    th = dd4.dd2.read_fits(out / "w" / f)
    sc = [float((th[s] * mine[s]).sum() / (mine[s] ** 2).sum()) for s in [ctx["interior"] & (ctx["idx"] == i) for i in range(4)]]
    rec[k] = {"rel_diff": float(np.abs(mine - th)[ctx["interior"]].max() / np.abs(th).max()), "scale": sc}
print(json.dumps(rec, indent=1)); (out / "c1-unit.json").write_text(json.dumps(rec, indent=1))
