# c02 (P0): exact (noise-free) polynomial bands, to characterise CASA's
# misfit on exact cubics found in c01. Arms p1, p7. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c02"
n = 256
x = np.linspace(-1, 1, n)
cub = 2.0 + 0.3 * x - 0.4 * x**2 + 0.5 * x**3
groups = [("cubic", cub), ("cubic-rev", cub[::-1]), ("cubic-x10", 10 * cub), ("quad", 2 + 0.5 * x**2),
          ("x3", 2 + 0.5 * x**3), ("line", 2 + 0.5 * x), ("cubic+1", cub + 1), ("quad2", 2 - 0.8 * x + 0.6 * x**2)]
job = []
for arm, call in (("p1", {"maxnpieces": 1}), ("p7", {})):
    spec = {"seed": 2000 + len(arm) + len(job), "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0,
            "groups": [{"name": nm, "A": A.tolist(), "e": 0.02, "range": 1.5e-3} for nm, A in groups]}
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
