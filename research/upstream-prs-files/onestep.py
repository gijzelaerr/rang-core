"""One-iteration change per solution interval between caps k and k+1:
QuartiCal's gain criterion vs the gauge-invariant change of the products G_p G_q^H.

usage: python onestep.py <setting dir> <k> <criterion>
"""
import json
import sys

import numpy as np
from daskms.experimental.zarr import xds_from_zarr

name, k, crit = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])


def load(label):
    ds = xds_from_zarr(f"{name}/{label}/gains.qc::G")[0]
    return ds.gains.values[..., 0, :], ds.gain_flags.values[..., 0]


g0, f0 = load(f"k{k}")
g1, f1 = load(f"k{k + 1}")
nt, nf, na, _ = g0.shape
ok = ((f0 == 0) & (f1 == 0)).all(axis=-1)  # intervals with every antenna unflagged
G0 = g0.reshape(nt, nf, na, 2, 2)
G1 = g1.reshape(nt, nf, na, 2, 2)

# QuartiCal's measure: relative change of the gains of the interval
dg = np.linalg.norm((G1 - G0).reshape(nt, nf, -1), axis=-1) / np.linalg.norm(G1.reshape(nt, nf, -1), axis=-1)
# Gauge-invariant: relative change of all baseline products G_p G_q^H
p, q = np.triu_indices(na, 1)
P0 = G0[:, :, p] @ np.conj(np.swapaxes(G0[:, :, q], -1, -2))
P1 = G1[:, :, p] @ np.conj(np.swapaxes(G1[:, :, q], -1, -2))
dp = np.linalg.norm((P1 - P0).reshape(nt, nf, -1), axis=-1) / np.linalg.norm(P1.reshape(nt, nf, -1), axis=-1)

out = {
    "k": k, "criterion": crit, "intervals_unflagged": int(ok.sum()),
    "frac_gain_change_below": float((dg[ok] < crit).mean()),
    "frac_product_change_below": float((dp[ok] < crit).mean()),
    "frac_product_change_below_x10": float((dp[ok] < 10 * crit).mean()),
    "median_gain_change": float(np.median(dg[ok])),
    "median_product_change": float(np.median(dp[ok])),
}
print(json.dumps(out))
