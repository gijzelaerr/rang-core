import sys; sys.path.insert(0, r"C:/Users/gijsm/Worktrees/rang/dd4-eso137/tools/oracles/dd2")
import numpy as np, dd2
g = np.load(r"D:/rang/outputs/dd4-20261123/run-02/O/cycle-0/gains.npz")
G = g["gains"]; print(G.shape, g["flags"].shape)
for f in range(G.shape[3]): print(f, np.abs(G[..., f, :]).min(), np.abs(G[..., f, :]).max(), np.median(np.abs(G[..., f, :])))
a = dd2.read_fits(r"D:/rang/outputs/dd4-20261123/run-02/C1/c1-image-pb.fits"); d = dd2.read_fits(r"D:/rang/outputs/dd4-20261123/run-02/C1/c1-dirty.fits"); c0 = dd2.read_fits(r"D:/rang/outputs/dd4-20261123/run-02/C1/c0p-dirty.fits")
s = slice(1340, 1540)
print("pb/c0p centre", (a[s, s] * c0[s, s]).sum() / (c0[s, s] ** 2).sum(), "dirty/c0p centre", (d[s, s] * c0[s, s]).sum() / (c0[s, s] ** 2).sum())
