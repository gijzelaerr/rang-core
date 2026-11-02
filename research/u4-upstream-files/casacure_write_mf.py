# ruff: noqa
"""Write a MultiFile table (CASARCFILES names an aipsrc with table.storage.option: multifile)."""

import os
import sys

os.chdir(sys.argv[1])
import casacore.tables as pt

d = pt.maketabdesc([pt.makescacoldesc("I", 0)])
t = pt.table("mf.tab", d, nrow=2, ack=False)
t.putcol("I", [5, 6])
t.close()
t = pt.table("mf.tab", ack=False)
print("casacore mf", t.getcol("I"))
t.close()
print(sorted(os.listdir("mf.tab")))
