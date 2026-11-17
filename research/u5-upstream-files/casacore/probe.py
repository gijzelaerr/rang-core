# ruff: noqa  (one-off upstream reproduction probe)
"""casacore probes for U5. Usage: python probe.py <case> <outdir>. One case per process."""

import os
import shutil
import sys

import casacore.tables as pt
import numpy as np

case, out = sys.argv[1], sys.argv[2]
shutil.rmtree(out, ignore_errors=True)
os.makedirs(out)
t_ = os.path.join(out, "t")


def walk(path, elem):
    """Walk a version-1 StManArrayFile (little-endian): refcount, ndim, dims, data; records 8-aligned."""
    import struct

    b = open(path, "rb").read()
    (ver,) = struct.unpack_from("<I", b, 0)
    off, recs = 16, []
    while off + 8 <= len(b):
        rc, nd = struct.unpack_from("<II", b, off)
        dims = struct.unpack_from("<%di" % nd, b, off + 8)
        n = int(np.prod(dims)) if nd else 0
        recs.append((off, rc, dims))
        off = (off + 8 + 4 * nd + elem * n + 7) // 8 * 8
    print(
        "file version",
        ver,
        "size",
        len(b),
        "records",
        len(recs),
        "refcount 0:",
        sum(r[1] == 0 for r in recs),
    )
    print("  ", recs)


def desc(*cols, dminfo=None):
    return pt.maketabdesc(list(cols))


if case == "fni":  # item 1: alignment gaps in table.f0i
    d = desc(pt.makearrcoldesc("C", 0j, valuetype="complex", ndim=2))
    t = pt.table(t_, d, nrow=4)
    for r in range(4):
        t.putcell("C", r, np.ones((3, 5), np.complex64))
    t.close()


elif case == "fni2":  # item 1, odd-length Int arrays: record = 4+4+4+4n
    d = desc(pt.makearrcoldesc("I", 0, ndim=1))
    t = pt.table(t_, d, nrow=8, ack=False)
    for r in range(8):
        t.putcell(
            "I", r, np.arange(3, dtype=np.int32)
        )  # record 4+4+4+12 = 24? see output
    t.close()
    t = pt.table(t_ + "b", desc(pt.makearrcoldesc("I", 0, ndim=1)), nrow=8, ack=False)
    for r in range(8):
        t.putcell("I", r, np.arange(4, dtype=np.int32))
    t.close()

elif (
    case == "mf"
):  # items 2: MultiFile header block (needs CASARCFILES with table.storage.option: multifile)
    d = desc(pt.makescacoldesc("I", 0), pt.makearrcoldesc("D", 0.0, ndim=1))
    t = pt.table(t_, d, nrow=30, ack=False)
    t.putcol("I", np.arange(30, dtype=np.int32))
    for r in range(30):
        t.putcell("D", r, np.arange(3.0))
    t.close()
    print(os.listdir(t_))

elif (
    case == "mfbig"
):  # item 3: many files -> header larger than one block (small block size via aipsrc)
    cols = [pt.makescacoldesc("I%03d" % i, 0) for i in range(1)]
    t = pt.table(t_, desc(*cols), nrow=5, ack=False)
    for i in range(int(os.environ.get("NCOL", "200"))):
        cd = pt.makearrcoldesc("A%03d" % i, 0.0, ndim=1)
        t.addcols(
            pt.maketabdesc([cd]),
            dminfo={
                "TYPE": "StandardStMan",
                "NAME": "SSM%03d_with_a_long_name_to_grow_header" % i,
                "SPEC": {},
            },
        )
    t.close()
    print(os.listdir(t_))

elif (
    case == "ismrecreate"
):  # item 4: ISM FixedShape indirect column, remove all rows, add rows
    cd = pt.makearrcoldesc(
        "A", 0.0, shape=[64], options=4
    )  # FixedShape, indirect (no Direct)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["A"]}
    }
    t = pt.table(
        t_,
        pt.maketabdesc([cd, pt.makescacoldesc("S", 0)]),
        dminfo=dm,
        nrow=3,
        ack=False,
    )
    t.putcol("A", np.ones((3, 64)))
    t.removerows(list(range(3)))
    t.addrows(5)
    t.putcol("S", np.arange(5, dtype=np.int32))
    t.close()

elif (
    case == "ismread"
):  # item 4 readback in a fresh process: python probe.py ismread <dir-of-previous>
    t = pt.table(os.path.join(out + "_src", "t"), ack=False)
    print(t.getdminfo("A")["TYPE"], t.getcell("A", 0)[:8])

elif (
    case == "ismput"
):  # item 5: repeated putcell with the same shape on a variable-shape ISM column
    cd = pt.makearrcoldesc("A", 0.0, ndim=1)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["A"]}
    }
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=1, ack=False)
    for k in range(int(os.environ.get("NPUT", "10"))):
        t.putcell("A", 0, np.full(1000, float(k)))
        t.flush()
        fs = sorted(
            f for f in os.listdir(t_) if f.startswith("table.f") and f.endswith("i")
        )
        print(k, [(f, os.path.getsize(os.path.join(t_, f))) for f in fs])
    t.close()

elif case == "tcsrange":  # item 6: ranged putcol on TiledCellStMan
    cd = pt.makearrcoldesc("A", 0.0, shape=[4, 2], options=0)
    dm = {
        "*1": {
            "TYPE": "TiledCellStMan",
            "NAME": "TCS",
            "SPEC": {"DEFAULTTILESHAPE": [4, 2]},
            "COLUMNS": ["A"],
        }
    }
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=6, ack=False)
    t.putcol("A", np.zeros((6, 4, 2)))
    print("whole putcol ok")
    t.putcell("A", 1, np.ones((4, 2)))
    print("putcell ok")
    try:
        t.putcol("A", np.full((2, 4, 2), 7.0), startrow=2, nrow=2)
        print("ranged putcol ok", t.getcol("A")[:, 0, 0])
    except Exception as e:
        print("ranged putcol:", type(e).__name__, e)
    try:
        print("ranged getcol", t.getcol("A", startrow=2, nrow=2)[:, 0, 0])
    except Exception as e:
        print("ranged getcol:", type(e).__name__, e)
    t.close()

elif case == "tcsshape":  # item 7: setShape with unflushed tiles
    cd = pt.makearrcoldesc("A", 0.0, ndim=2)
    dm = {
        "*1": {
            "TYPE": "TiledCellStMan",
            "NAME": "TCS",
            "SPEC": {"DEFAULTTILESHAPE": [4, 4]},
            "COLUMNS": ["A"],
        }
    }
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=1, ack=False)
    t.putcell("A", 0, np.full((4, 4), 1.0))
    t.putcell("A", 0, np.full((8, 4), 2.0))  # new shape, old cube unflushed
    print("after reshape", t.getcell("A", 0)[0, 0], t.getcell("A", 0).shape)
    t.close()
    t = pt.table(t_, ack=False)
    print("reopen", t.getcell("A", 0)[:, 0])

elif case == "msm":  # item 8 write
    dm = {
        "*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["I", "D"]}
    }
    d = pt.maketabdesc(
        [
            pt.makescacoldesc("I", 0),
            pt.makearrcoldesc("D", 0.0, shape=[3]),
            pt.makescacoldesc("S", 0),
        ]
    )
    t = pt.table(t_, d, dminfo=dm, nrow=5, ack=False)
    t.putcol("I", np.arange(1, 6, dtype=np.int32))
    t.putcol("D", np.ones((5, 3)))
    t.putcol("S", np.arange(5, dtype=np.int32))
    print("in session", t.getcol("I"))
    t.close()

elif case == "msmread":  # item 8 readback in a fresh process
    t = pt.table(os.path.join(out + "_src", "t"), ack=False)
    print("nrows", t.nrows(), "dm", t.getdminfo("I")["TYPE"])
    for c in os.environ.get("COLS", "I,D").split(","):
        try:
            print(c, t.getcol(c))
        except Exception as e:
            print(c, "raised", type(e).__name__, e)
    t.close()
    print("closed")

elif case == "pc":  # item 9: python-casacore conversions
    d = pt.maketabdesc(
        [
            pt.makearrcoldesc("S", "", ndim=2),
            pt.makearrcoldesc("S1", "", ndim=1),
            pt.makescacoldesc("U", 0, valuetype="uchar"),
        ]
    )
    t = pt.table(t_, d, nrow=1, ack=False)
    t.putcell("S", 0, np.array([["a", "b", "c"], ["d", "e", "f"]]))
    t.putcell("S1", 0, np.array(["a", "b"]))
    t.putcell("U", 0, 7)
    t.putkeyword("K", 5)
    print("2-D string getcell:", type(t.getcell("S", 0)), repr(t.getcell("S", 0)))
    print("1-D string getcell:", type(t.getcell("S1", 0)), repr(t.getcell("S1", 0)))
    print("getcol 2-D:", repr(t.getcol("S")))
    print(
        "uchar:",
        repr(t.getcell("U", 0)),
        t.getcol("U").dtype,
        t.getcoldesc("U")["valueType"],
    )
    print("int keyword type:", t.getkeyword("K"), type(t.getkeyword("K")))
    t.close()

elif (
    case == "ismput2"
):  # item 5: putcell with the same shape, table reopened between puts; also multi-row
    cd = pt.makearrcoldesc("A", 0.0, ndim=1)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["A"]}
    }
    nrow = int(os.environ.get("NROW", "1"))
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=nrow, ack=False)
    t.close()
    for k in range(5):
        t = pt.table(t_, readonly=False, ack=False)
        for r in range(nrow):
            t.putcell("A", r, np.full(1000, float(k + r)))
        t.close()
        print(k, "table.f0i size", os.path.getsize(os.path.join(t_, "table.f0i")))
    t = pt.table(t_, ack=False)
    print("values", [t.getcell("A", r)[0] for r in range(nrow)])

elif (
    case == "ismput3"
):  # item 5: alternate putcell between rows, same shape, one session
    cd = pt.makearrcoldesc("A", 0.0, ndim=1)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["A"]}
    }
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=2, ack=False)
    for k in range(int(os.environ.get("NPUT", "4"))):
        for r in (0, 1):
            t.putcell("A", r, np.full(1000, float(10 * k + r)))
            if os.environ.get("FLUSH", "1") == "1":
                t.flush()
            print(
                "put",
                k,
                "row",
                r,
                "table.f0i size",
                os.path.getsize(os.path.join(t_, "table.f0i")),
            )
    print("values", t.getcell("A", 0)[0], t.getcell("A", 1)[0])
    t.close()

elif (
    case == "ismput4"
):  # item 5: fill rows in order, then re-put one middle row with the same shape K times
    cd = pt.makearrcoldesc("V", 0.0, ndim=1)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["V"]}
    }
    t = pt.table(t_, pt.maketabdesc([cd]), dminfo=dm, nrow=10, ack=False)
    for r in range(10):
        t.putcell("V", r, np.full(4, float(r)))
    for k in range(int(os.environ.get("NPUT", "5"))):
        t.putcell("V", 5, np.full(4, 100.0 + k))
    t.close()
    print("values", [pt.table(t_, ack=False).getcell("V", r)[0] for r in range(10)])
    walk(os.path.join(t_, "table.f0i"), 8)
