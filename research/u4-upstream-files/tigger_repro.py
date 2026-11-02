# ruff: noqa
"""Minimal reproduction for the tigger-lsm issues (U4). Usage: python -I tigger_repro.py <workdir>"""

import os
import re
import sys
from importlib.metadata import version

os.chdir(sys.argv[1])
import numpy
from Tigger.Models import ModelClasses, SkyModel
from Tigger.Models.Formats import ASCII, BBS, ModelHTML

print(
    "astro-tigger-lsm",
    version("astro-tigger-lsm"),
    "numpy",
    numpy.__version__,
    "python",
    sys.version.split()[0],
)


def model():
    # a Gaussian with a three-term spectrum, 20 x 10 arcsec at PA 30 deg, and a one-term point source
    a = SkyModel.Source(
        "A",
        ModelClasses.Position(0.1, -0.5),
        ModelClasses.Polarization(2.0, 0, 0, 0),
        shape=ModelClasses.Gaussian(
            float(numpy.deg2rad(20 / 3600)),
            float(numpy.deg2rad(10 / 3600)),
            float(numpy.deg2rad(30)),
        ),
        spectrum=ModelClasses.SpectralIndex([-0.7, -0.1, 0.02], 1.4e9),
    )
    b = SkyModel.Source(
        "B",
        ModelClasses.Position(0.1, -0.5001),
        ModelClasses.Polarization(1.0, 0, 0, 0),
        spectrum=ModelClasses.SpectralIndex(-0.7, 1.4e9),
    )
    return SkyModel.SkyModel(a, b)


def desc(model):
    return [
        (
            s.name,
            getattr(s.spectrum, "spi", None),
            getattr(s.shape, "ex", None),
            getattr(s.shape, "pa", None),
        )
        for s in model.sources
    ]


ASCII.save(model(), "m.txt")
print("--- ASCII file")
print(open("m.txt").read())
try:
    print("ASCII.load:", desc(ASCII.load("m.txt")))
except Exception as e:
    print("ASCII.load raised:", type(e).__name__, e)

BBS.save(model(), "m.catalog")
print("--- BBS file")
print(open("m.catalog").read())
try:
    print("BBS.load:", desc(BBS.load("m.catalog")))
except Exception as e:
    print("BBS.load raised:", type(e).__name__, e)

# eval on mdlval: a harmless arithmetic expression in place of a literal number
ModelHTML.save(model(), "m.lsm.html")
txt = open("m.lsm.html").read()
print("--- HTML excerpt")
print(txt[:1000])
print("---")
new = re.sub(r"(mdlval=)(['\"]?)2\.0(['\"]?)", r"\g<1>'1+1+1'", txt, count=1)
assert new != txt
open("expr.lsm.html", "w").write(new)
print(
    "A flux I after loading mdlval='1+1+1':",
    [s.flux.I for s in ModelHTML.load("expr.lsm.html").sources if s.name == "A"],
)
