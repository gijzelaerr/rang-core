"""Lost station-bins (2 dumps x 32 channels) that are station-specific: another station keeps samples.
usage: python specific.py <before.npy> <ms>"""
import json
import sys

import numpy as np
from casacore.tables import table

before = np.load(sys.argv[1])
t = table(sys.argv[2], ack=False)
after = t.getcol("FLAG")
a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
_, tidx = np.unique(t.getcol("TIME"), return_inverse=True)
t.close()
cross = a1 != a2
ti, fi, nchan = 2, 32, before.shape[1]
nt, nf, na = tidx.max() // ti + 1, nchan // fi, 4


def counts(flag):
    ok = ~flag.any(-1)
    c = np.zeros((nt, nf, na), np.int64)
    for r in np.nonzero(cross)[0]:
        b = ok[r].reshape(nf, fi).sum(-1)
        c[tidx[r] // ti, :, a1[r]] += b
        c[tidx[r] // ti, :, a2[r]] += b
    return c


cb, ca = counts(before), counts(after)
lost = (cb > 0) & (ca == 0)
others_usable = (ca > 0).sum(-1, keepdims=True) > 0
whole_bin = (ca == 0).all(-1)  # every station lost the bin: channel/time flags
chan_frac_new = (after.any(-1) & ~before.any(-1))[cross].mean(axis=0)
print(json.dumps({
    "lost": int(lost.sum()),
    "lost_station_specific": int((lost & others_usable).sum()),
    "lost_all_stations_in_bin": int((lost & whole_bin[..., None]).sum()),
    "channels_newly_flagged_on_all_cross_rows": int((chan_frac_new == 1).sum()),
}))
