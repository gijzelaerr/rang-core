# ruff: noqa
"""Write the casacure test tables with python-casacore. Usage: python -I casacure_write.py <workdir>"""

import os
import sys
from importlib.metadata import version

import numpy as np

os.chdir(sys.argv[1])
import casacore.tables as pt

print("python-casacore", version("python-casacore"))
# fixed-shape Direct string array, default StandardStMan
d = pt.maketabdesc(
    [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("SD", "", shape=[2], options=1, valuetype="string"),
    ]
)
t = pt.table("sd.tab", d, nrow=3, ack=False)
for r in range(3):
    t.putcell("SD", r, ["p%d" % r, "q" * (r + 1)])
t.close()
t = pt.table("sd.tab", ack=False)
print("casacore SD", t.getcol("SD"))
print("dminfo", {k: v["TYPE"] for k, v in t.getdminfo().items()})
t.close()
# indirect fixed shape string array: control
d = pt.maketabdesc(
    [pt.makearrcoldesc("SI", "", shape=[2], options=4, valuetype="string")]
)
t = pt.table("si.tab", d, nrow=3, ack=False)
for r in range(3):
    t.putcell("SI", r, ["p%d" % r, "q" * (r + 1)])
t.close()
# ragged variable-shape column
d = pt.maketabdesc([pt.makearrcoldesc("V", 0.0, ndim=1, valuetype="float")])
t = pt.table("ragged.tab", d, nrow=3, ack=False)
for r in range(3):
    t.putcell("V", r, np.arange(1.0, r + 2.0, dtype=np.float32))
t.close()
t = pt.table("ragged.tab", ack=False)
try:
    print("casacore getcol V", t.getcol("V"))
except Exception as e:
    print("casacore getcol V raises:", type(e).__name__, e)
print("casacore getvarcol V", t.getvarcol("V"))
print("casacore getvarcol V start=1", t.getvarcol("V", 1, 2))
t.close()
# MemoryStMan
d = pt.maketabdesc([pt.makescacoldesc("I", 0)])
dm = {"*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["I"]}}
t = pt.table("msm.tab", d, nrow=2, dminfo=dm, ack=False)
t.close()
print("wrote msm.tab")
