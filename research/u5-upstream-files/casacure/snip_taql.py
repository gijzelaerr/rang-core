# ruff: noqa
import numpy as np
from casacure.tables import (
    table,
    maketabdesc,
    makescacoldesc,
    taql,
)  # or casacore.tables

t = table(
    "tq.tab",
    maketabdesc([makescacoldesc("TIME", 0.0), makescacoldesc("ANT", 0)]),
    nrow=6,
    ack=False,
)
t.putcol("TIME", np.arange(6.0))
t.putcol("ANT", np.array([3, 1, 2, 3, 1, 2]))
t.flush()
for q in (
    "SELECT TIME FROM tq.tab WHERE TIME BETWEEN 1 AND 3",
    "SELECT FROM tq.tab WHERE ANT == 3",
    "SELECT TIME FROM tq.tab ORDERBY DESC TIME",
):
    try:
        print(q, "->", taql(q).getcol("TIME").tolist())
    except Exception as err:
        print(q, "-> raises", err)
sel = t.query("ANT == 3")
for label, f in (
    ("sel.rownumbers(t)", lambda: list(sel.rownumbers(t))),
    ("t.rownumbers(sel)", lambda: list(t.rownumbers(sel))),
):
    try:
        print(label, "->", [int(x) for x in f()])
    except Exception as err:
        print(label, "-> raises", err)
