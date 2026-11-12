# ruff: noqa
import os, sys, numpy as np

if sys.argv[1] == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
path = sys.argv[2]
ls = lambda: {
    f: os.path.getsize(os.path.join(path, f))
    for f in sorted(os.listdir(path))
    if f.startswith("table.f")
}
print("before", ls())
t = T.table(path, readonly=False, ack=False)
t.addcols(T.makescacoldesc("WEIGHT", 0.0))
t.flush()
t.close()
print("after ", ls())
t = T.table(path, ack=False)
print({k: (v["TYPE"], v["NAME"], list(v["COLUMNS"])) for k, v in t.getdminfo().items()})
