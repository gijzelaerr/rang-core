import json
import sys

import numpy as np

sys.path.insert(0, r"C:\Users\gijsm\Worktrees\rang\fp-e1-chain\python")
from rang import core_ms

m32 = r"D:\rang\outputs\e1-20261109-02-data\a1-full-m32.ms"
full = r"D:\rang\outputs\fp-a1-20261106-simtruth\full\a1-full.ms"
nbl = 2016
out = {}
with core_ms.open_table(m32) as a, core_ms.open_table(full) as b:
    ta = a.getcol("TIME")
    for gi in (0, 121, 1334):
        tb = b.getcol("TIME", gi * nbl, nbl)
        ra = np.flatnonzero(ta == tb[0])
        da = a.getcol("DATA", int(ra[0]), nbl).astype(np.complex128)
        db = b.getcol("DATA", gi * nbl, nbl).astype(np.complex128)
        d = np.abs(da - db)
        ulp = np.spacing(
            np.maximum(np.abs(db.real), np.abs(db.imag)).astype(np.float32)
        ).astype(float)
        out[gi] = {
            "cells_differ": int((d > 0).sum()),
            "cells": int(d.size),
            "max_abs": float(d.max()),
            "max_in_float32_ulps": float((d / ulp).max()),
            "max_rel_to_cell": float((d / np.maximum(np.abs(db), 1e-30)).max()),
        }
print(json.dumps(out, indent=1))
with open(r"D:\rang\outputs\e1-20261109-02-data\verify-m32-posthoc.json", "w") as fh:
    json.dump(out, fh, indent=1)
