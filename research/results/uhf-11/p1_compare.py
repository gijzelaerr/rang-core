"""P1 comparator (research/uhf-11.md section 6): per scan, differing FLAG cells
over all cells (pass <= 1e-6) and FLAG_ROW equality.

    python -I p1_compare.py ROOT   (prints JSON)
"""

import json
import sys
from pathlib import Path

import numpy as np

TOL = 1e-6
root = Path(sys.argv[1])
out = {
    "criterion": f"differing cells / cells <= {TOL:g} and FLAG_ROW equal",
    "scans": {},
}
ok = True
for d in sorted((root / "labels" / "rang").iterdir()):
    t = root / "labels" / "tricolour" / d.name
    a = np.unpackbits(np.load(d / "flag.npy"), axis=1)
    b = np.unpackbits(np.load(t / "flag.npy"), axis=1)
    diff = int((a ^ b).sum())
    rang_only = int((a & ~b).sum())
    cells = a.size  # chan * corr is a multiple of 8 here, so no padding bits
    rows_equal = bool(
        np.array_equal(np.load(d / "flag_row.npy"), np.load(t / "flag_row.npy"))
    )
    frac = diff / cells
    passed = frac <= TOL and rows_equal
    ok &= passed
    out["scans"][d.name] = {
        "cells_packed": cells, "differ": diff, "rang_only": rang_only,
        "fraction": frac, "flag_row_equal": rows_equal,
        "rang_flagged": float(a.mean()), "tricolour_flagged": float(b.mean()),
        "pass": passed,
    }  # fmt: skip
out["pass"] = ok
print(json.dumps(out, indent=1))
