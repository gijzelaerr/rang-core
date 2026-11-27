# SPDX-License-Identifier: MIT
import math
import sys

import numpy as np
from rang import calmodels, core
from rang.formats import sky

lsm = (
    "/home/gijs/rang-data/uhf/reference/hhhy-4r55/fitted.PKS1934.UBand.wsclean.cat.txt"
)
args = sky.components(
    calmodels.SkyModel(lsm).sources(), (math.radians(294.85), math.radians(-63.71))
)
nu = 544e6 + 132812.5 * np.arange(4096)
uvw = np.random.default_rng(1).normal(0, 2000, (40, 3))
np.save(sys.argv[1], core.predict_components(uvw, nu, **args))
