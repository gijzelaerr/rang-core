import sys

import numpy as np
from daskms.experimental.zarr import xds_from_zarr

for n in ("x4-027", "x4-pre", "x4-post", "x4-ref", "native-027", "native-post"):
    ds = xds_from_zarr(f"{sys.argv[1]}/out/{n}/gains.qc::G")[0]
    f = ds.gain_flags.values[..., 0] != 0
    g = ds.gains.values[..., 0, :]
    print(
        n,
        "flagged antenna-intervals %.4f" % f.mean(),
        "intervals all-ant-flagged %.4f" % f.all(-1).mean(),
        "finite %.4f" % np.isfinite(g).mean(),
        "max|g| unflagged %.3g" % np.abs(g[~f]).max() if (~f).any() else "",
        "max|g| flagged %.3g" % np.nanmax(np.abs(g[f])),
    )
for n in ("x4-archived", "x4-transposed", "x4-archived-ref"):
    z = np.load(f"{sys.argv[2]}/{n}.npz")
    f = z["flags"] != 0
    print(
        "rang",
        n,
        "flagged %.4f" % f.mean(),
        "all-flagged %.4f" % f.all(-1).mean(),
        "finite %.4f" % np.isfinite(z["gains"]).mean(),
    )
