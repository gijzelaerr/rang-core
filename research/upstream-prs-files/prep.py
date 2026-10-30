"""Extract scan 9 of outer_scans.zip and add MODEL_DATA = 1 on the parallel hands.

usage: python prep.py <zip> <out_dir>
"""
import os
import shutil
import sys
import zipfile

import numpy as np
from casacore.tables import makearrcoldesc, maketabdesc, table

zpath, out = sys.argv[1], sys.argv[2]
member = "outer_scans/1672727931_sdp_l0_scan_9.ms/"
os.makedirs(out, exist_ok=True)
with zipfile.ZipFile(zpath) as z:
    for n in z.namelist():
        if n.startswith(member):
            z.extract(n, out)
ms = os.path.join(out, "scan9.ms")
shutil.move(os.path.join(out, member), ms)
shutil.rmtree(os.path.join(out, "outer_scans"))

t = table(ms, readonly=False, ack=False)
data = t.getcol("DATA")
desc = t.getcoldesc("DATA")
desc["name"] = "MODEL_DATA"
t.addcols(maketabdesc(makearrcoldesc("MODEL_DATA", 0j, valuetype="complex", ndim=2)))
model = np.zeros_like(data)
model[..., 0] = 1.0
model[..., 3] = 1.0
t.putcol("MODEL_DATA", model)
a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
flag = t.getcol("FLAG")
print("rows", t.nrows(), "shape", data.shape, "autos", int((a1 == a2).sum()),
      "times", len(np.unique(t.getcol("TIME"))), "flag fraction %.3f" % flag.mean(),
      "weight cols", [c for c in t.colnames() if "WEIGHT" in c])
t.close()
