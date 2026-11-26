"""DD8 A3 (post hoc): e/e-hat on converged cells; d3 gain tails on unchanged-data solves; where |g| > 10 sits."""

import json
from pathlib import Path

import numpy as np
from rang import core_ms

R = "D:/rang/outputs/dd8-20261125"
D7 = "D:/rang/outputs/dd7-20261125"
t = core_ms.open_table(D7 + "/b/sim.ms")
TIME = t.getcol("TIME")
t.close()
tindex = np.unique(TIME, return_inverse=True)[1]
gt = np.load(D7 + "/b/truth.npz")["gains"]  # (nblock, nant, ndir, 2)
nant = gt.shape[1]
p, q = np.triu_indices(nant, 1)
out = {"e_converged": {}, "d3_tails": {}, "d3_large": {}}
for name, ti in (("O-F", 4), ("O-F-2000", 4), ("O-F-64", 64), ("O-X", 4), ("BH-F", 4)):
    z = np.load(f"{R}/grid/{name}.npz")
    rec = json.loads(Path(f"{R}/grid/{name}.json").read_text())
    g, f, cv = z["gains"][:, 0], z["flags"][:, 0] != 0, z["converged"][:, 0]
    blk4, blkt = tindex // 4, tindex // ti
    nint = g.shape[0]
    pbar = np.stack(
        [gt[np.unique(blk4[blkt == j])].mean(0)[..., None, :] for j in range(nint)]
    )  # placeholder shape fix below
    pt = gt[:, p] * np.conj(gt[:, q])  # (nblock, npair, ndir, 2)
    pbar = np.stack([pt[np.unique(blk4[blkt == j])].mean(0) for j in range(nint)])
    ps = g[:, p] * np.conj(g[:, q])
    rel = np.abs(ps - pbar) / np.abs(pbar)
    ok = ~f[:, p] & ~f[:, q]
    both = ok & cv[:, p] & cv[:, q]
    res = []
    for d in range(1, 4):
        m_all = np.broadcast_to(ok[..., d, None], rel[..., d, :].shape)
        m_cv = np.broadcast_to(both[..., d, None], rel[..., d, :].shape)
        e_all = float(np.median(rel[..., d, :][m_all]))
        e_cv = float(np.median(rel[..., d, :][m_cv])) if m_cv.any() else float("nan")
        eh = rec["ehat_d"][d]
        res.append(
            {
                "dir": d,
                "e_over_ehat_all": e_all / eh,
                "e_over_ehat_converged_pairs": e_cv / eh,
                "converged_pair_fraction": float(m_cv.sum() / m_all.sum()),
            }
        )
    out["e_converged"][name] = res
for name, path in (
    ("real-MF-4 (DD7)", D7 + "/grid/real-MF-4.npz"),
    ("L2000-4 (DD7)", D7 + "/grid/L2000.npz"),
    ("L2000-16", R + "/grid/L2000-16.npz"),
    ("L2000-64", R + "/grid/L2000-64.npz"),
    ("R12", R + "/grid/R12.npz"),
    ("R2 (DD7)", D7 + "/grid/R2.npz"),
    ("RH-MF", R + "/grid/RH-MF.npz"),
    ("RH-L2000", R + "/grid/RH-L2000.npz"),
    ("O-F", R + "/grid/O-F.npz"),
    ("O-F-2000", R + "/grid/O-F-2000.npz"),
):
    z = np.load(path)
    g, f, cv = (
        np.abs(z["gains"][:, 0, :, 3, :]),
        z["flags"][:, 0, :, 3] != 0,
        z["converged"][:, 0, :, 3],
    )
    a = g[~f]
    out["d3_tails"][name] = {
        "p50": float(np.median(a)),
        "p99": float(np.percentile(a, 99)),
        "max": float(a.max()),
        "n_gt10": int((g.max(-1) > 10)[~f].sum()),
    }
    big = (g.max(-1) > 10) & ~f
    if big.any():
        ti_last = g.shape[0] - 1
        it, ant = np.nonzero(big)
        out["d3_large"][name] = {
            "cells": int(big.sum()),
            "converged": int(cv[big].sum()),
            "in_last_interval": int((it == ti_last).sum()),
            "antennas": np.unique(ant, return_counts=True)[0].tolist(),
            "counts": np.unique(ant, return_counts=True)[1].tolist(),
            "intervals": sorted(set(it.tolist()))[:20],
        }
Path(R + "/posthoc.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
