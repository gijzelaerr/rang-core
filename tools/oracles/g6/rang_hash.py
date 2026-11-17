# SPDX-License-Identifier: GPL-3.0-or-later
"""SHA-256 of a column read with rang's own reader (G6 criterion 6), in the
byte order compare.py hashes python-casacore's reads.

    python rang_hash.py MS COLUMN"""

import hashlib
import json
import sys

import numpy as np

from rang import core_ms


def main():
    ms, name = sys.argv[1], sys.argv[2]
    h = hashlib.sha256()
    with core_ms.open_table(ms) as t:
        step = max(1, (1 << 24) // int(np.prod(t.getcol("DATA", 0, 1).shape[1:])))
        for start in range(0, t.nrows, step):
            n = min(step, t.nrows - start)
            h.update(np.ascontiguousarray(t.getcol(name, start, n)).tobytes())
    print(json.dumps({"ms": ms, "column": name, "sha256_rang": h.hexdigest()}))


if __name__ == "__main__":
    main()
