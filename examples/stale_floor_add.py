"""Add a point source to DATA of a Measurement Set copy: JY on XX and YY, OFFSET pixels of SCALE arcsec in l.

Usage: stale_floor_add.py MS JY [OFFSET_PIXELS SCALE_ARCSEC]
"""

import sys

import numpy as np
from casacure import tables

path, jy = sys.argv[1], float(sys.argv[2])
offset = (
    float(sys.argv[3]) * float(sys.argv[4]) * np.pi / (180 * 3600)
    if len(sys.argv) > 3
    else 0.0
)
freq = tables.table(path + "/SPECTRAL_WINDOW", ack=False).getcol("CHAN_FREQ")[0]
t = tables.table(path, readonly=False, ack=False)
step = 200000
n_minus_1 = np.sqrt(1 - offset**2) - 1
for start in range(0, t.nrows(), step):
    n = min(step, t.nrows() - start)
    d = t.getcol("DATA", start, n)
    uvw = t.getcol("UVW", start, n)
    phase = uvw[:, 0, None] * offset + uvw[:, 2, None] * n_minus_1
    v = jy * np.exp(-2j * np.pi * phase * freq[None, :] / 299792458.0)
    d[:, :, 0] += v
    d[:, :, -1] += v
    t.putcol("DATA", d, start, n)
t.close()
t = tables.table(path, ack=False)
d = t.getcol("DATA", t.nrows() - 1, 1)
print("last row XX, YY after adding:", d[0, 0, 0], d[0, 0, -1])
t.close()
print("added", jy, "Jy at", offset, "rad", flush=True)
