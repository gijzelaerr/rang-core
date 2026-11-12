Target: https://github.com/tmolteno/casacure/issues
Status: ready to post
Reproduced on: casacure 3.8.41 (PyPI, Linux x86_64, CPython 3.12), python-casacore 3.8.1 as reference, 2026-11-12; source read at de45b5d
Duplicates checked: open and closed issues and PRs, searches "FixedShape", "TiledShapeStMan", "tiled element type", "getcoldesc", "dminfo", "nrow"; nearest #20 (dminfo ignored, fixed 3.8.32), #21 (DEFAULTTILESHAPE transposed, closed), #41 (TiledColumnStMan header tile shape, fixed 3.8.41); none covers these
Title: Tiled managers on create: a variable-shape column is accepted for TiledColumnStMan, nrow > 0 fails and leaves a broken table; getcoldesc reports StandardStMan for casacore tables

---

Four related differences around tiled storage managers on casacure 3.8.41, against python-casacore 3.8.1. One reproduction covers them:

```python
import os
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc, makescacoldesc  # or casacore.tables

# 1. TiledColumnStMan for a variable-shape column
d = maketabdesc([makearrcoldesc("FLAG", False, ndim=2)])
dm = {"*1": {"TYPE": "TiledColumnStMan", "NAME": "TiledFlag",
             "SPEC": {"DEFAULTTILESHAPE": np.array([4, 2, 8], dtype=np.int32)}, "COLUMNS": ["FLAG"]}}
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
dm = {"*1": {"TYPE": "TiledShapeStMan", "NAME": "TiledDATA",
             "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)}, "COLUMNS": ["DATA"]}}
try:
    table("tsm8.tab", d, nrow=8, dminfo=dm, ack=False).close()
    print("tsm8.tab created")
except Exception as err:
    print("tsm8.tab raises:", err)

# 3. getcoldesc of IncrementalStMan / TiledShapeStMan columns
d = maketabdesc([makescacoldesc("TIME", 0.0), makearrcoldesc("DATA", 0.0, ndim=2)])
dm = {"*1": {"TYPE": "IncrementalStMan", "NAME": "TimeISM", "SPEC": {}, "COLUMNS": ["TIME"]},
      "*2": {"TYPE": "TiledShapeStMan", "NAME": "TiledDATA",
             "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)}, "COLUMNS": ["DATA"]}}
t = table("desc.tab", d, nrow=0, dminfo=dm, ack=False)
t.addrows(8)
t.putcol("TIME", np.repeat([1.0, 2.0], 4))
t.putcol("DATA", np.ones((8, 4, 2)))
t.close()
t = table("desc.tab", ack=False)
for c in ("TIME", "DATA"):
    cd = t.getcoldesc(c)
    print(c, cd["dataManagerType"], cd["dataManagerGroup"])
print({k: v for k, v in t.getdminfo()["*2"]["SPEC"]["HYPERCUBES"]["*1"].items() if k != "ID"})
```

**1. TiledColumnStMan on a variable-shape column is accepted at `nrow=0`.** casacure creates `tcsm0.tab`, and `addrows` + `putcol` + `close` succeed. python-casacore refuses at creation with `TiledColumnStMan needs array column FLAG to be FixedShape` and writes nothing. It also cannot open casacure's table, failing with the same message. `default_ms(path, tabdesc={}, dminfo=dm)` behaves the same way. Expected: refuse at creation, as casacore does.

**2. `nrow > 0` with a variable-shape column in a tiled manager fails, with a misleading message, and leaves a table behind.**
- `tcsm4.tab`: `column .FLAG: bool cell length 0 does not match shape [] is not a scalar column (array columns are not writable yet)`.
- `tsm8.tab` (a valid TiledShapeStMan request, which python-casacore creates): `encode .DATA: unsupported tiled element type Double`. It fails the same way with an empty `SPEC` (no tile shape), so it is not the tile-shape validation. int, float, complex and dcomplex fail the same way. For bool the message is the `array columns are not writable yet` one. The error is raised by `table()` itself, not at `close()`.
- In both cases `table.dat`, `table.f0`, `table.f0_TSM*` and `table.lock` stay on disk. casacure reopens `tcsm4.tab` as a 4-row table with `DEFAULTTILESHAPE [524288]`. python-casacore fails on it with `TiledStMan::headerFileGet: mismatch in #row; expected 4, found 0`.
- The same TiledShapeStMan columns work when created at `nrow=0` and grown with `addrows`.

The messages come from `crates/casacure/src/tsm.rs:81` and `crates/casacure/src/table.rs:198` (de45b5d). Expected: create the rows with undefined cells, as casacore does. Failing that, refuse before anything is written, with a message naming the cause.

**3. `getcoldesc` reports `StandardStMan` for columns of a table casacore wrote.** Run part 3 with python-casacore, then reopen `desc.tab` with casacure and repeat the last four lines:

| `desc.tab` written by | read by | TIME | DATA |
| --- | --- | --- | --- |
| python-casacore | casacure | `StandardStMan` / `StandardStMan` | `StandardStMan` / `StandardStMan` |
| python-casacore | python-casacore | `IncrementalStMan` / `TimeISM` | `TiledShapeStMan` / `TiledDATA` |
| casacure | casacure | `IncrementalStMan` / `TimeISM` | `TiledShapeStMan` / `TiledDATA` |

`getdminfo` on the same table is right. python-casacore's `getcoldesc(col, actual=True)`, the default, reports the manager the column is bound to. With `actual=False` it gives the stored description, and that is `StandardStMan` / `StandardStMan`, the same as casacure's answer. So casacure returns the stored fields (`crates/casacure-python/src/table.rs:3594`) where python-casacore returns the actual ones. casacure's `getcoldesc` also has no `actual` keyword.

**4. TiledShapeStMan hypercube SPEC and the requested tile shape.** casacure's `getdminfo()["*2"]["SPEC"]["HYPERCUBES"]["*1"]` is `{'CubeShape': [], 'TileShape': [], 'CellShape': [], 'BucketSize': 8}` on both tables. python-casacore gives `CubeShape [2 4 8], TileShape [2 4 8], CellShape [2 4], BucketSize 512` on its own table. On the casacure-written table, python-casacore shows that the requested `DEFAULTTILESHAPE [2, 4, 8]` was stored as `[2, 4, 8192]` (`BucketSize 524288`, 512 KiB of tile for 512 bytes of data). casacure's own `getdminfo` also reports `[2, 4, 8192]`. This looks like the 3.8.33 deferral: the request is deferred at `nrow=0`, then not applied once the cell shape is known.
