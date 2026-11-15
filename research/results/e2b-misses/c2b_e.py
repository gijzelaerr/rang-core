"""9.22's ext4 steps (python-casacore, formats container).

    c2b_e.py make SRC_MS E_MS VERSION_TABLE OUT_JSON
    c2b_e.py casa_done E_MS VERSION_TABLE OUT_JSON

make:      TaQL copy of SRC (read-only mount) into E on ext4: every row, the row
           columns, DATA, WEIGHT, SIGMA, FLAG_CATEGORY and every subtable; FLAG and
           FLAG_ROW from the after-calibrate version; sha256 of E's DATA and of its
           FLAG + FLAG_ROW (C11's ext4 side).
casa_done: CORRECTED_DATA -> E2C_CASA_CORRECTED_DATA, FLAG -> E2C_CASA_FLAG, a new
           FLAG and FLAG_ROW from the version (rang's apply input).
"""

import hashlib
import json
import sys

import numpy as np
from casacore.tables import makecoldesc, table, taql

B = 500
ROWS = ("UVW, ANTENNA1, ANTENNA2, TIME, TIME_CENTROID, INTERVAL, EXPOSURE, FIELD_ID, "
        "DATA_DESC_ID, SCAN_NUMBER, FLAG_ROW, ARRAY_ID, OBSERVATION_ID, PROCESSOR_ID, "
        "STATE_ID, FEED1, FEED2, SIGMA, WEIGHT, FLAG_CATEGORY, DATA, FLAG")  # fmt: skip


def put_version(t, version):
    fv = table(version, ack=False)
    assert fv.nrows() == t.nrows()
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        t.putcol("FLAG", fv.getcol("FLAG", r0, k), r0, k)
        t.putcol("FLAG_ROW", fv.getcol("FLAG_ROW", r0, k), r0, k)
    fv.close()


def hashes(t):
    hd, hf = hashlib.sha256(), hashlib.sha256()
    for r0 in range(0, t.nrows(), B):
        k = min(B, t.nrows() - r0)
        hd.update(np.ascontiguousarray(t.getcol("DATA", r0, k)).tobytes())
        hf.update(np.ascontiguousarray(t.getcol("FLAG", r0, k)).tobytes())
        hf.update(np.ascontiguousarray(t.getcol("FLAG_ROW", r0, k)).tobytes())
    return hd.hexdigest(), hf.hexdigest()


def main(mode, *a):
    rec = {"mode": mode}
    if mode == "make":
        src, dst, version, out = a
        srctab = table(src, ack=False)
        taql(f"SELECT {ROWS} FROM $srctab GIVING '{dst}' AS PLAIN")
        srctab.close()
        t = table(dst, readonly=False, ack=False)
        put_version(t, version)
        t.flush()
        rec["rows"] = t.nrows()
        rec["columns"] = sorted(t.colnames())
        rec["subtables"] = sorted(k for k in t.getkeywords() if isinstance(t.getkeyword(k), str))
        rec["data_sha256"], rec["flag_sha256"] = hashes(t)
        t.close()
    elif mode == "casa_done":
        e, version, out = a
        t = table(e, readonly=False, ack=False)
        t.renamecol("CORRECTED_DATA", "E2C_CASA_CORRECTED_DATA")
        t.renamecol("FLAG", "E2C_CASA_FLAG")
        dm = t.getdminfo("E2C_CASA_FLAG")
        dm["NAME"] = "E2CFlagRang"
        dm.get("SPEC", {}).pop("HYPERCUBES", None)
        t.addcols(makecoldesc("FLAG", t.getcoldesc("E2C_CASA_FLAG")), dm)
        put_version(t, version)
        rec["columns"] = sorted(t.colnames())
        t.close()
    with open(out, "w") as f:
        json.dump(rec, f, indent=1)
    print(json.dumps(rec)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
