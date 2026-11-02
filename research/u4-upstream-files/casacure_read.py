# ruff: noqa
"""Read the tables with casacure. Usage: python -I casacure_read.py <workdir>"""

import os
import sys
from importlib.metadata import version

os.chdir(sys.argv[1])
import numpy as np

print("casacure", version("casacure"), "numpy", np.__version__)
from casacure.tables import table


def attempt(label, fn):
    try:
        print(label, "->", repr(fn()))
    except BaseException as e:
        print(label, "RAISES", type(e).__name__, e)


t = table("sd.tab")
attempt("SD getcol", lambda: t.getcol("SD"))
attempt("SD getcell 0", lambda: t.getcell("SD", 0))
attempt("dminfo", lambda: {k: v["TYPE"] for k, v in t.getdminfo().items()})
t.close()
t = table("si.tab")
attempt("SI (indirect) getcol", lambda: t.getcol("SI"))
t.close()
t = table("ragged.tab")
attempt("V getcol", lambda: t.getcol("V"))
attempt("V getvarcol", lambda: t.getvarcol("V"))
attempt("V getvarcol start=1", lambda: t.getvarcol("V", 1, 2))
for r in range(3):
    attempt("V getcell %d" % r, lambda: t.getcell("V", r))
t.close()
attempt("MemoryStMan open+read", lambda: table("msm.tab").getcol("I"))
attempt("MultiFile open+read", lambda: table("mf.tab").getcol("I"))
