"""Converged fraction, chi-squared and gauge-invariant model change per iteration cap.

usage: python analyse.py <setting dir> <time_interval> <freq_interval>
"""
import glob
import json
import os
import sys

import numpy as np
from casacore.tables import table
from daskms.experimental.zarr import xds_from_zarr

name, ti, fi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
t = table("scan9.ms", ack=False)
data = t.getcol("DATA")
model = t.getcol("MODEL_DATA")
flag = t.getcol("FLAG").any(axis=-1)
weight = t.getcol("WEIGHT_SPECTRUM")
a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
_, tidx = np.unique(t.getcol("TIME"), return_inverse=True)
t.close()
cross = a1 != a2
nchan = data.shape[1]
gt = tidx // ti
gf = np.arange(nchan) // fi


def load(path):
    ds = xds_from_zarr(f"{path}::G")[0]
    g = ds.gains.values[..., 0, :]  # time, freq, ant, corr
    gflag = ds.gain_flags.values[..., 0]
    return g, gflag, float(np.ravel(ds.conv_perc.values)[0]), int(np.ravel(ds.conv_iter.values)[0])


def predict(g):
    gp = g[gt[:, None], gf[None, :], a1[:, None]].reshape(len(a1), nchan, 2, 2)
    gq = g[gt[:, None], gf[None, :], a2[:, None]].reshape(len(a1), nchan, 2, 2)
    m = model.reshape(len(a1), nchan, 2, 2)
    return (gp @ m @ np.conj(np.swapaxes(gq, -1, -2))).reshape(len(a1), nchan, 4)


runs = {}
for d in sorted(glob.glob(f"{name}/*/gains.qc")):
    label = d.split("/")[1]
    g, gflag, perc, iters = load(d)
    ok = cross[:, None] & ~flag
    ok &= (gflag[gt[:, None], gf[None, :], a1[:, None]] == 0) & (gflag[gt[:, None], gf[None, :], a2[:, None]] == 0)
    v = predict(g)
    r2 = (weight * np.abs(data - v) ** 2)[ok]
    runs[label] = dict(conv_perc=perc, conv_iter=iters, chi2_mean=float(r2.mean()), n=int(ok.sum()), v=v, ok=ok)

ref = runs["k100"]
out = {}
for label, r in runs.items():
    ok = r["ok"] & ref["ok"]
    rel = np.abs(r["v"] - ref["v"])[ok] / np.maximum(np.abs(ref["v"])[ok], 1e-12)
    out[label] = dict(conv_perc=r["conv_perc"], conv_iter=r["conv_iter"], chi2_mean=r["chi2_mean"],
                      n_samples=r["n"], model_change_vs_k100_median=float(np.median(rel)),
                      model_change_vs_k100_p99=float(np.percentile(rel, 99)))
print(json.dumps(out, indent=1))
