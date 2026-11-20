import json, sys
from pathlib import Path
import numpy as np

L = Path(sys.argv[1])
tot_cells = tot_diff = tot_r_only = 0
worst = []
for d in sorted((L / "rang").glob("*/scan*")):
    t = L / "tricolour" / d.relative_to(L / "rang")
    info = json.loads((d / "label.json").read_text())
    n = info["chan"] * info["corr"]
    a = np.load(d / "flag.npy", mmap_mode="r")
    b = np.load(t / "flag.npy", mmap_mode="r")
    diff = r_only = 0
    for r0 in range(0, a.shape[0], 20000):
        x = np.unpackbits(a[r0 : r0 + 20000], axis=1)[:, :n].astype(bool)
        y = np.unpackbits(b[r0 : r0 + 20000], axis=1)[:, :n].astype(bool)
        diff += int((x ^ y).sum())
        r_only += int((x & ~y).sum())
    cells = a.shape[0] * n
    tot_cells += cells
    tot_diff += diff
    tot_r_only += r_only
    worst.append((diff / cells, str(d.relative_to(L / "rang"))))
worst.sort(reverse=True)
print(
    json.dumps(
        {
            "scans": len(worst),
            "cells": tot_cells,
            "differ": tot_diff,
            "fraction": tot_diff / tot_cells,
            "rang_only": tot_r_only,
            "worst5": worst[:5],
        },
        indent=1,
    )
)
