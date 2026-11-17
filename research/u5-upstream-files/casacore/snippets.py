# ruff: noqa  (one-off upstream reproduction probe)
"""Run the issue-text snippets as written. Usage: snippets.py <dir> <name> [arg]"""

import os
import struct
import subprocess
import sys

import casacore.tables as pt
import numpy as np

d, name = sys.argv[1], sys.argv[2]
os.makedirs(d, exist_ok=True)
os.chdir(d)
if name == "ism":
    N = int(sys.argv[3])
    cd = pt.makearrcoldesc("V", 0.0, ndim=1)
    dm = {
        "*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["V"]}
    }
    t = pt.table("t", pt.maketabdesc([cd]), dminfo=dm, nrow=10, ack=False)
    for r in range(10):
        t.putcell("V", r, np.full(4, float(r)))
    for k in range(N):
        t.putcell("V", 5, np.full(4, 100.0 + k))
    t.close()
    b = open("t/table.f0i", "rb").read()
    off = 16
    rc = []
    while off + 8 <= len(b):
        c, nd = struct.unpack_from("<Ii", b, off)
        n = int(np.prod(struct.unpack_from("<%di" % nd, b, off + 8)))
        rc.append(c - 2**32 if c >= 2**31 else c)
        off = (off + 8 + 4 * nd + 8 * n + 7) // 8 * 8
    print(
        "N",
        N,
        "size",
        len(b),
        "records",
        len(rc),
        "refcounts",
        rc,
        "row5",
        pt.table("t", ack=False).getcell("V", 5)[0],
    )
elif name == "tcs":
    cd = pt.makearrcoldesc("A", 0.0, shape=[4, 2])
    dm = {
        "*1": {
            "TYPE": "TiledCellStMan",
            "NAME": "TCS",
            "SPEC": {"DEFAULTTILESHAPE": [4, 2]},
            "COLUMNS": ["A"],
        }
    }
    t = pt.table("t", pt.maketabdesc([cd]), dminfo=dm, nrow=6, ack=False)
    t.putcol("A", np.zeros((6, 4, 2)))
    print("putcol ok")
    t.putcell("A", 1, np.ones((4, 2)))
    print("putcell ok")
    print("getcol whole", t.getcol("A").shape, "getcell", t.getcell("A", 1)[0, 0])
    for f in (
        lambda: t.putcol("A", np.full((2, 4, 2), 7.0), startrow=2, nrow=2),
        lambda: t.getcol("A", startrow=2, nrow=2),
    ):
        try:
            f()
            print("ranged ok")
        except Exception as e:
            print("ranged:", e)
elif name == "msm":
    dm = {"*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["D"]}}
    dd = pt.maketabdesc(
        [pt.makearrcoldesc("D", 0.0, shape=[3]), pt.makescacoldesc("S", 0)]
    )
    pt.table("t", dd, dminfo=dm, nrow=5, ack=False).close()
    for code in (
        "t=pt.table('t',ack=False)\ntry: t.getcol('D')\nexcept Exception as e: print('getcol:', e)\nt.close(); print('closed')",
        "pt.table('t',ack=False).close(); print('closed')",
    ):
        r = subprocess.run(
            [sys.executable, "-u", "-c", "import casacore.tables as pt\n" + code],
            capture_output=True,
            text=True,
        )
        print("rc", r.returncode, (r.stdout + r.stderr).strip().replace("\n", " | "))
elif name == "mf":
    t = pt.table("t", pt.maketabdesc([pt.makescacoldesc("I", 0)]), nrow=5, ack=False)
    for i in range(100):
        t.addcols(
            pt.maketabdesc([pt.makearrcoldesc("A%03d" % i, 0.0, ndim=1)]),
            dminfo={
                "TYPE": "StandardStMan",
                "NAME": "SSM%03d_with_a_long_name_to_grow_header" % i,
                "SPEC": {},
            },
        )
    t.close()
    b = open("t/table.mf", "rb").read()
    print(
        "mf size",
        len(b),
        "header",
        struct.unpack(">q", b[32:40])[0],
        "block",
        struct.unpack(">q", b[40:48])[0],
    )
