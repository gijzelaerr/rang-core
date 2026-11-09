"""Where rang's flag stage and Tricolour 0.2.1 differ on m32 (4.2, gate 3a)."""

import json
import sys

import numpy as np

sys.path.insert(0, r"C:\Users\gijsm\Worktrees\rang\fp-e1-chain\python")
from rang import core_ms
from rang.formats import flagversions

ms, tms, out = sys.argv[1:4]
name = next(v for v, _ in flagversions.versions(ms) if v.startswith("rang_calibrate_"))
a = flagversions.load(ms, name)[0]
with core_ms.open_table(tms) as t:
    b = t.getcol("FLAG")
    c = {
        n: t.getcol(n)
        for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER")
    }
d = (a != b).any(-1)
r, ch = np.nonzero(d)
rep = {
    "elements_differ": int((a != b).sum()),
    "cells_differ": int(d.sum()),
    "rang_only": int((a.any(-1) & ~b.any(-1)).sum()),
    "tricolour_only": int((~a.any(-1) & b.any(-1)).sum()),
    "corr_partial": int(((a != b).any(-1) & ~(a != b).all(-1)).sum()),
    "scans": {
        int(s): int((c["SCAN_NUMBER"][r] == s).sum())
        for s in np.unique(c["SCAN_NUMBER"][r])
    },
    "baselines": len(
        {(int(x), int(y)) for x, y in zip(c["ANTENNA1"][r], c["ANTENNA2"][r])}
    ),
    "channels": np.unique(ch).tolist(),
    "times_in_scan": None,
}
# position of each differing row's time within its scan
pos = []
for s in np.unique(c["SCAN_NUMBER"][r]):
    ts = np.unique(c["TIME"][c["SCAN_NUMBER"] == s])
    pos += [int(np.searchsorted(ts, t)) for t in c["TIME"][r][c["SCAN_NUMBER"][r] == s]]
rep["times_in_scan"] = np.bincount(pos).tolist()
print(json.dumps(rep, indent=1))
with open(out, "w") as fh:
    json.dump(rep, fh, indent=1)
