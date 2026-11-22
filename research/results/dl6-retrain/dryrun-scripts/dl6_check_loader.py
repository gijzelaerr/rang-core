# SPDX-License-Identifier: MIT
"""DL6 dry run, R2's loader check: dl6_load_ms.py's scan against rang's own
MS reader (`rang_core::ms_write::read_cells`), rows 0-99 and the last 100
kept rows of DATA, FLAG, ANTENNA1, ANTENNA2 and TIME, bit for bit.

    python dl6_check_loader.py SCAN.npz MS
"""

import json
import sys

import numpy as np
from rang import core_ms_write as w


def main():
    z = np.load(sys.argv[1])
    ms = sys.argv[2]
    keep = z["keep"]
    out = {"scan": sys.argv[1], "equal": {}}
    for lo in (0, len(keep) - 100):
        rows = keep[lo : lo + 100]
        r0, n = int(rows[0]), int(rows[-1] - rows[0] + 1)
        idx = rows - r0
        for col, key, dt in (
            ("DATA", "data", np.complex64),
            ("FLAG", "input_flags", bool),
            ("ANTENNA1", "antenna1", np.int32),
            ("ANTENNA2", "antenna2", np.int32),
            ("TIME", "times", np.float64),
        ):
            cells = w.read_cells(ms, col, r0, n)
            ref = np.asarray([np.asarray(c, dt) for c in cells])[idx]
            mine = z[key][lo : lo + 100]
            out["equal"][f"{col}@{lo}"] = bool(
                ref.shape == mine.shape and ref.tobytes() == mine.astype(dt).tobytes()
            )
    out["pass"] = all(out["equal"].values())
    print(json.dumps(out))
    if not out["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
