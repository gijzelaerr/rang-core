# ruff: noqa
import os
import numpy as np
from casacure.tables import (
    table,
    maketabdesc,
    makearrcoldesc,
    makescacoldesc,
)  # or casacore.tables

# 1. TiledColumnStMan for a variable-shape column
d = maketabdesc([makearrcoldesc("FLAG", False, ndim=2)])
dm = {
    "*1": {
        "TYPE": "TiledColumnStMan",
        "NAME": "TiledFlag",
        "SPEC": {"DEFAULTTILESHAPE": np.array([4, 2, 8], dtype=np.int32)},
        "COLUMNS": ["FLAG"],
    }
}
for name, nrow in (("tcsm0.tab", 0), ("tcsm4.tab", 4)):
    try:
        t = table(name, d, nrow=nrow, dminfo=dm, ack=False)
        if nrow == 0:
            t.addrows(4)
            t.putcol("FLAG", np.zeros((4, 4, 2), bool))
        t.close()
        print(name, "created")
    except Exception as err:
        print(name, "raises:", err)
    print(name, "on disk:", sorted(os.listdir(name)) if os.path.exists(name) else None)

# 2. a variable-shape column in TiledShapeStMan, created with rows
d = maketabdesc([makearrcoldesc("DATA", 0.0, ndim=2)])
dm = {
    "*1": {
        "TYPE": "TiledShapeStMan",
        "NAME": "TiledDATA",
        "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)},
        "COLUMNS": ["DATA"],
    }
}
try:
    table("tsm8.tab", d, nrow=8, dminfo=dm, ack=False).close()
    print("tsm8.tab created")
except Exception as err:
    print("tsm8.tab raises:", err)
print(
    "tsm8.tab on disk:",
    sorted(os.listdir("tsm8.tab")) if os.path.exists("tsm8.tab") else None,
)

# 3. getcoldesc of IncrementalStMan / TiledShapeStMan columns
d = maketabdesc([makescacoldesc("TIME", 0.0), makearrcoldesc("DATA", 0.0, ndim=2)])
dm = {
    "*1": {
        "TYPE": "IncrementalStMan",
        "NAME": "TimeISM",
        "SPEC": {},
        "COLUMNS": ["TIME"],
    },
    "*2": {
        "TYPE": "TiledShapeStMan",
        "NAME": "TiledDATA",
        "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)},
        "COLUMNS": ["DATA"],
    },
}
t = table("desc.tab", d, nrow=0, dminfo=dm, ack=False)
t.addrows(8)
t.putcol("TIME", np.repeat([1.0, 2.0], 4))
t.putcol("DATA", np.ones((8, 4, 2)))
t.close()
t = table("desc.tab", ack=False)
for c in ("TIME", "DATA"):
    cd = t.getcoldesc(c)
    print(c, cd["dataManagerType"], cd["dataManagerGroup"])
print(
    {
        k: v
        for k, v in t.getdminfo()["*2"]["SPEC"]["HYPERCUBES"]["*1"].items()
        if k != "ID"
    }
)
