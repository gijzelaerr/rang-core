# c01 (v8c-tfcrop-poly.md P0/P1): readout calibration on exact-fit groups and a
# first coarse readout of noisy groups; arms p1, p3, p7, line. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
sys.path.insert(0, W + "/python")
from rang import tfcrop
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c01"
n = 256
x = np.linspace(-1, 1, n)
rng = np.random.default_rng(1601)
def pw(k):
    edges = np.linspace(0, n, k + 1).round().astype(int)
    out = np.empty(n)
    for lo, hi in zip(edges[:-1], edges[1:]):
        p = rng.normal(0, 0.3, 4)
        xx = x[lo:hi]
        out[lo:hi] = 2.0 + p[0] + p[1] * xx + p[2] * xx**2 + p[3] * xx**3
    return np.maximum(out, 0.5)
cub = lambda: 2.0 + rng.normal(0, 0.3) * x + rng.normal(0, 0.3) * x**2 + rng.normal(0, 0.3) * x**3
groups = []
groups.append(("line", 2.0 + 0.5 * x, 0.02, 2e-3))
groups.append(("cubic", 2.0 + 0.3 * x - 0.4 * x**2 + 0.5 * x**3, 0.02, 2e-3))
groups.append(("pw7", pw(7), 0.02, 2e-3))
groups.append(("pw3", pw(3), 0.02, 2e-3))
for eta in (0.003, 0.01):
    groups.append((f"noisy{eta}", cub() * (1 + eta * rng.standard_normal(n)), 0.02, 0.01))
groups.append(("noisy0.03", cub() * (1 + 0.03 * rng.standard_normal(n)), 0.04, 0.02))
A = cub() * (1 + 0.01 * rng.standard_normal(n))
at = rng.choice(n, 6, replace=False); A[at] += rng.uniform(0.3, 1.0, 6)
groups.append(("spikes0.01", A, 0.02, 0.01))
arms = {"p1": ("poly", 1), "p3": ("poly", 3), "p7": ("poly", 7), "line": ("line", 1)}
job = []
for arm, (kind, mp) in arms.items():
    spec = {"seed": 1700 + mp, "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": []}
    for name, A, e, R in groups:
        F = tfcrop.robust_fit(A, np.ones(n, bool), kind, mp)
        spec["groups"].append({"name": name, "A": A.tolist(), "m0": (A / F - 1).tolist(), "e": e, "range": R})
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    call = {"mode": "tfcrop", "flagdimension": "freq", "extendflags": False}
    call |= {"freqfit": "line"} if kind == "line" else {"maxnpieces": mp}
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz", "calls": [call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
