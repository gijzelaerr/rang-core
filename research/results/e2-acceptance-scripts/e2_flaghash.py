"""Gate 2a's reference (research/e2-acceptance.md 6.2, 6.5): SHA-256 of an MS's
FLAG (as bool bytes, row-major (row, chan, corr)) and FLAG_ROW, read in
blocks of rows, with the row count and shape.

    python e2_flaghash.py MS OUT.json
"""

import hashlib
import json
import sys
import time

import numpy as np
from rang import core_ms

BLOCK = 4000


def main(ms, out):
    t0 = time.perf_counter()
    hf, hr = hashlib.sha256(), hashlib.sha256()
    with core_ms.open_table(ms) as t:
        n = t.nrows
        shape = None
        for r0 in range(0, n, BLOCK):
            k = min(BLOCK, n - r0)
            f = np.ascontiguousarray(np.asarray(t.getcol("FLAG", r0, k), dtype=bool))
            shape = f.shape[1:]
            hf.update(f.tobytes())
            fr = np.ascontiguousarray(
                np.asarray(t.getcol("FLAG_ROW", r0, k), dtype=bool)
            )
            hr.update(fr.tobytes())
    result = {
        "ms": str(ms), "rows": int(n), "cell_shape": [int(x) for x in shape],
        "flag_sha256": hf.hexdigest(), "flag_row_sha256": hr.hexdigest(),
        "seconds": time.perf_counter() - t0,
    }  # fmt: skip
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
