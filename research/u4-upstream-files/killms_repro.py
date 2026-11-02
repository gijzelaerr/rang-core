# ruff: noqa
"""killMS 3.3.0 MergeSols: pickle of options in the cwd and allow_pickle on inputs (U4).
DDFacet is only used for a logger in this module, so it is stubbed. Harmless marker only.
Usage: python -I killms_repro.py <killMS checkout> <workdir>"""

import importlib.util
import logging
import os
import pickle
import sys
import types

src, work = sys.argv[1], sys.argv[2]
os.chdir(work)
d = types.ModuleType("DDFacet")
o = types.ModuleType("DDFacet.Other")
l = types.ModuleType("DDFacet.Other.logger")
l.getLogger = logging.getLogger
o.logger = l
d.Other = o
sys.modules.update({"DDFacet": d, "DDFacet.Other": o, "DDFacet.Other.logger": l})
import numpy as np

spec = importlib.util.spec_from_file_location(
    "MergeSols", os.path.join(src, "killMS", "MergeSols.py")
)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
print("SaveName", M.SaveName, "numpy", np.__version__)


class Marker:
    def __reduce__(self):
        return (print, ("marker: callable ran during unpickling",))


# 1. main() without options reads whatever is in the working directory
pickle.dump(Marker(), open(M.SaveName, "wb"))
try:
    M.main()
except Exception as e:
    print("main() after unpickling:", type(e).__name__, e)
# 2. solutions input
np.savez("sols.npz", Sols=np.array([Marker()], dtype=object))
try:
    M.ClassMergeSols(["sols.npz"])
except Exception as e:
    print("ClassMergeSols after np.load:", type(e).__name__, e)
