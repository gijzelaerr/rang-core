# SPDX-License-Identifier: MIT
"""DD4 amendment A4: rewrite a two-correlation (XX, YY) MS in place as four
correlations (XX, XY, YX, YY). XY and YX hold zero data, are flagged (or not,
with --unflag-cross), and carry the weight min(w_XX, w_YY) (amendment A2).

    python to_four_corr.py MS [--unflag-cross] [--matched | --equal-unflagged]

--matched (DD4 amendment A5): XX and YY both take the weight min(w_XX, w_YY)
and the flag XX | YY, so WSClean 3.7's facet-solution path, which weights
each hand by its own weight and its correction sum by w_XX only, grids the
same Stokes I as its plain path and as rang. --equal-unflagged (A5's
diagnostic copy): every weight 1, nothing flagged (FLAG_ROW cleared too),
flagged data zeroed.

Runs under python-casacore in WSL (research/dd4-eso137.md, A4).
"""

import sys

import casacore.tables as pt
import numpy as np

CHUNK = 50_000


def main(ms, unflag_cross, mode=None):
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
        flag2 = t.getcol("FLAG_2C", r0, n) | t.getcol("FLAG_ROW", r0, n)[:, None, None]
        either = flag2[..., 0] | flag2[..., 1]
        for c in cols:
            two = t.getcol(c + "_2C", r0, n)
            if mode == "matched":
                if c == "FLAG":
                    two = np.stack([either, either], -1)
                elif c in ("WEIGHT_SPECTRUM", "WEIGHT"):
                    m = np.minimum(two[..., 0], two[..., 1])
                    two = np.stack([m, m], -1)
                elif c in ("SIGMA_SPECTRUM", "SIGMA"):
                    m = np.maximum(two[..., 0], two[..., 1])
                    two = np.stack([m, m], -1)
            elif mode == "equal-unflagged":
                if c == "FLAG":
                    two = np.zeros_like(two)
                elif c == "DATA":
                    two = np.where(flag2, 0, two).astype(two.dtype)
                else:
                    two = np.ones_like(two)
            four = np.zeros(two.shape[:-1] + (4,), two.dtype)
            four[..., 0], four[..., 3] = two[..., 0], two[..., 1]
            if c == "FLAG":
                cross = (
                    np.zeros_like(two[..., 0])
                    if (unflag_cross or mode == "equal-unflagged")
                    else np.ones_like(two[..., 0])
                )
                four[..., 1] = four[..., 2] = cross
            elif c in ("WEIGHT_SPECTRUM", "WEIGHT"):
                four[..., 1] = four[..., 2] = np.minimum(two[..., 0], two[..., 1])
            elif c in ("SIGMA_SPECTRUM", "SIGMA"):
                four[..., 1] = four[..., 2] = np.maximum(two[..., 0], two[..., 1])
            t.putcol(c, four, r0, n)
    t.removecols([c + "_2C" for c in cols])
    if mode == "equal-unflagged":
        t.putcol("FLAG_ROW", np.zeros(nrow, bool))
    t.close()
    p = pt.table(ms + "/POLARIZATION", readonly=False, ack=False)
    p.putcell("NUM_CORR", 0, 4)
    p.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], np.int32))
    p.putcell("CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], np.int32))
    p.close()
    t = pt.table(ms, ack=False)
    print(ms, nrow, t.getcell("DATA", 0).shape, t.getcell("FLAG", 0)[0])


if __name__ == "__main__":
    mode = next(
        (m[2:] for m in sys.argv if m in ("--matched", "--equal-unflagged")), None
    )
    main(sys.argv[1], "--unflag-cross" in sys.argv, mode)
