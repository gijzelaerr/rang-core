# ruff: noqa
import os, sys, numpy as np

if sys.argv[1] == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
p = sys.argv[2]
d = T.maketabdesc([T.makearrcoldesc("FLAG", False, ndim=2)])
dmi = {
    "*1": {
        "TYPE": "TiledColumnStMan",
        "NAME": "TiledFlag",
        "SPEC": {"DEFAULTTILESHAPE": np.array([4, 2, 8], dtype=np.int32)},
        "COLUMNS": ["FLAG"],
    }
}
try:
    t = T.table(p, d, nrow=4, dminfo=dmi, ack=False)
    print("created")
except Exception as e:
    print("create raises:", e)
    t = None
print("on disk:", sorted(os.listdir(p)) if os.path.exists(p) else None)
if t is not None:
    try:
        t.putcol("FLAG", np.zeros((4, 4, 2), bool))
        print("putcol ok")
    except Exception as e:
        print("putcol raises:", e)
    try:
        t.close()
        print("closed")
    except Exception as e:
        print("close raises:", e)
    print("on disk:", sorted(os.listdir(p)))
