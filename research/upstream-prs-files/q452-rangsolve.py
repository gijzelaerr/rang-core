"""rang's port of the 0.2.7 complex solve on scan 9 arrays (2 x 32 intervals).

usage: RANG_SOLVE_OPTIONS=qp_weights=... python rangsolve.py <in.npz> <out.npz> <max_iter> <fraction>
Autocorrelations are excluded through FLAG_ROW (QuartiCal drops them).
"""

import os
import sys
import time

import numpy as np
from rangtoy import core

src, out, cap, frac = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
z = np.load(src)
a1, a2 = z["a1"], z["a2"]
nant = int(max(a1.max(), a2.max())) + 1
nchan = z["data"].shape[1]
flag_row = z["flag_row"] | (a1 == a2)
t0 = time.time()
sol = core.solve_complex(
    z["data"],
    z["weights"],
    z["flag"],
    flag_row,
    a1,
    a2,
    (z["tidx"] // 2).astype(np.uint32),
    (np.arange(nchan) // 32).astype(np.uint32),
    ntime_bins=int(z["tidx"].max()) // 2 + 1,
    nfreq_bins=nchan // 32,
    nant=nant,
    model=z["model"],
    max_iterations=cap,
    stop_criterion=1e-7,
    stop_fraction=frac,
)
wall = time.time() - t0
np.savez(out, gains=sol.gains, flags=sol.flags)
print(
    f"rang {os.environ.get('RANG_SOLVE_OPTIONS', '(unset)')} {os.path.basename(src)} cap {cap} frac {frac}: "
    f"iterations {sol.iterations}, converged fraction {sol.converged_fraction:.4f}, wall {wall:.1f} s"
)
