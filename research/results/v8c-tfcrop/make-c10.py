# c10 (P3, membership per piece): A = 2 (1 + eta s_f) alternating, with 4 probe
# channels raised to 2 (1 + t eta) inside one 7-piece (piece 3 = 110..145 or the
# last, 218..255), t in 1.9, 2.1, 2.3, 2.6; arm p7 (default). Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
sys.path.insert(0, W + "/tools/oracles/casa")
import tfcrop_template as tt
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c10"
n = 256; f = np.arange(n); x = f.astype(float); eta = 0.01
groups = []
for where, pr in (("mid", [115, 122, 131, 140]), ("last", [223, 230, 239, 248])):
    for t in (1.9, 2.1, 2.3, 2.6):
        A = 2.0 * (1 + eta * (-1.0) ** f); A[pr] = 2.0 * (1 + t * eta)
        groups.append({"name": f"{where}-t{t}", "A": A.tolist(), "m0": (A / 2.0 - 1).tolist(), "e": 0.02, "range": 2e-3, "probes": pr, "t": t})
spec = {"seed": 10010, "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": groups}
json.dump(spec, open(f"{P}/spec-p7.json", "w"))
subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-p7.json", P + "/t24x40x256.ms.json", P, "RO-p7"], check=True)
json.dump([{"name": "RO-p7.p7", "template": "/p/t24x40x256.ms", "data": "/p/RO-p7.npz",
            "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False}]}], open(P + "/job.json", "w"), indent=1)
