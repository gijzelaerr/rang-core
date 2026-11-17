"""9.19: sha256 of FLAG + FLAG_ROW and of CORRECTED_DATA of R/casa/e2b.ms,
read natively on Windows with rang's reader (9p reads from WSL returned
ENOMEM). Taken before step 1 and after step 7; equal hashes mean the
restore is exact.

    python b2_hash.py OUT_JSON
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
MS = "D:/rang/outputs/e2-20261111-20-e2b/casa/e2b.ms"
B = 1000


def main(out):
    from rang import core_ms

    t0 = time.time()
    hf, hc = hashlib.sha256(), hashlib.sha256()
    with core_ms.open_table(MS) as t:
        cols = sorted(t.columns)
        n = t.nrows
        for r0 in range(0, n, B):
            k = min(B, n - r0)
            hf.update(np.ascontiguousarray(t.getcol("FLAG", r0, k)).tobytes())
            hf.update(np.ascontiguousarray(t.getcol("FLAG_ROW", r0, k)).tobytes())
            hc.update(np.ascontiguousarray(t.getcol("CORRECTED_DATA", r0, k)).tobytes())
    rec = {"columns": cols, "rows": n, "flag_sha256": hf.hexdigest(),
           "corrected_sha256": hc.hexdigest(), "secs": time.time() - t0}  # fmt: skip
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
