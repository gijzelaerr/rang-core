# ruff: noqa
"""Minimal reproduction for crystalball import_from_wsclean (U4). Usage: python -I crystalball_repro.py <workdir>"""

import os
import sys
from importlib.metadata import version

os.chdir(sys.argv[1])
import numpy

print(
    "crystalball",
    version("crystalball"),
    "codex-africanus",
    version("codex-africanus"),
    "numpy",
    numpy.__version__,
    "python",
    sys.version.split()[0],
)
HEAD = "Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI, ReferenceFrequency='1400000000.0', MajorAxis, MinorAxis, Orientation\n"
open("m.txt", "w").write(
    HEAD
    + "s0c0,POINT,00:00:00.0,-30.00.00.0,1.0,[-0.7,-0.1],false,1400000000.0,,,\n"
    + "s0c1,POINT,00:00:10.0,-30.00.00.0,0.5,[-0.7],false,1400000000.0,,,\n"
)
open("n.txt", "w").write(
    HEAD
    + "s0c0,POINT,00:00:00.0,-30.00.00.0,1.0,[-0.7,-0.1],false,1400000000.0,,,\n"
    + "s0c1,POINT,00:00:10.0,-30.00.00.0,0.5,[-0.7,0.0],false,1400000000.0,,,\n"
)
from crystalball.wsclean import import_from_wsclean

for name in ["m.txt", "n.txt"]:
    try:
        print(name, "loaded:", import_from_wsclean(name))
    except Exception as e:
        print(name, "raised:", type(e).__name__, e)
