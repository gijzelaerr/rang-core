# ruff: noqa
"""casacure writes fixed-shape string arrays; a variable-shape string array written by casacore as control.
Usage: python -I casacure_write2.py cure|core <workdir>"""

import os
import sys

which = sys.argv[1]
os.chdir(sys.argv[2])
if which == "cure":
    from casacure.tables import makearrcoldesc, maketabdesc, table

    for name, opt in [("sd-cure.tab", 1), ("si-cure.tab", 4)]:
        d = maketabdesc(
            [makearrcoldesc("S", "", shape=[2], options=opt, valuetype="string")]
        )
        t = table(name, d, nrow=3, ack=False)
        for r in range(3):
            t.putcell("S", r, ["p%d" % r, "q" * (r + 1)])
        t.close()
        t = table(name, ack=False)
        try:
            print(name, "casacure reads own", t.getcol("S"))
        except Exception as e:
            print(name, "casacure reads own RAISES", type(e).__name__, e)
        t.close()
    t = table("sv-core.tab", ack=False)
    print(
        "casacure reads casacore variable-shape string column:",
        t.getcol("S"),
        t.getcell("S", 1),
    )
    t.close()
    print("iscelldefined", hasattr(t, "iscelldefined"), "info", hasattr(t, "info"))
else:
    import casacore.tables as pt

    d = pt.maketabdesc([pt.makearrcoldesc("S", "", ndim=1, valuetype="string")])
    t = pt.table("sv-core.tab", d, nrow=3, ack=False)
    for r in range(3):
        t.putcell("S", r, ["p%d" % r, "q" * (r + 1)])
    t.close()
    print("casacore wrote sv-core.tab")
    if len(sys.argv) > 3:
        for name in ["sd-cure.tab", "si-cure.tab"]:
            try:
                t = pt.table(name, ack=False)
                print(name, "casacore reads", t.getcol("S"))
                t.close()
            except Exception as e:
                print(name, "casacore RAISES", type(e).__name__, str(e)[:200])
