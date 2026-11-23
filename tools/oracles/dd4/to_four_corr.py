# SPDX-License-Identifier: MIT
"""DD4 amendment A4: rewrite a two-correlation (XX, YY) MS in place as four
correlations (XX, XY, YX, YY). XY and YX hold zero data, are flagged (or not,
with --unflag-cross), and carry the weight min(w_XX, w_YY) (amendment A2).

    python to_four_corr.py MS [--unflag-cross]

Runs under python-casacore in WSL (research/dd4-eso137.md, A4).
"""

import sys

import casacore.tables as pt
import numpy as np

CHUNK = 50_000


def main(ms, unflag_cross):
    t = pt.table(ms, readonly=False, ack=False)
    nrow = t.nrows()
    cols = ["DATA", "FLAG", "WEIGHT_SPECTRUM", "SIGMA_SPECTRUM", "WEIGHT", "SIGMA"]
    descs = {c: t.getcoldesc(c) for c in cols}
    dms = {c: t.getdminfo(c) for c in cols}
    # Old columns renamed, new ones added in their place.
    for c in cols:
        t.renamecol(c, c + "_2C")
    for c in cols:
        desc = dict(descs[c], name=c)
        dm = dict(dms[c])
        dm["NAME"] = dm["NAME"] + "4"
        spec = dict(dm["SPEC"])
        spec.pop("HYPERCUBES", None)
        tile = np.array(spec["DEFAULTTILESHAPE"])
        tile[0] = 4
        spec["DEFAULTTILESHAPE"] = tile
        dm["SPEC"] = spec
        t.addcols(pt.maketabdesc([pt.makecoldesc(c, desc)]), dm)
    for r0 in range(0, nrow, CHUNK):
        n = min(CHUNK, nrow - r0)
        for c in cols:
            two = t.getcol(c + "_2C", r0, n)
            four = np.zeros(two.shape[:-1] + (4,), two.dtype)
            four[..., 0], four[..., 3] = two[..., 0], two[..., 1]
            if c == "FLAG":
                cross = (
                    np.zeros_like(two[..., 0])
                    if unflag_cross
                    else np.ones_like(two[..., 0])
                )
                four[..., 1] = four[..., 2] = cross
            elif c in ("WEIGHT_SPECTRUM", "WEIGHT"):
                four[..., 1] = four[..., 2] = np.minimum(two[..., 0], two[..., 1])
            elif c in ("SIGMA_SPECTRUM", "SIGMA"):
                four[..., 1] = four[..., 2] = np.maximum(two[..., 0], two[..., 1])
            t.putcol(c, four, r0, n)
    t.removecols([c + "_2C" for c in cols])
    t.close()
    p = pt.table(ms + "/POLARIZATION", readonly=False, ack=False)
    p.putcell("NUM_CORR", 0, 4)
    p.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
    p.putcell("CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32))
    p.close()
    t = pt.table(ms, ack=False)
    print(ms, nrow, t.getcell("DATA", 0).shape, t.getcell("FLAG", 0)[0])


if __name__ == "__main__":
    main(sys.argv[1], "--unflag-cross" in sys.argv)
