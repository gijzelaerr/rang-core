# ruff: noqa
# Step 1 (casacure): add a variable-shape array column and write nothing to it.
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc, makescacoldesc

t = table("ac.tab", maketabdesc([makescacoldesc("TIME", 0.0)]), nrow=3, ack=False)
t.putcol("TIME", np.arange(3.0))
t.addcols(makearrcoldesc("CORRECTED_DATA", 0j, ndim=2, valuetype="complex"))
t.close()
