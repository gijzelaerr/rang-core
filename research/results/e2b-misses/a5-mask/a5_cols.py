"""Arm A5 (research/e2b-misses.md 9.21): the column list and row count of an
MS, read-only, before and after every run.

    a5_cols.py MS OUT_JSON
"""

import json
import sys

from casacore.tables import table

ms, out = sys.argv[1:3]
t = table(ms, readonly=True, ack=False)
rec = {"columns": sorted(t.colnames()), "nrows": t.nrows()}
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
