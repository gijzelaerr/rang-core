# c04 (P0c, control T-a): c01's noisy0.01 and cubic averages A with
# Gaussian mirrored rows (sd 0.03) instead of readout rows; arm p1. If F is
# a function of A alone, c01's measured F predicts these flags. Labelled probe.
import json
import numpy as np
P = "D:/rang/outputs/v8c-tfcrop-20261116/probes/c04"
r = json.load(open("D:/rang/outputs/v8c-tfcrop-20261116/probes/c01/readout-c01.json"))
info = json.load(open(P + "/t24x40x256.ms.json"))
nbl, ntime, n = info["nbl"], info["ntime"], info["nchan"]
rng = np.random.default_rng(4004)
data = np.zeros((nbl * ntime, n, 4), np.complex64)
planes = []
for k in range(nbl * 4):
    b, c = divmod(k, 4)
    g = ("p1.noisy0.01", "p1.cubic")[k % 2]
    A = np.array(r[g]["A"])
    u = np.clip(0.03 * rng.standard_normal((ntime // 2, n)), -0.5, 0.5)
    u = np.concatenate([u, -u])
    data[b::nbl, :, c] = (A[None, :] * (1 + u)).astype(np.complex64)
    planes.append([b, c, g])
np.savez(P + "/C1.npz", data=data, flag=np.zeros(data.shape, bool))
json.dump({"planes": planes} | info, open(P + "/C1.json", "w"))
json.dump([{"name": "C1.p1", "template": "/p/t24x40x256.ms", "data": "/p/C1.npz",
            "calls": [{"mode": "tfcrop", "flagdimension": "freq", "extendflags": False, "maxnpieces": 1}]}],
          open(P + "/job.json", "w"), indent=1)
