"""Post hoc (e1-chain.md 8): rang's K table against CASA's gaincal K
(e1_casa_k.py output) and the truth, per scan: |rang - CASA| median, p95 and the
antennas above 0.03 ns (C1's K class B: median <= 0.01, p95 <= 0.03 ns)."""

import json
import sys

import numpy as np

sys.path.insert(0, r"C:\Users\gijsm\Worktrees\rang\fp-e1-chain\python")
from rang.formats import caltable

ktab, casa_json, truth_npz, out = sys.argv[1:5]
c = json.load(open(casa_json))  # noqa: SIM115
ct, ca = np.array(c["time"]), np.array(c["antenna"])
cp, cf = np.array(c["fparam"]), np.array(c["flag"], bool)
k = caltable.read(ktab)
a, tt_, f, p = k.column("ANTENNA1"), k.column("TIME"), k.flags[:, 0, :], k.params[:, 0, :]
truth = np.load(truth_npz)["gauge0_tau_ns"]
rep = {}
for i, tm in enumerate(np.unique(tt_)):
    s = tt_ == tm
    cs = np.abs(ct - tm) < 30
    order = np.argsort(ca[cs])
    rr, cc = p[s][np.argsort(a[s])], cp[cs][order]
    ok = ~f[s][np.argsort(a[s])] & ~cf[cs][order]
    d = np.abs(rr - cc)[ok]
    ants = np.sort(a[s])
    big = [(int(ants[j]), h, round(float(rr[j, h] - cc[j, h]), 4)) for j in range(len(ants))
           for h in range(2) if ok[j, h] and abs(rr[j, h] - cc[j, h]) > 0.03]  # fmt: skip
    rep[f"solution {i}"] = {
        "rang_minus_casa": {"median": float(np.median(d)), "p95": float(np.percentile(d, 95)),
                            "max": float(d.max())},  # fmt: skip
        "above_0.03ns": big,
        "rang_minus_truth_median": float(np.median(np.abs(rr - truth[ants])[ok])),
        "casa_minus_truth_median": float(np.median(np.abs(cc - truth[ants])[ok])),
    }
rep["scan_difference_rang"] = float(np.nanmedian(np.abs(np.diff([p[tt_ == t][np.argsort(a[tt_ == t])] for t in np.unique(tt_)], axis=0))))
print(json.dumps(rep, indent=1))
with open(out, "w") as fh:
    json.dump(rep, fh, indent=1)
