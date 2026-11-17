"""Section 11: a fresh copy of src.ms (flag-stage FLAG) carrying S1 seed 1's simulated DATA."""

import shutil
from pathlib import Path

import numpy as np
from rang import core_ms, core_ms_write

O = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
dst = O / "sim-s1-20261171-uf.ms"
shutil.copytree(O / "src.ms", dst)
with core_ms.open_table(O / "sim-s1-20261171-u.ms") as t:
    data = np.asarray(t.getcol("DATA"))
with core_ms_write.open_table(dst, readonly=False) as t:
    t.putcol("DATA", data)
print("ok", data.shape)
