"""W6 criterion 1c: MODEL_DATA differs from its 7+7j sentinel exactly on the
selected rows (field, scans, cross-correlations). python-casacore.

    python rows_check.py MS FIELD SCAN[,SCAN...]"""

import json
import sys

import numpy as np
import casacore.tables as ct


def main():
    ms, field, scans = (
        sys.argv[1],
        int(sys.argv[2]),
        [int(s) for s in sys.argv[3].split(",")],
    )
    t = ct.table(ms, ack=False)
    sel = (
        (t.getcol("FIELD_ID") == field)
        & np.isin(t.getcol("SCAN_NUMBER"), scans)
        & (t.getcol("ANTENNA1") != t.getcol("ANTENNA2"))
        & (t.getcol("DATA_DESC_ID") == 0)
    )
    changed = np.zeros(t.nrows(), bool)
    for s in range(0, t.nrows(), 2048):
        n = min(2048, t.nrows() - s)
        changed[s : s + n] = (t.getcol("MODEL_DATA", s, n) != 7 + 7j).any(axis=(1, 2))
    out = {
        "selected": int(sel.sum()),
        "changed": int(changed.sum()),
        "equal_sets": bool(np.array_equal(sel, changed)),
    }
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
