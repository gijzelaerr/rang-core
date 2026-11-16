# c09 (P1/P3 on gate-like averages): V8b-style smooth bandpasses (cubic + 0.2 sin)
# times (1 + eta g), eta 0.004-0.02, two groups with positive spikes; arms p7
# (default), p1, line; ladders centred on the current best model. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
sys.path.insert(0, W + "/tools/oracles/casa")
import tfcrop_template as tt
tt.OPTS.update(overlap=1, overlap_left=0, sched={1: [1, 1, 1], 2: [1, 2, 2], 3: [1, 3, 3], 7: [1, 7, 7]})
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c09"
n = 256; x = np.linspace(-1, 1, n)
rng = np.random.default_rng(9009)
groups = []
for k, eta in enumerate((0.004, 0.007, 0.01, 0.01, 0.014, 0.02, 0.01, 0.007)):
    p = rng.normal(0, 0.3, 4)
    band = np.abs(1 + p[0] * x + p[1] * x**2 + p[2] * x**3 + 0.2 * np.sin(3 * x + p[3])) * 2.0
    A = band * (1 + eta * rng.standard_normal(n))
    if k >= 6:
        at = rng.choice(n, 5, replace=False); A[at] *= 1 + rng.uniform(0.05, 0.5, 5)
    A = np.maximum(A, 0.2)
    groups.append((f"bp{k}-eta{eta}", A, 0.02 if eta < 0.015 else 0.03))
base = dict(rule="custom", clip=2.0, stop=0.0, nstages=5)
job = []
for arm, kind, mp, call in (("p7", "poly", 7, {}), ("p1", "poly", 1, {"maxnpieces": 1}), ("line", "line", 1, {"freqfit": "line"})):
    gs = []
    for nm, A, e in groups:
        F = tt.template(A, np.ones(n, bool), kind, mp, **base)
        gs.append({"name": nm, "A": A.tolist(), "m0": (A / F - 1).tolist(), "e": e, "range": 3e-3})
    spec = {"seed": 9100 + mp + len(arm), "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": gs}
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
