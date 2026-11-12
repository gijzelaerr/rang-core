import sys
import time

import dask
from dask.diagnostics import ProgressBar

DT = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
print(
    "python",
    sys.version.split()[0],
    "dask",
    dask.__version__,
    "isatty",
    sys.stdout.isatty(),
    flush=True,
)
t0 = time.perf_counter()
with ProgressBar(minimum=1, dt=DT):
    dask.delayed(time.sleep)(1.0).compute()
print(f"\nwall {time.perf_counter() - t0:.2f} s for a 1.0 s task, dt={DT}", flush=True)
