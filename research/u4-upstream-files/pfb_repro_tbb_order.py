# ruff: noqa
"""kclean's order: numba.set_num_threads before set_envs. Usage: python -I pfb_repro_tbb_order.py kclean|swapped"""

import sys
from importlib.metadata import version

for p in ["pfb-imaging", "numba", "tbb"]:
    print(p, version(p))
from pfb_imaging import (
    set_envs,
)  # as the CLI: pfb_imaging sets NUMBA_THREADING_LAYER before numba is imported

from numba import set_num_threads

try:
    if sys.argv[1] == "kclean":
        set_num_threads(2)
        set_envs(2, 2)
    else:
        set_envs(2, 2)
        set_num_threads(2)
    print(sys.argv[1], "order: OK")
except Exception as e:
    print(
        sys.argv[1], "order raised:", type(e).__name__, " ".join(str(e).split())[:200]
    )
