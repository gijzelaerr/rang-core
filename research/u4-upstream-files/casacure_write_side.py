# ruff: noqa
"""Fixed-shape string tables and a variable-shape float column. Usage: python -I casacure_write_side.py cure|core <workdir>"""

import os
import sys

import numpy as np

which = sys.argv[1]
os.chdir(sys.argv[2])
if which == "cure":
    from casacure.tables import makearrcoldesc, maketabdesc, table

    for name, opt in [("sd.tab", 1), ("si.tab", 4)]:
        t = table(
            name,
            maketabdesc(
                [makearrcoldesc("S", "", shape=[2], options=opt, valuetype="string")]
            ),
            nrow=3,
            ack=False,
        )
        for r in range(3):
            t.putcell("S", r, ["p%d" % r, "q" * (r + 1)])
        t.close()
        print(name, "casacure reads own:", table(name, ack=False).getcol("S"))
    t = table(
        "vf.tab",
        maketabdesc([makearrcoldesc("V", 0.0, ndim=1, valuetype="float")]),
        nrow=2,
        ack=False,
    )
    print(
        "V desc", {k: t.getcoldesc("V").get(k) for k in ("valueType", "ndim", "option")}
    )
    for dt in (np.float32, np.float64):
        try:
            t.putcell("V", 0, np.arange(2.0, dtype=dt))
            print("float column putcell", dt.__name__, "ok")
        except Exception as e:
            print("float column putcell", dt.__name__, "raises", type(e).__name__, e)
    print("float column getcol", repr(t.getcol("V")))
    t.close()
    t = table(
        "vd.tab", maketabdesc([makearrcoldesc("V", 0.0, ndim=1)]), nrow=2, ack=False
    )
    t.putcell("V", 0, np.arange(2.0))
    print("double column putcell ok", t.getcell("V", 0))
    t.close()
    t = table(
        "ff.tab",
        maketabdesc([makearrcoldesc("V", 0.0, ndim=1, shape=[2], valuetype="float")]),
        nrow=2,
        ack=False,
    )
    t.putcell("V", 0, np.arange(2.0, dtype=np.float32))
    print("fixed-shape float column putcell ok", t.getcell("V", 0))
    t.close()
else:
    import casacore.tables as pt

    t = pt.table(
        "vfc.tab",
        pt.maketabdesc([pt.makearrcoldesc("V", 0.0, ndim=1, valuetype="float")]),
        nrow=2,
        ack=False,
    )
    t.putcell("V", 0, np.arange(2.0, dtype=np.float32))
    print("python-casacore float column putcell ok", t.getcell("V", 0))
    t.close()
    for name in ["sd.tab", "si.tab"]:
        try:
            t = pt.table(name, ack=False)
            print(name, "python-casacore reads", t.getcol("S"))
            t.close()
        except Exception as e:
            print(name, "python-casacore raises", type(e).__name__, repr(str(e))[:200])
