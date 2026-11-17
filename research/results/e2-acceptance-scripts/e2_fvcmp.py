"""Compare the frozen and amended E2-B arms' flag versions element-wise (read only;
research/e2-acceptance.md 7.1). python e2_fvcmp.py MS OUT.json"""

import json
import sys

import numpy as np
from rang import core_ms
from rang.formats import flagversions

ms = sys.argv[1]
pairs = [
    ("rang_flag_20261112T005356Z", "rang_flag_20261112T165116Z"),
    ("rang_calibrate_20261112T010110Z", "rang_calibrate_20261112T165819Z"),
    ("rang_apply_20261112T013707Z", "rang_apply_20261112T173358Z"),
]
out = {}
with core_ms.open_table(ms) as t:
    n = t.nrows
for a_name, b_name in pairs:
    acc = {
        "elements_differ": 0,
        "frozen_only": 0,
        "amended_only": 0,
        "frozen_true": 0,
        "amended_true": 0,
    }
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        a = np.asarray(flagversions.load(ms, a_name, r0, k)[0], bool)
        b = np.asarray(flagversions.load(ms, b_name, r0, k)[0], bool)
        acc["elements_differ"] += int((a != b).sum())
        acc["frozen_only"] += int((a & ~b).sum())
        acc["amended_only"] += int((b & ~a).sum())
        acc["frozen_true"] += int(a.sum())
        acc["amended_true"] += int(b.sum())
    out[f"{a_name} vs {b_name}"] = acc
    print(a_name, b_name, acc, flush=True)
with open(sys.argv[2], "w") as fh:
    json.dump(out, fh, indent=1)
