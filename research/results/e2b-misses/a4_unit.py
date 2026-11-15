"""Gate 3c's matched-state switch, copied verbatim from e2_post.py's UNIT_PY
(branch fp-e2-acceptance) for arm A4 (research/e2b-misses.md 9.9).

    a4_unit.py MS on|off OUT_JSON
"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, mode, out = sys.argv[1:4]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
rec = {"mode": mode}
if mode == "on":
    assert "RANG_FLAG" in cols and "E2_CASA_FLAG" not in cols
    n = t.nrows()
    rows_extra = 0
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        fr = t.getcol("FLAG_ROW", r0, k)
        rf = t.getcol("RANG_FLAG", r0, k)
        rows_extra += int((fr & ~rf.all(axis=(1, 2))).sum())
    rec["flag_row_not_all_rang_flag"] = rows_extra
    t.renamecol("FLAG", "E2_CASA_FLAG")
    t.renamecol("RANG_FLAG", "FLAG")
    t.renamecol("WEIGHT_SPECTRUM", "E2_WEIGHT_SPECTRUM")
    t.renamecol("WEIGHT", "E2_WEIGHT")
    desc = t.getcoldesc("E2_WEIGHT")
    # its own storage manager, so removecols drops it whole: rang's reader
    # rejects a StandardStMan that casacore added a column to and removed
    t.addcols(makecoldesc("WEIGHT", desc),
              {"TYPE": "StandardStMan", "NAME": "E2UnitWeight", "SPEC": {}})
    w = np.ones((n, t.getcell("E2_WEIGHT", 0).shape[0]), np.float32)
    t.putcol("WEIGHT", w)
else:
    assert "E2_CASA_FLAG" in cols
    t.removecols(["WEIGHT"])
    t.renamecol("E2_WEIGHT", "WEIGHT")
    t.renamecol("E2_WEIGHT_SPECTRUM", "WEIGHT_SPECTRUM")
    t.renamecol("FLAG", "RANG_FLAG")
    t.renamecol("E2_CASA_FLAG", "FLAG")
rec["columns"] = t.colnames()
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
