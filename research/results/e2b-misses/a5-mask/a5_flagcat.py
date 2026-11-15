"""Arm A5 (research/e2b-misses.md 9.21): WSClean 3.7 needs a FLAG_CATEGORY
column, which a5_slim.py left out. Add it to the ext4 copy, empty, as in the
source (no cell defined), with the source's column description.

    a5_flagcat.py SRC_MS COPY_MS OUT_JSON
"""

import json
import sys

from casacore.tables import makecoldesc, table

src, dst, out = sys.argv[1:4]
s = table(src, readonly=True, ack=False)
d = table(dst, readonly=False, ack=False)
if "FLAG_CATEGORY" not in d.colnames():
    d.addcols(makecoldesc("FLAG_CATEGORY", s.getcoldesc("FLAG_CATEGORY")),
              {"TYPE": "StandardStMan", "NAME": "A5FlagCategory", "SPEC": {}})  # fmt: skip
rec = {"columns": sorted(d.colnames()), "defined_row0": bool(d.iscelldefined("FLAG_CATEGORY", 0))}
d.close()
s.close()
with open(out, "w") as f:
    json.dump(rec, f, indent=1)
print(json.dumps(rec))
