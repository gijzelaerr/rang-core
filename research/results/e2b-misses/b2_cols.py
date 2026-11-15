"""9.19's column steps on R/casa/e2b.ms (python-casacore, formats container).

    b2_cols.py MS save OUT_JSON
    b2_cols.py MS casa_done OUT_JSON
    b2_cols.py MS restore SAVE_JSON OUT_JSON
    b2_cols.py MS compare A FA B FB OUT_JSON

save:      record the column set and sha256 of FLAG+FLAG_ROW and of CORRECTED_DATA;
           copy CORRECTED_DATA to E2C_SAVE_CORRECTED_DATA (own tiled manager),
           FLAG -> E2C_SAVE_FLAG, FLAG_ROW copied to E2C_SAVE_FLAG_ROW; a new FLAG
           (own manager) and FLAG_ROW from the after-calibrate version. CASA's
           applycal then writes the existing CORRECTED_DATA (no column is added,
           so no data manager name clashes with CorrectedTiled / TiledCorrected).
casa_done: FLAG -> E2C_CASA_FLAG; a new FLAG and FLAG_ROW from the version again.
           rang's apply then writes E2C_RANG_CORRECTED_DATA (its own manager) and FLAG.
restore:   CORRECTED_DATA <- E2C_SAVE_CORRECTED_DATA; remove the E2C_* columns and
           the new FLAG; E2C_SAVE_FLAG -> FLAG; FLAG_ROW back; check both hashes and
           the column set against save's record.
compare:   2b's comparison (e2p_compare.py's rule) of A/FA (CASA) against B/FB.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from casacore.tables import makecoldesc, table

B = 250  # 9p reads of 2000-row blocks (262 MB) failed with ENOMEM
VERSION = "rang_apply_20261112T013707Z"  # FLAG before rang's apply (2b's prep)
EPS = float(np.finfo(np.float32).eps)


def col_hash(t, cols):
    h = hashlib.sha256()
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        for c in cols:
            h.update(np.ascontiguousarray(t.getcol(c, r0, k)).tobytes())
    return h.hexdigest()


def copy_col(t, src, dst):
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        t.putcol(dst, t.getcol(src, r0, k), r0, k)


def add_like(t, name, template, dm_name):
    dm = t.getdminfo(template)
    dm["NAME"] = dm_name
    if "SPEC" in dm and "HYPERCUBES" in dm["SPEC"]:
        dm["SPEC"].pop("HYPERCUBES", None)
    t.addcols(makecoldesc(name, t.getcoldesc(template)), dm)


def new_flag(t, ms, template, dm_name):
    add_like(t, "FLAG", template, dm_name)
    fv = table(ms + ".flagversions/flags." + VERSION, ack=False)
    assert fv.nrows() == t.nrows()
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        t.putcol("FLAG", fv.getcol("FLAG", r0, k), r0, k)
        t.putcol("FLAG_ROW", fv.getcol("FLAG_ROW", r0, k), r0, k)
    fv.close()


def compare(t, a, fa, b, fb):
    n = t.nrows()
    res = {"rows": n, "cells": 0, "compared_cells": 0, "flag_elements_differ": 0,
           "cells_over_class_c": 0, "max_eps_of_cell_max": 0.0, "max_rel": 0.0,
           "nonfinite_compared": 0, "columns": [a, fa, b, fb]}  # fmt: skip
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        c, g = t.getcol(a, r0, k), t.getcol(b, r0, k)
        fc, fg = t.getcol(fa, r0, k), t.getcol(fb, r0, k)
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
    return res


def main(ms, mode, *rest):
    out = Path(rest[-1])
    t = table(ms, readonly=(mode == "compare"), ack=False)
    rec = {"mode": mode}
    if mode == "save":
        assert "E2C_SAVE_FLAG" not in t.colnames() and "RANG_FLAG" in t.colnames()
        rec["columns"] = sorted(t.colnames())
        rec["flag_sha256"] = col_hash(t, ["FLAG", "FLAG_ROW"])
        rec["corrected_sha256"] = col_hash(t, ["CORRECTED_DATA"])
        # no data copy (a 36 GB write over 9p failed with ENOMEM): rename the
        # column and give CASA an empty CORRECTED_DATA on its own manager
        t.renamecol("CORRECTED_DATA", "E2C_SAVE_CORRECTED_DATA")
        add_like(t, "CORRECTED_DATA", "E2C_SAVE_CORRECTED_DATA", "E2CCasaCorrected")
        t.renamecol("FLAG", "E2C_SAVE_FLAG")
        t.addcols(makecoldesc("E2C_SAVE_FLAG_ROW", t.getcoldesc("FLAG_ROW")),
                  {"TYPE": "StandardStMan", "NAME": "E2CSaveFlagRow", "SPEC": {}})  # fmt: skip
        copy_col(t, "FLAG_ROW", "E2C_SAVE_FLAG_ROW")
        new_flag(t, ms, "E2C_SAVE_FLAG", "E2CFlagCasa")
    elif mode == "casa_done":
        t.renamecol("FLAG", "E2C_CASA_FLAG")
        new_flag(t, ms, "E2C_CASA_FLAG", "E2CFlagRang")
    elif mode == "restore":
        before = json.loads(Path(rest[0]).read_text())
        drop = [c for c in ("CORRECTED_DATA", "E2C_RANG_CORRECTED_DATA", "FLAG",
                            "E2C_CASA_FLAG") if c in t.colnames()]  # fmt: skip
        t.removecols(drop)
        t.renamecol("E2C_SAVE_CORRECTED_DATA", "CORRECTED_DATA")
        t.renamecol("E2C_SAVE_FLAG", "FLAG")
        copy_col(t, "E2C_SAVE_FLAG_ROW", "FLAG_ROW")
        t.removecols(["E2C_SAVE_FLAG_ROW"])
        rec["removed"] = drop + ["E2C_SAVE_FLAG_ROW"]
        rec["columns"] = sorted(t.colnames())
        rec["flag_sha256"] = col_hash(t, ["FLAG", "FLAG_ROW"])
        rec["corrected_sha256"] = col_hash(t, ["CORRECTED_DATA"])
        rec["columns_equal"] = rec["columns"] == before["columns"]
        rec["flag_equal"] = rec["flag_sha256"] == before["flag_sha256"]
        rec["corrected_equal"] = rec["corrected_sha256"] == before["corrected_sha256"]
    elif mode == "cleanup":
        # undo a save that failed while copying (harness incident, 2026-11-15)
        before = json.loads(Path(rest[0]).read_text())
        assert "E2C_SAVE_FLAG" not in t.colnames()
        extra = [c for c in t.colnames() if c.startswith("E2C_")]
        t.removecols(extra)
        rec["removed"] = extra
        rec["columns"] = sorted(t.colnames())
        rec["columns_equal"] = rec["columns"] == before
    elif mode == "compare":
        rec.update(compare(t, *rest[:4]))
    t.close()
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
