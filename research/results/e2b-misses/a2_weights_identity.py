"""A2: the spec- and ones-weight cases' CASA solutions compared value by value
(research/e2b-misses.md 9.4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
import numpy as np
from rang.formats import caltable

O = Path(r"D:\rang\outputs\e2b-arms-20261114\a2")
for p in (("match-ones", "match-spec"), ("after-ones", "after-spec")):
    for t in ("K", "G", "B", "Gsec", "F"):
        a = caltable.read(O / p[0] / "tables" / t)
        b = caltable.read(O / p[1] / "tables" / t)
        ok = ~a.flags & ~b.flags
        print(
            p,
            t,
            "max|dpar|",
            float(np.abs(a.params - b.params)[ok].max()),
            "flags differ",
            int((a.flags != b.flags).sum()),
        )
