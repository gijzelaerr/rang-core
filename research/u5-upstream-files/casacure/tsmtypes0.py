# ruff: noqa
import numpy as np, sys, os

if sys.argv[1] == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
os.chdir(sys.argv[2])
for mgr in ("TiledShapeStMan", "TiledColumnStMan"):
    for vt, dt in (
        ("boolean", bool),
        ("int", np.int32),
        ("float", np.float32),
        ("double", np.float64),
        ("complex", np.complex64),
        ("dcomplex", np.complex128),
    ):
        name = f"{mgr}-{vt}.tab"
        kw = dict(shape=[4, 2]) if mgr == "TiledColumnStMan" else dict(ndim=2)
        d = T.maketabdesc([T.makearrcoldesc("X", dt(0), valuetype=vt, **kw)])
        dm = {
            "*1": {
                "TYPE": mgr,
                "NAME": "tx",
                "SPEC": {"DEFAULTTILESHAPE": np.array([4, 2, 8], dtype=np.int32)},
                "COLUMNS": ["X"],
            }
        }
        try:
            t = T.table(name, d, nrow=0, dminfo=dm, ack=False)
            t.addrows(8)
            t.putcol("X", np.ones((8, 4, 2), dtype=dt))
            t.close()
            t = T.table(name, ack=False)
            ok = t.getcol("X").dtype
            t.close()
            print(mgr, vt, "ok", ok)
        except Exception as e:
            print(mgr, vt, "raises", str(e)[:120])
