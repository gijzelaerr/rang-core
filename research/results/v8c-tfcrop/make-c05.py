# c05 (P3, joins): piecewise-linear bands, exact within each piece, with
# small jumps at candidate piece edges (round, floor, ceil of k*256/7, and
# round of k*256/3). Reads piece boundaries and the template's behaviour at
# joins. Arms p7 and p3. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c05"
n = 256; f = np.arange(n)
rng = np.random.default_rng(5005)
def pwl(edges, jump):
    A = np.empty(n); lev = 2.0
    for j, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        s = rng.uniform(-2e-3, 2e-3)
        A[lo:hi] = lev + s * (f[lo:hi] - lo)
        lev = A[hi - 1] + s + jump * (1 if j % 2 == 0 else -1) * 2.0
    return A
k7 = np.arange(8) * n / 7
ed = {"round7": np.round(k7).astype(int), "floor7": np.floor(k7).astype(int), "ceil7": np.ceil(k7).astype(int),
      "round3": np.round(np.arange(4) * n / 3).astype(int)}
groups = [("r7+5e-3", pwl(ed["round7"], 5e-3), 8e-3), ("r7-5e-3", pwl(ed["round7"], -5e-3), 8e-3),
          ("r7+2e-2", pwl(ed["round7"], 2e-2), 3e-2), ("f7+5e-3", pwl(ed["floor7"], 5e-3), 8e-3),
          ("c7+5e-3", pwl(ed["ceil7"], 5e-3), 8e-3), ("r3+5e-3", pwl(ed["round3"], 5e-3), 8e-3),
          ("r3-5e-3", pwl(ed["round3"], -5e-3), 8e-3), ("r7+5e-3b", pwl(ed["round7"], 5e-3), 8e-3)]
job = []
for arm, call in (("p7", {}), ("p3", {"maxnpieces": 3})):
    spec = {"seed": 5100 + len(job), "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "edges": {k: v.tolist() for k, v in ed.items()},
            "groups": [{"name": nm, "A": A.tolist(), "e": 0.02, "range": R} for nm, A, R in groups]}
    json.dump(spec, open(f"{P}/spec-{arm}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-{arm}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-{arm}"], check=True)
    job.append({"name": f"RO-{arm}.{arm}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-{arm}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False} | call]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
