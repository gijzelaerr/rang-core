# c03 (P2, influence): exact line/cubic bands with single-channel
# perturbations of A; reads the template's response kernel. Arms p1, p7, line.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c03"
n = 256
x = np.linspace(-1, 1, n)
line = 2 + 0.5 * x
cub = 2.0 + 0.3 * x - 0.4 * x**2 + 0.5 * x**3
many = [1, 2, 3, 40, 100, 160, 220, 252, 254]
def sp(base, chans, d):
    A = base.copy(); A[chans] *= 1 + d; return A
groups = [("p+2e-3", sp(line, many, 2e-3), 3e-3), ("p-2e-3", sp(line, many, -2e-3), 3e-3),
          ("p+2e-2", sp(line, many, 2e-2), 0.03), ("p-2e-2", sp(line, many, -2e-2), 0.03),
          ("p+0.2", sp(line, many, 0.2), 0.3), ("one128", sp(line, [128], 2e-3), 3e-3),
          ("cub128", sp(cub, [128], 2e-3), 3e-3), ("edge", sp(line, [2, 253], 2e-3), 3e-3)]
job = []
for arm, call in (("p1", {"maxnpieces": 1}), ("p7", {}), ("line", {"freqfit": "line"})):
    spec = {"seed": 3000 + len(job), "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0,
            "groups": [{"name": nm, "A": A.tolist(), "e": 0.02, "range": R} for nm, A, R in groups]}
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
