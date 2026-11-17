# c06 (P3, joins): two flat pieces with one step at channel 128 (the
# maxnpieces=2 edge), steps up and down of 1e-3, 5e-3, 2e-2: the step response
# of the template at a join, and whether it is linear and sign-symmetric. Arm p2.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c06"
n = 256; f = np.arange(n)
def step(j, slope=0.0):
    return 2.0 * (1 + slope * (f - 128)) * np.where(f < 128, 1.0, 1.0 + j)
groups = [(f"s{j:+g}", step(j), 1.5 * abs(j)) for j in (1e-3, -1e-3, 5e-3, -5e-3, 2e-2, -2e-2)]
groups += [("s+5e-3sl", step(5e-3, 1e-3), 7.5e-3), ("flat", step(0.0), 1e-3)]
spec = {"seed": 6006, "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0,
        "groups": [{"name": nm, "A": A.tolist(), "e": 0.02, "range": R} for nm, A, R in groups]}
json.dump(spec, open(f"{P}/spec-p2.json", "w"))
subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-p2.json",
                P + "/t24x40x256.ms.json", P, "RO-p2"], check=True)
json.dump([{"name": "RO-p2.p2", "template": "/p/t24x40x256.ms", "data": "/p/RO-p2.npz",
            "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False, "maxnpieces": 2}]}],
          open(P + "/job.json", "w"), indent=1)
