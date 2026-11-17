# ruff: noqa
# Step 2 (python-casacore): read the column casacure added.
import casacore.tables as pt

t = pt.table("ac.tab", ack=False)
print("iscelldefined", t.iscelldefined("CORRECTED_DATA", 0))
print("getcell shape", t.getcell("CORRECTED_DATA", 0).shape)
try:
    t.getcol("CORRECTED_DATA")
except Exception as err:
    print("getcol raises:", err)
