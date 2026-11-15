"""Arm A5 (research/e2b-misses.md 9.18, amendment): a private copy of gate
3c's matched state, so that A5 needs no rename on the shared CASA copy.
Reads R/casa/e2b.ms read-only in either state of a4_unit.py:
- FLAG: rang's FLAG after apply (RANG_FLAG when off, FLAG when on);
- WEIGHT: 1 (own storage manager), no WEIGHT_SPECTRUM;
- RANG_CORRECTED_DATA and the row columns as they are; subtables copied.
Then every copied column is compared with its source, chunk by chunk.

    a5_slim.py SRC_MS OUT_MS OUT_JSON
"""

import hashlib
import json
import sys

import numpy as np
from casacore.tables import makecoldesc, table

src, out, rec_path = sys.argv[1:4]
t = table(src, readonly=True, ack=False)
cols = t.colnames()
on = "E2_CASA_FLAG" in cols
flag_src = "FLAG" if on else "RANG_FLAG"
assert flag_src in cols and "RANG_CORRECTED_DATA" in cols
rows = ["UVW", "ANTENNA1", "ANTENNA2", "ARRAY_ID", "DATA_DESC_ID", "EXPOSURE",
        "FEED1", "FEED2", "FIELD_ID", "FLAG_ROW", "INTERVAL", "OBSERVATION_ID",
        "PROCESSOR_ID", "SCAN_NUMBER", "STATE_ID", "TIME", "TIME_CENTROID", "SIGMA"]  # fmt: skip
keep = rows + [flag_src, "RANG_CORRECTED_DATA", "WEIGHT" if on else "E2_NONE"]
keep = [c for c in keep if c in cols]
sel = t.query(columns=",".join(keep))
sel.copy(out, deep=True, valuecopy=True)
sel.close()
o = table(out, readonly=False, ack=False)
if flag_src != "FLAG":
    o.renamecol(flag_src, "FLAG")
if "WEIGHT" in o.colnames():
    o.removecols(["WEIGHT"])
desc = t.getcoldesc("WEIGHT" if not on else "E2_WEIGHT")
o.addcols(makecoldesc("WEIGHT", desc),
          {"TYPE": "StandardStMan", "NAME": "A5UnitWeight", "SPEC": {}})  # fmt: skip
n = o.nrows()
o.putcol("WEIGHT", np.ones((n, t.getcell("SIGMA", 0).shape[0]), np.float32))
o.flush()
# Compare every copied column with its source, and hash the two big ones.
pairs = [(c, c) for c in rows] + [("FLAG", flag_src), ("RANG_CORRECTED_DATA",) * 2]
diff = {}
h = {c: hashlib.sha256() for c in ("FLAG", "RANG_CORRECTED_DATA")}
for r0 in range(0, n, 2000):
    k = min(2000, n - r0)
    for oc, sc in pairs:
        a, b = o.getcol(oc, r0, k), t.getcol(sc, r0, k)
        if not np.array_equal(a, b):
            diff[oc] = diff.get(oc, 0) + 1
        if oc in h:
            h[oc].update(np.ascontiguousarray(a).tobytes())
w = o.getcol("WEIGHT")
rec = {"source_state": "on" if on else "off", "source_columns": sorted(cols),
       "nrows": n, "nrows_source": t.nrows(), "columns": sorted(o.colnames()),
       "chunks_differing": diff, "weight_all_one": bool((w == 1).all()),
       "sha256": {c: v.hexdigest() for c, v in h.items()},
       "subtables": sorted(o.getkeywords().keys())}  # fmt: skip
o.close()
t.close()
json.dump(rec, open(rec_path, "w"), indent=1)  # noqa: SIM115
print(json.dumps({k: v for k, v in rec.items() if k != "source_columns"}))
sys.exit(0 if not diff and rec["weight_all_one"] and n == rec["nrows_source"] else 1)
