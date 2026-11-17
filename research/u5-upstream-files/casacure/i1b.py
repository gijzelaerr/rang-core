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
    t = T.table(p, d, nrow=0, dminfo=dmi, ack=False)
    print("nrow=0 created")
    t.addrows(4)
    t.putcol("FLAG", np.zeros((4, 4, 2), bool))
    t.close()
    print("addrows+putcol+close ok")
except Exception as e:
    print("raises:", type(e).__name__, str(e).replace(os.path.dirname(p), "<dir>"))
print("on disk:", sorted(os.listdir(p)) if os.path.exists(p) else None)
if sys.argv[1] == "cc":
    ms = p + ".ms"
    try:
        desc = T.required_ms_desc("MAIN")
        desc["FLAG"]["shape"] = None if False else desc["FLAG"].get("shape")
        T.default_ms(ms, tabdesc={}, dminfo=dmi).close()
        print("default_ms ok", sorted(os.listdir(ms))[:6])
    except Exception as e:
        print(
            "default_ms raises:",
            type(e).__name__,
            str(e).replace(os.path.dirname(p), "<dir>"),
        )
