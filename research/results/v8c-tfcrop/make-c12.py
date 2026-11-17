# c12 (band ends): A = B (1 + eta s_f), s_f alternating, eta 0.01, B smooth
# curved bands (cubics, a sine, a steep slope) with no channel past 2 sigma, so
# nothing is excluded and F = S(P) is known; reads F at the band ends. p7, p1.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
sys.path.insert(0, W + "/tools/oracles/casa")
import tfcrop_template as tt
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c12"
n = 256; f = np.arange(n); x = np.linspace(-1, 1, n); eta = 0.01
Bs = {"cubA": 2 + 0.3 * x - 0.4 * x**2 + 0.5 * x**3, "cubB": 2 - 0.5 * x + 0.6 * x**2 - 0.3 * x**3, "quad": 2 + 0.8 * x**2,
      "slope": 1.5 + 0.9 * x, "sine": 2 + 0.3 * np.sin(2.5 * x + 0.4), "sineB": 2 + 0.2 * np.sin(4 * x), "flat": np.full(n, 2.0), "x3": 2 + 0.8 * x**3}
tt.OPTS.update(overlap=1, sd_scope="global")
job = []
for arm, m, call in (("p7", 7, {}), ("p1", 1, {"maxnpieces": 1})):
    tt.OPTS["sched_full"] = {m: [(m, 3)] * 3}
    gs = []
    for nm, B in Bs.items():
        A = B * (1 + eta * (-1.0) ** f)
        F = tt.template(A, np.ones(n, bool), "poly", m, rule="full", clip=2.0, stop=0.0, nstages=3)
        gs.append({"name": nm, "A": A.tolist(), "m0": (A / F - 1).tolist(), "e": 0.02, "range": 3e-3})
    spec = {"seed": 12000 + m, "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": gs}
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json", P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
