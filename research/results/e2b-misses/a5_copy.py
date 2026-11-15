"""9.18's reduced copy of R/casa/e2b.ms for WSClean (python-casacore).

    a5_copy.py SRC_MS DST_MS OUT_JSON

All rows; the columns WSClean reads, RANG_CORRECTED_DATA, FLAG = RANG_FLAG,
WEIGHT = 1; subtables copied by the deep copy. SRC is opened read-only.
"""

import json
import sys

import numpy as np
from casacore.tables import table, taql

COLS = ("UVW, ANTENNA1, ANTENNA2, TIME, TIME_CENTROID, INTERVAL, EXPOSURE, FIELD_ID, "
        "DATA_DESC_ID, SCAN_NUMBER, FLAG_ROW, ARRAY_ID, OBSERVATION_ID, PROCESSOR_ID, "
        "STATE_ID, FEED1, FEED2, SIGMA, WEIGHT, RANG_CORRECTED_DATA, RANG_FLAG AS FLAG")  # fmt: skip


def main(src, dst, out):
    t = table(src, ack=False)
    assert "RANG_FLAG" in t.colnames() and "E2_CASA_FLAG" not in t.colnames()
    sub = sorted(k for k in t.getkeywords() if isinstance(t.getkeyword(k), str))
    taql(f"SELECT {COLS} FROM $t GIVING '{dst}' AS PLAIN")
    t.close()
    c = table(dst, readonly=False, ack=False)
    n = c.nrows()
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        w = c.getcol("WEIGHT", r0, k)
        c.putcol("WEIGHT", np.ones_like(w), r0, k)
    rec = {"rows": n, "columns": c.colnames(), "src_subtables": sub,
           "dst_keywords": sorted(c.getkeywords()),
           "flag_desc": c.getcoldesc("FLAG")}  # fmt: skip
    c.close()
    json.dump(rec, open(out, "w"), indent=1, default=str)  # noqa: SIM115
    print(json.dumps(rec, default=str)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
