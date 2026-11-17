# c07 (P1, membership): A = 2 x (1 + eta s_f), s_f = +-1 alternating (sigma = eta
# under any definition), with M probe channels raised to 2 (1 + t eta); groups
# step t over 1.5..3.0; designs M=8 and M=32; arm p1. Whether the probes are
# kept shows as a shift of F of order t eta M / 64. Labelled probe.
import json, subprocess, sys
import numpy as np
W = "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly"
sys.path.insert(0, W + "/tools/oracles/casa")
import tfcrop_template as tt
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c07"
n = 256; f = np.arange(n); x = f.astype(float); eta = 0.01
ts = (1.5, 1.8, 1.9, 2.0, 2.1, 2.2, 2.5, 3.0)
job = []
for M in (8, 32):
    probes = np.round(np.linspace(10, 245, M)).astype(int)
    groups = []
    for t in ts:
        A = 2.0 * (1 + eta * (-1.0) ** f)
        A[probes] = 2.0 * (1 + t * eta)
        K = np.ones(n, bool); K[probes] = False
        Fp = tt.smooth_inplace(np.polyval(np.polyfit(x[K], A[K], 3), x))
        groups.append({"name": f"M{M}-t{t}", "A": A.tolist(), "m0": (A / Fp - 1).tolist(), "e": 0.02, "range": 2e-3, "probes": probes.tolist(), "t": t})
    spec = {"seed": 7000 + M, "planes_per_group": 138, "k_tests": 8, "cutoff": 3.0, "groups": groups}
    json.dump(spec, open(f"{P}/spec-M{M}.json", "w"))
    subprocess.run([sys.executable, W + "/tools/oracles/casa/tfcrop_readout.py", "design", f"{P}/spec-M{M}.json",
                    P + "/t24x40x256.ms.json", P, f"RO-M{M}"], check=True)
    job.append({"name": f"RO-M{M}.M{M}", "template": "/p/t24x40x256.ms", "data": f"/p/RO-M{M}.npz",
                "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False, "maxnpieces": 1}]})
json.dump(job, open(P + "/job.json", "w"), indent=1)
