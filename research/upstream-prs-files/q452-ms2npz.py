"""Dump scan 9 arrays for rang's port. usage: python ms2npz.py <ms> <out.npz> <unit|native>"""

import sys

import numpy as np
from casacore.tables import table

ms, out, arm = sys.argv[1:4]
t = table(ms, ack=False)
time = t.getcol("TIME")
utime, tidx = np.unique(time, return_inverse=True)
data = t.getcol("DATA")
w = t.getcol("WEIGHT_SPECTRUM") if arm != "unit" else np.ones(data.shape, np.float32)
np.savez(
    out,
    data=data,
    model=t.getcol("MODEL_DATA"),
    weights=w.astype(np.float32),
    flag=t.getcol("FLAG"),
    flag_row=t.getcol("FLAG_ROW"),
    a1=t.getcol("ANTENNA1"),
    a2=t.getcol("ANTENNA2"),
    tidx=tidx,
)
t.close()
print(out, data.shape, len(utime), "times")
