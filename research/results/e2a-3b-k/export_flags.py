"""Windows side of research/e2a-3b-k.md: the D1 subset's FLAG versions (flag stage, R0 and T-T after A0), packed, from D:."""

import hashlib
import sys
from pathlib import Path

import numpy as np
from rang import core_ms

D = Path(r"D:\rang\outputs\e2a-3b-diag-20261117\d1")
out = Path(sys.argv[1])
for name in ("src", "rang-r0", "rang-tt"):
    with core_ms.open_table(D / f"{name}.ms") as t:
        c = {
            k: np.asarray(t.getcol(k))
            for k in ("TIME", "ANTENNA1", "ANTENNA2", "FLAG_ROW")
        }
        f = np.ascontiguousarray(np.asarray(t.getcol("FLAG"), bool))
    h = hashlib.sha256(f.tobytes()).hexdigest()
    np.savez_compressed(
        out / f"{name}-flags.npz",
        shape=np.array(f.shape),
        flag=np.packbits(f.ravel()),
        **c,
    )
    print(name, f.shape, int(f.sum()), h)
