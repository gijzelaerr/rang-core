"""Export field-0 FLAG of two flag versions at the D3 copy's source rows (packed)."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from rang import core_ms

RUN = Path(r"D:\rang\outputs\e2a-20261115")
base = json.loads(
    Path(r"D:\rang\outputs\e2a-3b-diag-20261117\d3\fcal-base.json").read_text()
)
rows = np.asarray(base["source_rows"], np.int64)
out = Path(sys.argv[1])
# contiguous runs
brk = np.flatnonzero(np.diff(rows) != 1) + 1
runs = np.split(rows, brk)
print("runs", [(int(r[0]), len(r)) for r in runs])
for name, ver in (
    ("stage", "flags.rang_calibrate_20261115T132707Z"),
    ("after", "flags.rang_apply_20261115T144017Z"),
):
    parts, prow = [], []
    with core_ms.open_table(RUN / "e2a.ms.flagversions" / ver) as t:
        for r in runs:
            for s in range(0, len(r), 20000):
                k = min(20000, len(r) - s)
                parts.append(np.asarray(t.getcol("FLAG", int(r[s]), k), bool))
                prow.append(np.asarray(t.getcol("FLAG_ROW", int(r[s]), k), bool))
    f = np.ascontiguousarray(np.concatenate(parts))
    fr = np.concatenate(prow)
    with core_ms.open_table(RUN / "e2a.ms") as t:
        tm = np.concatenate(
            [np.asarray(t.getcol("TIME", int(r[0]), len(r))) for r in runs]
        )
        a1 = np.concatenate(
            [np.asarray(t.getcol("ANTENNA1", int(r[0]), len(r))) for r in runs]
        )
        a2 = np.concatenate(
            [np.asarray(t.getcol("ANTENNA2", int(r[0]), len(r))) for r in runs]
        )
    h = hashlib.sha256(f.tobytes()).hexdigest()
    np.savez_compressed(
        out / f"f0-{name}-flags.npz",
        shape=np.array(f.shape),
        flag=np.packbits(f.ravel()),
        FLAG_ROW=fr,
        TIME=tm,
        ANTENNA1=a1,
        ANTENNA2=a2,
    )
    print(name, f.shape, int(f.sum()), h)
