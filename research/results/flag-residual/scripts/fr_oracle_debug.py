"""flag-residual G-Q diagnosis: QuartiCal's rule restated in numpy on the oracle block, against
QuartiCal's and rang's flags (run in the oracle container with /opt/qc/bin/python)."""

import sys
from pathlib import Path

import numpy as np

o = Path(sys.argv[1])
z = np.load(o / "block.npz")
res, flag, a1, a2, nant = z["res"], z["flag"], z["a1"].astype(np.int64), z["a2"].astype(np.int64), int(z["nant"])
q = np.load(o / "quartical_flags.npy").astype(bool)
r = np.load(o / "rang_flags.npy").astype(bool)
bl = a1 * (2 * nant - a1 - 1) // 2 + a2
nrow, nchan, _ = res.shape
ok = flag != 1
out = np.zeros((nrow, nchan), bool)
for c in (0, 3):
    est = {}
    for part, v in (("re", res[..., c].real), ("im", res[..., c].imag)):
        g = v[ok]
        gmed = np.median(g)
        gmad = np.median(np.abs(g - gmed)) * np.float32(1.4826)
        est[part] = (gmed, gmad, {})
        for b in np.unique(bl):
            sel = (bl == b)[:, None] & ok
            x = v[sel]
            if x.size:
                m = np.median(x)
                est[part][2][b] = (m, np.median(np.abs(x - m)) * np.float32(1.4826))
    for row in range(nrow):
        if a1[row] == a2[row]:
            continue
        b = bl[row]
        if b not in est["re"][2] or est["re"][2][b][1] == 0 or est["im"][2][b][1] == 0:
            out[row] = True
            continue
        mre, sre = est["re"][2][b]
        mim, sim = est["im"][2][b]
        vre, vim = res[row, :, c].real, res[row, :, c].imag
        dev = ((vre - mre) / sre) ** 2 + ((vim - mim) / sim) ** 2
        gdev = ((vre - est["re"][0]) / est["re"][1]) ** 2 + ((vim - est["im"][0]) / est["im"][1]) ** 2
        out[row] |= (dev > 25) | (gdev > 100)
print("numpy restatement flagged", out.mean(), "vs quartical diff", (out != q).mean(), "vs rang diff", (out != r).mean())
d = np.argwhere(q != r)[:5]
for i, j in d:
    print("row", i, "chan", j, "a1", a1[i], "a2", a2[i], "q", q[i, j], "r", r[i, j], "np", out[i, j], "flag", flag[i, j])
