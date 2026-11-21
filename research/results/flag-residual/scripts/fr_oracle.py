"""flag-residual (#51), gate G-Q: rang's QuartiCal-mode kernel against QuartiCal 0.2.7's
own numba kernels on the same residual array.

    python fr_oracle.py dump MS OUTDIR        # rang's venv: residual block + rang's flags
    python fr_oracle.py quartical OUTDIR      # in the oracle container: QuartiCal's flags
    python fr_oracle.py compare OUTDIR        # cell-by-cell difference, gate record

The block: the first scan of J1939-6342 (E2-N's flux calibrator) in the `on` MS after its
run, channels 0-127 (one QuartiCal chunk), residual = CORRECTED_DATA minus the scan's
per-channel complex median (rang's kernel), flags = FLAG any correlation, unwhitened,
diagonal correlations, threshold_bl 5, threshold_global 10, max_deviation 0.
"""

import json
import sys
from pathlib import Path

import numpy as np

FIELD = "J1939-6342"
NCHAN = 128
DIAG = (0, 3)
BL, GBL, MAXDEV = 5.0, 10.0, 0.0


def dump(ms, out):
    from rang import core, core_ms

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ext = core.extension()
    with core_ms.open_table(f"{ms}/FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(FIELD)
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        nant = t.nrows
    with core_ms.open_table(ms) as t:
        f = t.getcol("FIELD_ID")
        s = t.getcol("SCAN_NUMBER")
        sel = np.flatnonzero(f == fid)
        scan = int(s[sel].min())
        rows = sel[s[sel] == scan]
        chans = slice(0, NCHAN)
        data = t.getcol_rows("CORRECTED_DATA", rows, chans=chans).astype(np.complex64)
        flag = t.getcol_rows("FLAG", rows, chans=chans)
        a1 = t.getcol_rows("ANTENNA1", rows).astype(np.uint32)
        a2 = t.getcol_rows("ANTENNA2", rows).astype(np.uint32)
    nrow, nchan, ncorr = data.shape
    f8 = np.ascontiguousarray(flag, np.uint8)
    model = ext.flag_residual_median_model(
        data.view(np.float32), f8, nrow, nchan, ncorr
    )
    model = model.reshape(nchan, ncorr, 2).view(np.complex64)[..., 0]
    res = np.ascontiguousarray(data - model[None], np.complex64)
    res[~np.isfinite(res)] = 0
    rowflag = np.ascontiguousarray(flag.any(-1), np.int8)
    rang = ext.flag_residual_quartical(
        res.view(np.float32), rowflag.astype(np.uint8), nrow, nchan, ncorr, a1, a2, nant,
        list(DIAG), BL, GBL, MAXDEV,
    ).reshape(nrow, nchan)  # fmt: skip
    np.savez(out / "block.npz", res=res, flag=rowflag, a1=a1, a2=a2, nant=nant)
    np.save(out / "rang_flags.npy", rang)
    json.dump({"ms": str(ms), "field": FIELD, "scan": scan, "rows": int(nrow),
               "chans": NCHAN, "nant": int(nant)}, open(out / "block.json", "w"), indent=1)  # fmt: skip


def quartical(out):
    from quartical.flagging.flagging_kernels import (
        compute_bl_mad_and_med,
        compute_gbl_mad_and_med,
        compute_mad_flags,
        compute_whitened_residual,
    )

    out = Path(out)
    z = np.load(out / "block.npz")
    res, flag, a1, a2, nant = z["res"], z["flag"], z["a1"], z["a2"], int(z["nant"])
    a1, a2 = a1.astype(np.int64), a2.astype(np.int64)
    wres = compute_whitened_residual(res, np.ones(res.shape, np.float32))
    bl_re = compute_bl_mad_and_med(wres.real.copy(), flag, a1, a2, nant)
    bl_im = compute_bl_mad_and_med(wres.imag.copy(), flag, a1, a2, nant)
    g_re = compute_gbl_mad_and_med(wres.real.copy(), flag)
    g_im = compute_gbl_mad_and_med(wres.imag.copy(), flag)
    flags = compute_mad_flags(
        wres, g_re, g_im, bl_re, bl_im, a1, a2, GBL, BL, MAXDEV, DIAG, nant
    )
    np.save(out / "quartical_flags.npy", np.asarray(flags))
    import quartical

    json.dump({"quartical": getattr(quartical, "__version__", "unknown")},
              open(out / "quartical.json", "w"))  # fmt: skip


def compare(out):
    out = Path(out)
    r = np.load(out / "rang_flags.npy").astype(bool)
    q = np.load(out / "quartical_flags.npy").astype(bool)
    diff = r != q
    rec = {
        "cells": int(r.size),
        "rang_flagged": int(r.sum()),
        "quartical_flagged": int(q.sum()),
        "differing": int(diff.sum()),
        "differing_fraction": float(diff.mean()),
        "pass": bool(diff.mean() <= 1e-6),
        "first_differences": [[int(i), int(j)] for i, j in np.argwhere(diff)[:20]],
    }
    json.dump(rec, open(out / "gate-q.json", "w"), indent=1)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"dump": lambda: dump(sys.argv[2], sys.argv[3]),
     "quartical": lambda: quartical(sys.argv[2]),
     "compare": lambda: compare(sys.argv[2])}[cmd]()  # fmt: skip
