"""9.22's Windows steps, native (no 9p), with rang's reader and writer.

    python c2b_win.py hash_src OUT_JSON      C11's source side: sha256 of R/casa/e2b.ms's
                                             DATA and of the version's FLAG + FLAG_ROW
    python c2b_win.py apply OUT_JSON         rang's apply (new P) on the D: copy into
                                             E2C_RANG_CORRECTED_DATA and FLAG
    python c2b_win.py compare WHICH OUT_JSON WHICH: c9 | measure | beside (2b's rule)
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))

R = Path("D:/rang/outputs/e2-20261111-20-e2b")
SRC = R / "casa" / "e2b.ms"
VERSION = SRC.parent / "e2b.ms.flagversions" / "flags.rang_apply_20261112T013707Z"
COPY = Path("D:/rang/outputs/e2b-2b-20261115/e2b-2b.ms")
B = 500
EPS = float(np.finfo(np.float32).eps)


def hash_src():
    from rang import core_ms

    hd, hf = hashlib.sha256(), hashlib.sha256()
    with core_ms.open_table(SRC) as t, core_ms.open_table(VERSION) as v:
        n = t.nrows
        assert v.nrows == n
        for r0 in range(0, n, B):
            k = min(B, n - r0)
            hd.update(np.ascontiguousarray(t.getcol("DATA", r0, k)).tobytes())
            hf.update(np.ascontiguousarray(v.getcol("FLAG", r0, k)).tobytes())
            hf.update(np.ascontiguousarray(v.getcol("FLAG_ROW", r0, k)).tobytes())
    return {"rows": n, "data_sha256": hd.hexdigest(), "flag_sha256": hf.hexdigest()}


def apply():
    from rang import applycal

    s = json.loads((R / "rang-run" / "apply" / "summary.json").read_text())
    calls = []
    for e in s["applied"]:
        applycal.applycal(
            COPY, [R / "rang-run" / "calibrate" / n for n in e["tables_applied"]],
            interp=[t["interp"] for t in e["tables"]],
            gainfield=[t["gainfield"] for t in e["tables"]],
            calwt=[t["calwt"] for t in e["tables"]], field=e["fields"],
            applymode=e["applymode"], scan=e["scans"], parang=e["parang"],
            frame=e["frame"], receptor_angle=e["receptor_angle"], parang_flags="none",
            column="E2C_RANG_CORRECTED_DATA",
        )  # fmt: skip
        calls.append({"fields": e["fields"], "parang": e["parang"], "frame": e["frame"]})
    return {"calls": calls}


PAIRS = {  # (table of A, A, FA) against (table of B, B, FB); A is the reference side (CASA)
    "c9": ((COPY, "E2C_CASA_CORRECTED_DATA", "E2C_CASA_FLAG"),
           (SRC, "RANG_CORRECTED_DATA", "RANG_FLAG")),
    "measure": ((COPY, "E2C_CASA_CORRECTED_DATA", "E2C_CASA_FLAG"),
                (COPY, "E2C_RANG_CORRECTED_DATA", "FLAG")),
    "beside": ((SRC, "RANG_CORRECTED_DATA", "RANG_FLAG"),
               (COPY, "E2C_RANG_CORRECTED_DATA", "FLAG")),
}  # fmt: skip


def compare(which):
    """2b's rule (e2p_compare.py): c = A (CASA side), g = B (rang side)."""
    from rang import core_ms

    (ta, a, fa), (tb, b, fb) = PAIRS[which]
    res = {"which": which, "columns": [str(ta), a, fa, str(tb), b, fb], "cells": 0,
           "compared_cells": 0, "flag_elements_differ": 0, "cells_over_class_c": 0,
           "max_eps_of_cell_max": 0.0, "max_rel": 0.0, "nonfinite_compared": 0}  # fmt: skip
    with core_ms.open_table(ta) as A, core_ms.open_table(tb) as Bt:
        n = A.nrows
        assert Bt.nrows == n
        res["rows"] = n
        for name in ("TIME", "ANTENNA1", "ANTENNA2"):
            assert np.array_equal(A.getcol(name), Bt.getcol(name)), name
        for r0 in range(0, n, B):
            k = min(B, n - r0)
            c, g = A.getcol(a, r0, k), Bt.getcol(b, r0, k)
            fc, fg = A.getcol(fa, r0, k), Bt.getcol(fb, r0, k)
            res["flag_elements_differ"] += int((fc != fg).sum())
            res["cells"] += int(fc.shape[0] * fc.shape[1])
            use = ~(fc | fg)
            ag = np.abs(g)
            cellmax = ag.max(-1, keepdims=True)
            d = np.abs(c.astype(np.complex128) - g.astype(np.complex128))
            tol = np.maximum(1e-6 * ag, 11 * EPS * cellmax)
            bad = use & ~(d <= tol)
            res["nonfinite_compared"] += int((use & ~np.isfinite(d)).sum())
            res["cells_over_class_c"] += int(bad.any(-1).sum())
            res["compared_cells"] += int(use.any(-1).sum())
            with np.errstate(divide="ignore", invalid="ignore"):
                e = np.where(use & (cellmax > 0), d / (EPS * cellmax), 0.0)
                rel = np.where(use & (ag > 0), d / ag, 0.0)
            res["max_eps_of_cell_max"] = max(res["max_eps_of_cell_max"], float(np.nanmax(e)))
            res["max_rel"] = max(res["max_rel"], float(np.nanmax(rel)))
    res["met"] = res["cells_over_class_c"] == 0 and res["flag_elements_differ"] == 0
    return res


def main(mode, *a):
    t0 = time.time()
    if mode == "hash_src":
        rec = hash_src()
    elif mode == "apply":
        rec = apply()
    else:
        rec = compare(a[0])
    rec["secs"] = time.time() - t0
    Path(a[-1]).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
