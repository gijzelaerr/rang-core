"""check_uvtab.py: conversion check (a) of research/v5-obit.md, section 1.

    python3 check_uvtab.py MS FIELD FILE.uvtab   (in rang-obit, cwd = the uvtab's directory)

Reads the MS with python-casacore (cross-correlations of FIELD, XX and YY, DATA) and the
uvtab back through Obit's Python module, and prints both sides' row counts, unflagged
visibility counts, weight sums and visibility sums per correlation, and their ratio.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
from casacore.tables import table


def ms_side(ms, field):
    t = table(ms, ack=False)
    pol = table(ms + "/POLARIZATION", ack=False).getcell("CORR_TYPE", 0).tolist()
    ix = [pol.index(9), pol.index(12)]
    q = t.query(f"FIELD_ID=={field} && DATA_DESC_ID==0 && ANTENNA1!=ANTENNA2")
    out = {"rows": q.nrows(), "n": [0, 0], "w": [0.0, 0.0], "re": [0.0, 0.0], "im": [0.0, 0.0]}
    has_ws = "WEIGHT_SPECTRUM" in q.colnames() and q.iscelldefined("WEIGHT_SPECTRUM", 0)
    step = 100000
    for r0 in range(0, q.nrows(), step):
        n = min(step, q.nrows() - r0)
        d = q.getcol("DATA", r0, n)
        f = q.getcol("FLAG", r0, n) | q.getcol("FLAG_ROW", r0, n)[:, None, None]
        if has_ws:
            w = q.getcol("WEIGHT_SPECTRUM", r0, n)
        else:
            w = np.broadcast_to(q.getcol("WEIGHT", r0, n)[:, None, :], d.shape)
        for k, c in enumerate(ix):
            ok = ~f[:, :, c] & (w[:, :, c] > 0)
            out["n"][k] += int(ok.sum())
            out["w"][k] += float(w[:, :, c][ok].astype(np.float64).sum())
            out["re"][k] += float(d[:, :, c].real[ok].astype(np.float64).sum())
            out["im"][k] += float(d[:, :, c].imag[ok].astype(np.float64).sum())
    return out


def obit_side(path):
    import OErr
    import OSystem
    import UV

    err = OErr.OErr()
    OSystem.OSystem("chk", 1, 100, 0, [" "], 1, [os.path.dirname(os.path.abspath(path)) + "/"],
                    True, False, err)  # fmt: skip
    uv = UV.newPFUV("in", os.path.basename(path), 1, True, err)
    OErr.printErrMsg(err, "open")
    desc = uv.Desc.Dict
    nrp = desc["nrparm"]
    inc = desc["inaxes"]
    nchan, nstok = inc[desc["jlocf"]], inc[desc["jlocs"]]
    uv.List.set("nVisPIO", 1)
    uv.Open(UV.READONLY, err)
    out = {"rows": 0, "n": [0] * nstok, "w": [0.0] * nstok, "re": [0.0] * nstok,
           "im": [0.0] * nstok, "nchan": nchan, "nstok": nstok}  # fmt: skip
    nvis = desc["nvis"]
    import array  # noqa: F401  (VisBuf is a buffer)

    for _ in range(nvis):
        uv.Read(err)
        buf = np.frombuffer(uv.VisBuf, dtype=np.float32)
        rec = buf[nrp : nrp + 3 * nchan * nstok].reshape(nchan, nstok, 3)
        out["rows"] += 1
        for s in range(nstok):
            w = rec[:, s, 2].astype(np.float64)
            ok = w > 0
            out["n"][s] += int(ok.sum())
            out["w"][s] += float(w[ok].sum())
            out["re"][s] += float(rec[:, s, 0][ok].astype(np.float64).sum())
            out["im"][s] += float(rec[:, s, 1][ok].astype(np.float64).sum())
    uv.Close(err)
    OErr.printErrMsg(err, "read")
    return out


def main() -> None:
    ms, field, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    a = ms_side(ms, field)
    b = obit_side(path)
    rel = {k: [b[k][i] / a[k][i] - 1 if a[k][i] else None for i in range(2)]
           for k in ("w", "re", "im")}  # fmt: skip
    print(json.dumps({"ms": a, "obit": b, "relative_obit_minus_ms": rel,
                      "rows_equal": a["rows"] == b["rows"], "n_equal": a["n"] == b["n"][:2]},
                     indent=1))  # fmt: skip


if __name__ == "__main__":
    main()
