# ruff: noqa
"""pfb-imaging set_envs then a numba parallel region. Usage: python -I pfb_repro_tbb.py"""

from importlib.metadata import version

for p in ["pfb-imaging", "numba", "tbb"]:
    print(p, version(p))
from pfb_imaging import set_envs

set_envs(2, 2)
import numba
import numpy as np


@numba.njit(parallel=True)
def f(x):
    s = 0.0
    for i in numba.prange(x.size):
        s += x[i]
    return s


try:
    print("sum", f(np.ones(1000)), "layer", numba.threading_layer())
except Exception as e:
    print("raised:", type(e).__name__, str(e)[:900])
