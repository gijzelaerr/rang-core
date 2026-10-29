"""Check a LUNO QuartiCal solve against the support extraction (host stage).

Reports, per gain bin, whether QuartiCal flagged the gains, how the unflagged-gain
pattern maps onto bins with TRAIN data, and the worst baseline closure
|G_p G_q^H - I| (identity up to a common unitary is expected for DATA = MODEL).
"""

import json
import pathlib
import sys

import numpy as np

extract, solve = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
gains = np.load(solve / "gains.npy")
flags = np.load(solve / "gain_flags.npy") != 0
time = np.load(extract / "group1" / "time.npy")
flag = np.load(extract / "group1" / "flag.npy")
weight = np.load(extract / "group1" / "weight.npy")
model = np.load(extract / "group1" / "model.npy")
a1, a2 = (
    np.load(extract / "group1" / "antenna1.npy"),
    np.load(extract / "group1" / "antenna2.npy"),
)
integration = np.searchsorted(np.unique(time), time)
train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
nt, nf = gains.shape[:2]
support = np.zeros((nt, nf, 4), dtype=bool)
rows, channels = np.nonzero(train)
for r, c in zip(rows, channels):
    support[integration[r] // 2, c // 32, [a1[r], a2[r]]] = True
binned = support.any(-1)
closure = 0.0
for t, f in zip(*np.nonzero(binned)):
    active = np.flatnonzero(support[t, f])
    for i, p in enumerate(active):
        for q in active[i + 1 :]:
            if not (flags[t, f, p] or flags[t, f, q]):
                product = gains[t, f, p] @ gains[t, f, q].conj().T
                closure = max(closure, float(np.abs(product - np.eye(2)).max()))
print(
    json.dumps(
        {
            "gain_grid": [nt, nf],
            "bins_with_train": int(binned.sum()),
            "supported_station_bins_flagged": int((support & flags).sum()),
            "unsupported_station_bins_unflagged": int((~support & ~flags).sum()),
            "max_baseline_closure_on_unflagged": closure,
        }
    )
)
