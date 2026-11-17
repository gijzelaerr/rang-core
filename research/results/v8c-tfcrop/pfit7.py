# pfit7.py BATCH KEY NP: fit measured F = S(P), P piecewise cubic with NP pieces, edges by coordinate descent
import json, sys
import numpy as np
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/tools/oracles/casa")
import tfcrop_template as tt
n = 256; f = np.arange(n)
S = np.array([tt.smooth_inplace(np.eye(n)[i]) for i in range(n)]).T
def basis(edges):
    cols = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        xx = (f - (lo + hi) / 2) / 64.0
        for d in range(4): cols.append(np.where((f >= lo) & (f < hi), xx**d, 0.0))
    return np.array(cols).T
b, k, NP = sys.argv[1], sys.argv[2], int(sys.argv[3])
r = json.load(open(f"D:/rang/outputs/v8c-tfcrop-20261116/probes/{b}/readout-{b}.json"))
A, F, lo, hi = (np.array(r[k][q]) for q in ("A", "F", "lo", "hi"))
ok = np.isfinite(lo) & np.isfinite(hi)
wt = np.where(ok, 1 / (0.5 * (hi - lo) + 2e-6 * A), 0)
def chi(edges):
    Bm = S @ basis(edges); c, *_ = np.linalg.lstsq(Bm * wt[:, None], F * wt, rcond=None)
    return np.sqrt(np.sum(((Bm @ c - F) * wt) ** 2) / ok.sum())
edges = list(np.round(np.arange(NP + 1) * n / NP).astype(int))
print("round edges", edges, "chi", round(chi(edges), 2))
for sweep in range(3):
    for j in range(1, NP):
        best = min((chi(edges[:j] + [e] + edges[j + 1:]), e) for e in range(edges[j - 1] + 5, edges[j + 1] - 4))
        edges[j] = best[1]
print("best edges ", edges, "chi", round(chi(edges), 2))
