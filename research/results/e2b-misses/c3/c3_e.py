"""e2b-misses 9.28's ext4 steps (python-casacore, rang-formats-oracle).

    c3_e.py make SRC_MS E_MS FLAG_NPY OUT_JSON
    c3_e.py casa_done E_MS SRC_MS FLAG_NPY OUT_JSON
    c3_e.py subset E_MS FID OUT_MS OUT_JSON
    c3_e.py unitw MS OUT_JSON
    c3_e.py compare E_MS F_MS FID FLAG_NPY OUT_JSON

make:      TaQL copy of SRC (read-only mount of e3-20261111-input/e2b.ms) into E
           on ext4, as c2b_e.py's make: every row, the row columns, DATA, WEIGHT,
           SIGMA, FLAG_CATEGORY, every subtable. FLAG from FLAG_NPY (rang's FLAG
           after apply, packed), FLAG_ROW the source's: 9.28's check shows the pair
           is the after-calibrate version, hash for hash; FEED
           RECEPTOR_ANGLE -90 (2b's prep). Hashes as c2b's (C11).
casa_done: CORRECTED_DATA -> E2C_CASA_CORRECTED_DATA, FLAG -> E2C_CASA_FLAG, a new
           FLAG from FLAG_NPY and FLAG_ROW from SRC (the version again, as c2b_e.py).
subset:    the rows of field FID of E (row columns, DATA, FLAG, FLAG_ROW, WEIGHT,
           SIGMA, FLAG_CATEGORY, subtables) -> OUT_MS (rang's apply input).
unitw:     WEIGHT = 1 on MS (gate 3c's matched state; no WEIGHT_SPECTRUM).
compare:   2b's rule (c2b_win.py compare, e2p_compare.py): E's E2C_CASA_* on field
           FID's rows against F's E2C_RANG_CORRECTED_DATA and FLAG; also each side's
           flags against FLAG_NPY (the frozen after-apply flags).
"""

import hashlib
import json
import sys

import numpy as np
from casacore.tables import makecoldesc, table, taql

B = 500
EPS = float(np.finfo(np.float32).eps)
ROWS = ("UVW, ANTENNA1, ANTENNA2, TIME, TIME_CENTROID, INTERVAL, EXPOSURE, FIELD_ID, "
        "DATA_DESC_ID, SCAN_NUMBER, FLAG_ROW, ARRAY_ID, OBSERVATION_ID, PROCESSOR_ID, "
        "STATE_ID, FEED1, FEED2, SIGMA, WEIGHT, FLAG_CATEGORY, DATA, FLAG")  # fmt: skip


def unpack(p):
    return np.unpackbits(p, axis=-1, count=4).astype(bool)


def put_flags(t, packed, flag_row):
    n = t.nrows()
    assert packed.shape[0] == n == len(flag_row)
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        t.putcol("FLAG", unpack(packed[r0 : r0 + k]), r0, k)
        t.putcol("FLAG_ROW", flag_row[r0 : r0 + k], r0, k)


def source_flag_row(src):
    s = table(src, ack=False)
    fr = s.getcol("FLAG_ROW")
    s.close()
    return fr


def hashes(t):
    hd, hf = hashlib.sha256(), hashlib.sha256()
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        hd.update(np.ascontiguousarray(t.getcol("DATA", r0, k)).tobytes())
        hf.update(np.ascontiguousarray(t.getcol("FLAG", r0, k)).tobytes())
        hf.update(np.ascontiguousarray(t.getcol("FLAG_ROW", r0, k)).tobytes())
    return hd.hexdigest(), hf.hexdigest()


def field_rows(t, fid):
    f = t.getcol("FIELD_ID")
    idx = np.nonzero(f == fid)[0]
    assert len(idx) and np.array_equal(idx, np.arange(idx[0], idx[-1] + 1)), (
        "rows not contiguous"
    )
    return int(idx[0]), int(idx[-1]) + 1


def make(src, dst, npy, rec):
    packed = np.load(npy, mmap_mode="r")
    srctab = table(src, ack=False)
    taql(f"SELECT {ROWS} FROM $srctab GIVING '{dst}' AS PLAIN")
    srctab.close()
    t = table(dst, readonly=False, ack=False)
    assert packed.shape[0] == t.nrows()
    put_flags(t, packed, source_flag_row(src))
    feed = table(f"{dst}/FEED", readonly=False, ack=False)
    ra = feed.getcol("RECEPTOR_ANGLE")
    rec["receptor_angle_before"] = sorted({float(x) for x in ra.ravel()})
    feed.putcol("RECEPTOR_ANGLE", np.full_like(ra, -np.pi / 2))
    feed.close()
    t.flush()
    rec["rows"] = t.nrows()
    rec["columns"] = sorted(t.colnames())
    rec["subtables"] = sorted(
        k for k in t.getkeywords() if isinstance(t.getkeyword(k), str)
    )
    rec["data_sha256"], rec["flag_sha256"] = hashes(t)
    t.close()


def casa_done(e, src, npy, rec):
    packed = np.load(npy, mmap_mode="r")
    t = table(e, readonly=False, ack=False)
    t.renamecol("CORRECTED_DATA", "E2C_CASA_CORRECTED_DATA")
    t.renamecol("FLAG", "E2C_CASA_FLAG")
    dm = t.getdminfo("E2C_CASA_FLAG")
    dm["NAME"] = "E2CFlagRang"
    dm.get("SPEC", {}).pop("HYPERCUBES", None)
    t.addcols(makecoldesc("FLAG", t.getcoldesc("E2C_CASA_FLAG")), dm)
    put_flags(t, packed, source_flag_row(src))
    rec["columns"] = sorted(t.colnames())
    t.close()


def subset(e, fid, out, rec):
    t = table(e, ack=False)
    r0, r1 = field_rows(t, int(fid))
    cols = ROWS
    taql(f"SELECT {cols} FROM $t WHERE FIELD_ID == {int(fid)} GIVING '{out}' AS PLAIN")
    t.close()
    s = table(out, ack=False)
    rec.update(
        rows=s.nrows(), first_row_in_e=r0, end_row_in_e=r1, columns=sorted(s.colnames())
    )
    assert s.nrows() == r1 - r0
    s.close()


def unitw(ms, rec):
    t = table(ms, readonly=False, ack=False)
    assert "WEIGHT_SPECTRUM" not in t.colnames()
    n = t.nrows()
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        w = t.getcol("WEIGHT", r0, k)
        t.putcol("WEIGHT", np.ones_like(w), r0, k)
    t.flush()
    rec["weight_all_one"] = bool((t.getcol("WEIGHT") == 1).all())
    rec["rows"] = n
    t.close()


def compare(e, f, fid, npy, rec):
    packed = np.load(npy, mmap_mode="r")
    A = table(e, ack=False)
    Bt = table(f, ack=False)
    r_first, r_end = field_rows(A, int(fid))
    n = Bt.nrows()
    assert r_end - r_first == n
    for name in ("TIME", "ANTENNA1", "ANTENNA2"):
        assert np.array_equal(A.getcol(name, r_first, n), Bt.getcol(name)), name
    res = {"fid": int(fid), "rows": n, "first_row_in_e": r_first, "cells": 0,
           "compared_cells": 0, "flag_elements_differ": 0, "cells_over_class_c": 0,
           "max_eps_of_cell_max": 0.0, "max_rel": 0.0, "nonfinite_compared": 0,
           "casa_flag_ne_frozen": 0, "rang_flag_ne_frozen": 0}  # fmt: skip
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        c = A.getcol("E2C_CASA_CORRECTED_DATA", r_first + r0, k)
        fc = A.getcol("E2C_CASA_FLAG", r_first + r0, k)
        g = Bt.getcol("E2C_RANG_CORRECTED_DATA", r0, k)
        fg = Bt.getcol("FLAG", r0, k)
        fz = unpack(packed[r_first + r0 : r_first + r0 + k])
        res["casa_flag_ne_frozen"] += int((fc != fz).sum())
        res["rang_flag_ne_frozen"] += int((fg != fz).sum())
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
            ee = np.where(use & (cellmax > 0), d / (EPS * cellmax), 0.0)
            rel = np.where(use & (ag > 0), d / ag, 0.0)
        res["max_eps_of_cell_max"] = max(
            res["max_eps_of_cell_max"], float(np.nanmax(ee))
        )
        res["max_rel"] = max(res["max_rel"], float(np.nanmax(rel)))
    A.close()
    Bt.close()
    res["met"] = res["cells_over_class_c"] == 0 and res["flag_elements_differ"] == 0
    rec.update(res)


def main(mode, *a):
    rec = {"mode": mode}
    if mode == "make":
        make(a[0], a[1], a[2], rec)
    elif mode == "casa_done":
        casa_done(a[0], a[1], a[2], rec)
    elif mode == "subset":
        subset(a[0], a[1], a[2], rec)
    elif mode == "unitw":
        unitw(a[0], rec)
    elif mode == "compare":
        compare(a[0], a[1], a[2], a[3], rec)
    with open(a[-1], "w") as fh:
        json.dump(rec, fh, indent=1)
    print(json.dumps(rec)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
