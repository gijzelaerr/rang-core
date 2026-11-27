# SPDX-License-Identifier: MIT
"""The model step's cost on this host: rang's `core.predict_components` (the call
calmodels.set_model makes for the DOI 1934-638 catalogue) on N random rows at D's
4,096 channels, single call, the frozen wheel. Run 2026-11-27 on nash (1 slot):
N = 20 took 18.89 s, 29.6 ns per row x channel x component.

    python bench_predict.py N
"""

import sys
import time

import numpy as np
from rang import calmodels, core
from rang.formats import sky

lsm = (
    "/home/gijs/rang-data/uhf/reference/hhhy-4r55/fitted.PKS1934.UBand.wsclean.cat.txt"
)
src = calmodels.SkyModel(lsm).sources()
import math

args = sky.components(src, (math.radians(294.85), math.radians(-63.71)))
nu = 544e6 + 132812.5 * np.arange(4096)
rng = np.random.default_rng(0)
uvw = rng.normal(0, 2000, (int(sys.argv[1]), 3))
t = time.perf_counter()
v = core.predict_components(uvw, nu, **args)
dt = time.perf_counter() - t
n = uvw.shape[0] * len(nu) * len(src) if hasattr(src, "__len__") else None
print(
    "rows",
    uvw.shape[0],
    "s",
    round(dt, 2),
    "per row s",
    dt / uvw.shape[0],
    "ns/elem",
    dt / (uvw.shape[0] * 4096 * 7779) * 1e9,
)
print(
    "projected fcal 304416 rows h",
    dt / uvw.shape[0] * 304416 / 3600,
    "+ 3C286 (models are 1 comp)",
)
