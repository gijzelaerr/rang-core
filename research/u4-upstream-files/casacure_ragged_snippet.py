# ruff: noqa
"""The snippet of casacure issue #25, for either backend. Usage: python -I casacure_ragged_snippet.py casacure|casacore <workdir>"""

import importlib
import os
import sys

import numpy as np

m = importlib.import_module(sys.argv[1] + ".tables")
table, maketabdesc, makearrcoldesc = m.table, m.maketabdesc, m.makearrcoldesc
os.chdir(sys.argv[2])
t = table(
    sys.argv[1] + "-ragged.tab",
    maketabdesc([makearrcoldesc("V", 0.0, ndim=1)]),
    nrow=3,
    ack=False,
)
for r in range(3):
    t.putcell("V", r, np.arange(1.0, r + 2.0))
t.close()
try:
    print(
        sys.argv[1],
        repr(table(sys.argv[1] + "-ragged.tab", ack=False).getcol("V")).replace(
            "\n", " "
        ),
    )
except Exception as e:
    print(sys.argv[1], "raises", type(e).__name__, e)
