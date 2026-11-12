# ruff: noqa
import numpy as np
from casacure.tables import (
    table,
    maketabdesc,
    makearrcoldesc,
    makescacoldesc,
)  # or casacore.tables

d = maketabdesc(
    [
        makescacoldesc("D", 0.0),
        makescacoldesc("B", False),
        makearrcoldesc("A", 0.0, ndim=1),
        makearrcoldesc("FLAG_CATEGORY", False, ndim=3),
    ]
)
# 1. a never-written 3-D column
t = table("u.tab", d, nrow=3, ack=False)
t.putcol("D", np.arange(3.0))
t.close()
t = table("u.tab", ack=False)
try:
    v = t.getcol("FLAG_CATEGORY")
    print("getcol FLAG_CATEGORY:", v.shape, v.dtype)
except Exception as err:
    print("getcol FLAG_CATEGORY raises:", err)
t.close()
# 2. a 0-row table
table("z.tab", d, nrow=0, ack=False).close()
t = table("z.tab", ack=False)
print(
    "0 rows:",
    {c: np.asarray(t.getcol(c)).dtype.str for c in ("D", "B", "A", "FLAG_CATEGORY")},
)
t.close()
