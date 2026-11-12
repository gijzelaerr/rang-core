# ruff: noqa
"""U5 casacure probes. Usage: python probe.py <cc|pc> <workdir> <probe> [...]

cc = casacure.tables / casacure.measures, pc = python-casacore (casacore.tables /
casacore.measures). Each probe prints plain lines; run the same probe on both.
"""

import os
import subprocess
import sys

import numpy as np

BACK, WORK, PROBE = sys.argv[1], sys.argv[2], sys.argv[3]
if BACK == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
os.makedirs(WORK, exist_ok=True)
P = lambda n: os.path.join(WORK, f"{BACK}-{n}")  # noqa: E731


def show(label, fn):
    try:
        print(label, "->", repr(fn()))
    except BaseException as e:  # noqa: BLE001
        print(label, "-> RAISES", type(e).__name__, str(e).splitlines()[0][:200])


def dminfo_tiled(col):
    return {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledFlag",
            "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)},
            "COLUMNS": [col],
        }
    }


if PROBE == "dminfo":  # items 1 and 2
    # (1) variable-shape column + TiledColumnStMan
    d = T.maketabdesc([T.makearrcoldesc("FLAG", False, ndim=2)])
    show(
        "1 create var-shape FLAG in TiledColumnStMan",
        lambda: T.table(
            P("tcsm-var"), d, nrow=4, dminfo=dminfo_tiled("FLAG"), ack=False
        ).close(),
    )
    # (2) shape given, no options
    c = T.makearrcoldesc("FLAG", False, shape=[4, 2])
    print("2 makearrcoldesc(shape=[4,2]) option:", c["desc"].get("option"))
    show(
        "2 create shape=[4,2] FLAG in TiledColumnStMan",
        lambda: T.table(
            P("tcsm-shape"),
            T.maketabdesc([c]),
            nrow=4,
            dminfo=dminfo_tiled("FLAG"),
            ack=False,
        ).close(),
    )
    t = T.table(
        P("plain-shape"),
        T.maketabdesc([T.makearrcoldesc("FLAG", False, shape=[4, 2])]),
        nrow=1,
        ack=False,
    )
    print("2 getcoldesc option after create:", t.getcoldesc("FLAG").get("option"))
    t.close()

elif PROBE == "open":  # open a table written by the other backend
    for name in sys.argv[4:]:

        def rd(name=name):
            t = T.table(name, ack=False)
            out = (
                t.nrows(),
                t.getcoldesc("FLAG").get("option"),
                t.getcol("FLAG").shape,
            )
            t.close()
            return out

        show(f"open {os.path.basename(name)}", rd)

elif PROBE == "measures":  # item 3
    if BACK == "cc":
        from casacure.measures import measures
    else:
        from casacore.measures import measures
    dm = measures()
    q = lambda v, u: {"value": v, "unit": u}  # noqa: E731
    e = dm.epoch("UTC", q(59444.5, "d"))
    for ref in ("TAI", "UT1", "UT2", "TT", "TDT", "TDB"):
        show(
            f"3 UTC 59444.5d -> {ref}",
            lambda ref=ref: (
                dm.measure(e, ref)["refer"],
                dm.measure(e, ref)["m0"]["value"] - 59444.5,
            ),
        )
    show(
        "3 TAI 59444.5d -> UTC",
        lambda: (
            dm.measure(dm.epoch("TAI", q(59444.5, "d")), "UTC")["m0"]["value"] - 59444.5
        ),
    )
    pos = dm.position(
        "ITRF", q(5109360.133, "m"), q(2006852.586, "m"), q(-3238948.127, "m")
    )
    show(
        "3 position(ITRF, x,y,z m)",
        lambda: {k: (pos[k]["value"], pos[k]["unit"]) for k in ("m0", "m1", "m2")},
    )
    for ref in ("ITRF", "WGS84"):
        show(
            f"3 measure(pos, {ref})",
            lambda ref=ref: {
                k: (
                    round(dm.measure(pos, ref)[k]["value"], 9),
                    dm.measure(pos, ref)[k]["unit"],
                )
                for k in ("m0", "m1", "m2")
            },
        )

elif (
    PROBE == "mktsm"
):  # item 4 fixture: TiledShapeStMan DATA, written by either backend
    n = 2000
    d = T.maketabdesc([T.makearrcoldesc("DATA", 0j, ndim=2, valuetype="complex")])
    dmi = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TiledDATA",
            "SPEC": {"DEFAULTTILESHAPE": np.array([4, 16, 64], dtype=np.int32)},
            "COLUMNS": ["DATA"],
        }
    }
    t = T.table(P("tsm"), d, nrow=n, dminfo=dmi, ack=False)
    t.putcol("DATA", np.ones((n, 16, 4), dtype=np.complex64))
    t.close()
    print("written", P("tsm"), sorted(os.listdir(P("tsm"))))

elif PROBE == "truncate":  # item 4: open, truncate the biggest file to half, read
    path = sys.argv[4]
    t = T.table(path, ack=False)
    files = [os.path.join(path, f) for f in os.listdir(path) if f.startswith("table.f")]
    big = max(files, key=os.path.getsize)
    size = os.path.getsize(big)
    os.truncate(big, size // 2)
    print("4 truncated", os.path.basename(big), size, "->", size // 2, flush=True)
    show("4 getcol DATA after truncation", lambda: t.getcol("DATA").shape)

elif PROBE == "describe":  # item 5: ISM and TSM columns written by python-casacore
    path = sys.argv[4]
    t = T.table(path, ack=False)
    for col in ("TIME", "ANT", "DATA"):
        cd = t.getcoldesc(col)
        print(
            f"5 getcoldesc {col}: dataManagerType={cd.get('dataManagerType')!r} "
            f"dataManagerGroup={cd.get('dataManagerGroup')!r}"
        )
    for k, v in sorted(t.getdminfo().items()):
        spec = v.get("SPEC", {})
        print(
            f"5 getdminfo {k}: TYPE={v['TYPE']} NAME={v['NAME']!r} COLUMNS={list(v['COLUMNS'])} "
            f"SPEC keys={sorted(spec)} HYPERCUBES={spec.get('HYPERCUBES', {}).get('*1', {}) if isinstance(spec.get('HYPERCUBES'), dict) else spec.get('HYPERCUBES')}"
        )

elif PROBE == "mkdescribe":  # item 5 fixture, python-casacore only
    d = T.maketabdesc(
        [
            T.makescacoldesc("TIME", 0.0),
            T.makescacoldesc("ANT", 0),
            T.makearrcoldesc("DATA", 0.0, ndim=2),
        ]
    )
    dmi = {
        "*1": {
            "TYPE": "IncrementalStMan",
            "NAME": "TimeISM",
            "SPEC": {},
            "COLUMNS": ["TIME", "ANT"],
        },
        "*2": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TiledDATA",
            "SPEC": {"DEFAULTTILESHAPE": np.array([2, 4, 8], dtype=np.int32)},
            "COLUMNS": ["DATA"],
        },
    }
    t = T.table(P("describe"), d, nrow=8, dminfo=dmi, ack=False)
    t.putcol("TIME", np.repeat([1.0, 2.0], 4))
    t.putcol("ANT", np.arange(8))
    t.putcol("DATA", np.ones((8, 4, 2)))
    t.close()
    print("written", P("describe"))

elif PROBE == "taql":  # item 6
    path = P("taql")
    t = T.table(
        path,
        T.maketabdesc([T.makescacoldesc("TIME", 0.0), T.makescacoldesc("ANT", 0)]),
        nrow=6,
        ack=False,
    )
    t.putcol("TIME", np.arange(6.0))
    t.putcol("ANT", np.array([3, 1, 2, 3, 1, 2]))
    t.flush()
    qs = {
        "BETWEEN": f"SELECT TIME FROM {path} WHERE TIME BETWEEN 1 AND 3",
        "bare SELECT FROM": f"SELECT FROM {path} WHERE ANT == 3",
        "ORDERBY DESC TIME": f"SELECT TIME FROM {path} ORDERBY DESC TIME",
        "ORDERBY TIME DESC": f"SELECT TIME FROM {path} ORDERBY TIME DESC",
    }
    for k, q in qs.items():
        show("6 " + k, lambda q=q: T.taql(q).getcol("TIME").tolist())
    sel = t.query("ANT == 3")
    show("6 sel.rownumbers()", lambda: list(sel.rownumbers()))
    show("6 sel.rownumbers(t)", lambda: list(sel.rownumbers(t)))
    show("6 t.rownumbers(sel)", lambda: list(t.rownumbers(sel)))
    t.close()

elif PROBE == "unwritten":  # items 7 and 12
    d = T.maketabdesc(
        [
            T.makescacoldesc("D", 0.0),
            T.makescacoldesc("S", ""),
            T.makescacoldesc("B", False),
            T.makearrcoldesc("A", 0.0, ndim=1),
            T.makearrcoldesc("FLAG_CATEGORY", False, ndim=3),
        ]
    )
    t = T.table(P("unwritten"), d, nrow=3, ack=False)
    t.putcol("D", np.arange(3.0))
    t.close()
    t = T.table(P("unwritten"), ack=False)
    show(
        "7 getcol FLAG_CATEGORY (never written)",
        lambda: (t.getcol("FLAG_CATEGORY").shape, t.getcol("FLAG_CATEGORY").dtype),
    )
    show(
        "7 getcell FLAG_CATEGORY 0",
        lambda: np.asarray(t.getcell("FLAG_CATEGORY", 0)).shape,
    )
    t.close()
    t = T.table(P("zero"), d, nrow=0, ack=False)
    t.close()
    t = T.table(P("zero"), ack=False)
    for c in ("D", "S", "B", "A", "FLAG_CATEGORY"):
        show(
            f"12 0-row getcol {c}",
            lambda c=c: (
                np.asarray(t.getcol(c)).dtype.str,
                np.asarray(t.getcol(c)).shape,
            ),
        )
    t.close()

elif PROBE == "mkaddcols":  # item 11 fixture
    n = 20000
    d = T.maketabdesc(
        [
            T.makescacoldesc("TIME", 0.0),
            T.makearrcoldesc("DATA", 0j, ndim=2, valuetype="complex"),
        ]
    )
    t = T.table(P("addcols"), d, nrow=n, ack=False)
    t.putcol("TIME", np.arange(n, dtype=float))
    t.putcol("DATA", np.ones((n, 16, 4), dtype=np.complex64))
    t.close()
    print("written", P("addcols"))

elif PROBE == "addcols":  # item 11: add a column to the existing StandardStMan
    path = sys.argv[4]
    ls = lambda: {
        f: os.path.getsize(os.path.join(path, f))
        for f in sorted(os.listdir(path))
        if f.startswith("table.f")
    }  # noqa: E731
    print("11 before", ls())
    t = T.table(path, readonly=False, ack=False)
    dm = [v for v in t.getdminfo().values() if "DATA" in v["COLUMNS"]][0]
    t.addcols(
        T.makearrcoldesc("CORRECTED_DATA", 0j, ndim=2, valuetype="complex"),
        dminfo={"TYPE": dm["TYPE"], "NAME": dm["NAME"], "SPEC": dm["SPEC"]},
    )
    t.flush()
    t.close()
    print("11 after ", ls())

elif PROBE == "multifile":  # item 13
    for name in sys.argv[4:]:
        show(
            f"13 open {os.path.basename(name)}",
            lambda name=name: T.table(name, ack=False).colnames(),
        )

elif PROBE == "mk13":  # item 13 fixtures, python-casacore only
    d = T.maketabdesc([T.makescacoldesc("X", 0.0)])
    t = T.table(
        P("mem"),
        d,
        nrow=2,
        dminfo={
            "*1": {"TYPE": "MemoryStMan", "NAME": "m", "SPEC": {}, "COLUMNS": ["X"]}
        },
        ack=False,
    )
    t.close()
    print("written", P("mem"))
else:
    sys.exit(f"unknown probe {PROBE}")
_ = subprocess
