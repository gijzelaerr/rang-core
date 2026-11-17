"""Counts of cells whose FLAG differs between correlations, per packed export (research/e2a-3b-k.md step 5)."""

import json
import sys

import numpy as np

out = {}
for f in sys.argv[1:]:
    z = np.load(f)
    sh = tuple(int(x) for x in z["shape"])
    fl = np.unpackbits(z["flag"])[: np.prod(sh)].reshape(sh).astype(bool)
    cross = z["ANTENNA1"] != z["ANTENNA2"]
    fl = fl[cross]
    out[f.split("\\")[-1]] = {
        "cells": int(fl[..., 0].size),
        "any": int(fl.any(-1).sum()),
        "all": int(fl.all(-1).sum()),
        "parallel_differ": int((fl[..., 0] != fl[..., 3]).sum()),
        "cross_only_on_unflagged_parallel": int(
            ((fl[..., 1] | fl[..., 2]) & ~fl[..., 0] & ~fl[..., 3]).sum()
        ),
    }
print(json.dumps(out, indent=1))
