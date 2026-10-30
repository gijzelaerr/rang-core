"""Per station x solution-interval bins: unflagged cross-correlation samples before and after flagging.

usage: python bins.py <before.npy> <ms> <time_interval> <freq_interval>   -> JSON on stdout
       python bins.py --save <ms> <out.npy>                                 (save the FLAG column)
       python bins.py --preflag <ms> <fraction>                             (flag extra whole channels)
"""
import json
import sys

import numpy as np
from casacore.tables import table

if sys.argv[1] == "--save":
    t = table(sys.argv[2], ack=False)
    np.save(sys.argv[3], t.getcol("FLAG"))
    sys.exit()

if sys.argv[1] == "--preflag":
    # Widen the native channel flags: flag whole channels next to already flagged
    # ranges (as a wider static mask would) until the target fraction is reached.
    t = table(sys.argv[2], readonly=False, ack=False)
    target = float(sys.argv[3])
    flag = t.getcol("FLAG")
    a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    cross = a1 != a2
    while flag[cross].mean() < target:
        chan_frac = flag[cross].mean(axis=(0, 2))
        flagged = chan_frac > 0.5
        grow = (np.roll(flagged, 1) | np.roll(flagged, -1)) & ~flagged
        if not grow.any():
            break
        flag[:, grow, :] = True
    t.putcol("FLAG", flag)
    print(json.dumps({"preflag_fraction_cross": float(flag[cross].mean())}))
    t.close()
    sys.exit()

before = np.load(sys.argv[1])
t = table(sys.argv[2], ack=False)
after = t.getcol("FLAG")
a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
_, tidx = np.unique(t.getcol("TIME"), return_inverse=True)
t.close()
ti, fi = int(sys.argv[3]), int(sys.argv[4])
cross = a1 != a2
nant = int(max(a1.max(), a2.max())) + 1
nt = tidx.max() // ti + 1
nchan = before.shape[1]
nf = (nchan + fi - 1) // fi


def counts(flag):
    ok = ~flag.any(axis=-1)  # a sample is usable when no correlation is flagged
    c = np.zeros((nt, nf, nant), np.int64)
    for r in np.nonzero(cross)[0]:
        per_bin = np.add.reduceat(ok[r].astype(np.int64), np.arange(0, nchan, fi))
        c[tidx[r] // ti, :, a1[r]] += per_bin
        c[tidx[r] // ti, :, a2[r]] += per_bin
    return c


cb, ca = counts(before), counts(after)
lost = (cb > 0) & (ca == 0)
lost_samples = cb[lost]
out = {
    "intervals": [int(ti), int(fi)],
    "cross_flag_fraction_before": float(before[cross].any(-1).mean()),
    "cross_flag_fraction_after": float(after[cross].any(-1).mean()),
    "new_flagged_cells": int((after.any(-1) & ~before.any(-1))[cross].sum()),
    "station_bins": int(cb.size),
    "station_bins_usable_before": int((cb > 0).sum()),
    "station_bins_usable_after": int((ca > 0).sum()),
    "station_bins_lost": int(lost.sum()),
    "lost_bins_unflagged_samples_before_median": float(np.median(lost_samples)) if lost.any() else None,
    "lost_bins_unflagged_samples_before_max": int(lost_samples.max()) if lost.any() else None,
    "lost_bins_by_station": [int(x) for x in lost.sum(axis=(0, 1))],
}
print(json.dumps(out, indent=1))
