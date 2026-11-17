# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 7 (post hoc): the K1 intervals of an
arm, and per antenna the unflagged parallel-hand cells (> 150 m baselines)
in each interval under the FLAG the arm's pass 1 solved on (the arm's MS
after its run: A0's FLAG).

    python cf_k1cells.py CASE ARM ANT [ANT ...]
"""

import json
import sys

import cf_score as S
import numpy as np
from rang import core_ms


def main(case, name, *ants):
    d = S.O / case
    ms = d / f"arm-{name}.ms"
    rows = S.Rows(ms)
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    k1 = S.tab(A / "K1")
    t1 = np.unique(np.round(k1.column("TIME"), 3))
    fr = rows.field_rows
    with core_ms.open_table(ms) as t:
        tm = np.asarray(t.getcol("TIME"))[fr]
        a1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        a2 = np.asarray(t.getcol("ANTENNA2"))[fr]
        uvw = np.asarray(t.getcol("UVW"))[fr]
        f = np.asarray(t.getcol_rows("FLAG", fr))[..., (0, 3)]
        frw = np.asarray(t.getcol_rows("FLAG_ROW", fr))
    long_ = (np.hypot(uvw[:, 0], uvw[:, 1]) > 150) & (a1 != a2)
    ok = ~(f | frw[:, None, None]) & long_[:, None, None]
    iv = np.abs(tm[:, None] - t1[None, :]).argmin(1)
    out = {"k1_times_rel_s": (t1 - t1[0]).tolist(), "per_antenna": {}}
    for a in map(int, ants):
        sel = (a1 == a) | (a2 == a)
        per = {}
        for i in range(len(t1)):
            s = sel & (iv == i)
            per[i] = {
                "rows": int(s.sum()),
                "cells_X": int(ok[s, :, 0].sum()),
                "cells_Y": int(ok[s, :, 1].sum()),
                "channels_X": int(ok[s, :, 0].any(0).sum()),
                "baselines_X": int(ok[s, :, 0].any(1).sum()),
            }
        out["per_antenna"][a] = per
    S.write(S.O / f"score-k1cells-{case}-{name}.json", out)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
