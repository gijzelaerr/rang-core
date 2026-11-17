# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 12: an arm's six tables against
e2a-3b-k's archived rang U tables on S0f, cell for cell (bitwise).

    python cf_same.py CASE ARM
"""

import json
import sys

import cf_score as S
import numpy as np


def main(case, name):
    A = S.O / case / f"arm-{name}.ms.rang-run" / "calibrate"
    U = S.K / "sim-s0f-u.ms.rang-run" / "calibrate"
    out = {}
    for n in ("K0", "G0", "B0", "K1", "G1", "B1"):
        a, b = S.tab(A / n), S.tab(U / n)
        out[n] = {
            "params_bitwise": bool(np.array_equal(a.params, b.params)),
            "flags_equal": bool(np.array_equal(a.flags, b.flags)),
            "times_equal": bool(np.array_equal(a.column("TIME"), b.column("TIME"))),
        }
    out["all_equal"] = all(all(v.values()) for v in out.values())
    S.write(S.O / f"score-same-{case}-{name}.json", out)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
