# SPDX-License-Identifier: MIT
"""research/calchain-floor.md section 3: S0f' (stepped truth, k_sim's own
`make`) and S0c (K_T, G_T of scan 9 on every scan), noise-free, B_T = 1.

    python cf_sim.py stepped|const

Each case lives in its own directory under O with links to e2a-3b-k's
`src.ms` and `rang-u.ms` (read only; `make` copies src.ms). k_sim's
functions are imported, not copied.
"""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2a-3b-k"))

import k_sim

K = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
O = Path.home() / "rang-data" / "outputs" / "calchain-floor-20261117"


def main(case):
    d = O / case
    d.mkdir(parents=True, exist_ok=True)
    for n in ("src.ms", "rang-u.ms"):
        if not (d / n).exists():
            (d / n).symlink_to(K / n)
    k_sim.O = d  # TT (T-T's tables) stays e2a-3b-k's
    if case == "const":
        orig = k_sim._per_dump

        def per_dump(tab, dump_t, dump_scan, kind, mode):
            out = orig(tab, dump_t, dump_scan, kind, mode)
            first = dump_scan == np.unique(dump_scan)[0]
            out[:] = out[np.flatnonzero(first)[0]][None]
            return out

        k_sim._per_dump = per_dump
    elif case != "stepped":
        raise SystemExit(__doc__)
    return k_sim.make("s1f", "none")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
