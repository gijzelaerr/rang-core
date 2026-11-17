# c11: (a) RS, p1: absolute against relative residual: line band 1..4 times
# (1 + eta s_f) alternating, 4 probes at relative height t eta at the low end
# (ch 10-40) or the high end (215-245), t 1.6..2.6. (b) OW, p7: channel
# ownership: flat band 2.0, one dip of -2e-3 at channel 0, 1, 2, 37, 38, 253,
# 254 or 255. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c11"
n = 256; f = np.arange(n); eta = 0.01
B = 1 + 3 * f / 255.0
rs = []
for where, pr in (("low", [10, 20, 30, 40]), ("high", [215, 225, 235, 245])):
    for t in (1.6, 1.9, 2.2, 2.6):
        A = B * (1 + eta * (-1.0) ** f); A[pr] = B[pr] * (1 + t * eta)
        rs.append({"name": f"{where}-t{t}", "A": A.tolist(), "m0": (A / B - 1).tolist(), "e": 0.02, "range": 2e-3, "probes": pr, "t": t})
ow = []
for c in (0, 1, 2, 37, 38, 253, 254, 255):
    A = np.full(n, 2.0); A[c] *= 1 - 2e-3
    ow.append({"name": f"dip{c}", "A": A.tolist(), "e": 0.02, "range": 1e-3})
job = []
for nm, groups, call in (("RS", rs, {"maxnpieces": 1}), ("OW", ow, {})):
    spec = {"seed": 11000 + len(job), "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": groups}
    json.dump(spec, open(f"{P}/spec-{nm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{nm}.json", P + "/t24x40x256.ms.json", P, f"RO-{nm}"], check=True)
    job.append({"name": f"RO-{nm}.{nm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{nm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
