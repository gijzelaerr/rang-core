# ruff: noqa
"""Tigger ASCII.save with NumPy scalar shape values. Usage: python -I tigger_numpy_scalars.py <workdir>"""

import os
import sys

os.chdir(sys.argv[1])
import numpy
from Tigger.Models import ModelClasses, SkyModel
from Tigger.Models.Formats import ASCII

print("numpy", numpy.__version__)
src = SkyModel.Source(
    "A",
    ModelClasses.Position(0.1, -0.5),
    ModelClasses.Polarization(2.0, 0, 0, 0),
    shape=ModelClasses.Gaussian(
        numpy.deg2rad(20 / 3600), numpy.deg2rad(10 / 3600), numpy.deg2rad(30)
    ),
    spectrum=ModelClasses.SpectralIndex(-0.7, 1.4e9),
)
ASCII.save(SkyModel.SkyModel(src), "np.txt")
print(open("np.txt").read())
print("loaded:", [s.name for s in ASCII.load("np.txt").sources])
try:
    ASCII.load("np.txt", verbose=True)
except Exception as e:
    print("verbose load raises:", type(e).__name__, e)
