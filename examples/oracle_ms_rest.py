"""The oracle side of task E5 (research/e5-table-writer-rest.md).

python-casacore 3.8.1 in `rang-ms-reader:local` (NumPy 2.5.3):

    python examples/oracle_ms_rest.py write <out> <fixture.ms> <luno.ms>
    CASARCFILES=<rc> python examples/oracle_ms_rest.py write-mf <out>
    python examples/oracle_ms_rest.py readback <dump-dir> <label=table> ...
    python examples/oracle_ms_rest.py read-column <out.json> <table> <column>

`write` performs every frozen case but the MultiFile ones (the module-level
`CASES`) with python-casacore, each on a fresh path under
`<out>/casacore/<case>` (cases with a `source` on a copy of it: the
fixture, the LUNO export or casacore's own output of an earlier case), one
close per session, and stores the values it used in `<out>/values/<case>.npz`
(seeded generator, seed 20261030) and the case list with wall times in
`<out>/cases.json`. `write-mf` does the MultiFile cases; casacore makes
MultiFile tables when the aipsrc file named by `CASARCFILES` says
`table.storage.option: multifile` (python-casacore has no argument for it).
No case reads a table inside its write session: values that depend on an
input are read before the session, in a separate read-only open (oracle
side only; the core side gets the stored values). The host checker
(`examples/check_ms_rest.py`) replays the same functions with
`rang.core_ms_write` as `pt`. `readback` dumps every column cell by cell
(definedness included), the keywords, column keywords and `table.info`;
MemoryStMan columns are skipped there (casacore aborts after reading one)
and read by `read-column` in a process of their own.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oracle_ms_create import Values, copy_tree, numeric, plain, strings

LOCK = {"lockoptions": "permanent", "ack": False}


def is_core(pt):
    return hasattr(pt, "create_table")


def mf_kw(pt):
    """The core asks for MultiFile; casacore takes it from aipsrc."""
    return {"multifile": True} if is_core(pt) else {}


def runs(rng, n, k=5, longest=9):
    """`n` indices into an alphabet of `k`, in runs of 1 to `longest` rows."""
    out = []
    while len(out) < n:
        out += [int(rng.integers(0, k))] * int(rng.integers(1, longest + 1))
    return np.array(out[:n], dtype=np.int64)


def run_values(v, key, n, alphabet):
    """Values of `n` rows drawn in runs from the alphabet made by
    `alphabet(rng)` (its first axis the choices)."""
    a = v.get(key + ".alphabet", alphabet)
    idx = v.get(key + ".runs", lambda r: runs(r, n, len(a)))
    return a[idx]


def read_before(pt, path, f):
    """Oracle side only: `f(table)` on a read-only open of `path`, closed
    before the write session."""
    t = pt.table(str(path), ack=False)
    try:
        return f(t)
    finally:
        t.close()


SCALARS = [
    ("B", False, "bool", "bool"),
    ("UC", 0, "uchar", "uint8"),
    ("SH", 0, "short", "int16"),
    ("I", 0, "int", "int32"),
    ("UI", 0, "uint", "uint32"),
    ("I64", 0, "int64", "int64"),
    ("F", 0.0, "float", "float32"),
    ("D", 0.0, "double", "float64"),
    ("C", 0j, "complex", "complex64"),
    ("DC", 0j, "dcomplex", "complex128"),
]


def ism(name, columns, **spec):
    return {"TYPE": "IncrementalStMan", "NAME": name, "SPEC": spec, "COLUMNS": columns}


def tiled(kind, name, columns, tile):
    return {
        "TYPE": kind,
        "NAME": name,
        "SPEC": {"DEFAULTTILESHAPE": np.array(tile, np.int32)},
        "COLUMNS": columns,
    }


# ---------------------------------------------------------------------------
# IncrementalStMan.


def i_scalars(pt, path, v, src):
    n = 2000
    cols = [pt.makescacoldesc(c, d, valuetype=vt) for c, d, vt, _ in SCALARS]
    cols.append(pt.makescacoldesc("S", ""))
    names = [c for c, _, _, _ in SCALARS] + ["S"]
    dm = {"*1": ism("ISM", names, BUCKETSIZE=1024)}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK)
    alphabets = {}
    for c, _, _, dt in SCALARS:
        alphabets[c] = v.get(f"{c}.alphabet", lambda r, dt=dt: numeric(r, 5, dt))
        t.putcol(c, run_values(v, c, n, lambda r, c=c: alphabets[c]))
    alphabets["S"] = v.get("S.alphabet", lambda r: strings(r, 5, 0, 13))
    t.putcol("S", list(run_values(v, "S", n, lambda r: alphabets["S"])))
    rows = v.get("edit.rows", lambda r: r.integers(0, n, 40))
    which = v.get("edit.cols", lambda r: r.integers(0, len(names), 40))
    pick = v.get("edit.pick", lambda r: r.integers(0, 5, 40))
    for row, c, k in zip(rows, which, pick):
        name = names[int(c)]
        value = alphabets[name][int(k)]
        t.putcell(
            name, int(row), value.item() if hasattr(value, "item") else str(value)
        )
    t.close()


def i_arrays(pt, path, v, src):
    n = 400
    cols = [
        pt.makearrcoldesc("A", 0.0, shape=[3], options=1),
        pt.makearrcoldesc("AB", False, shape=[5], options=1),
        pt.makearrcoldesc("AS", "", shape=[2], options=1),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makearrcoldesc("FF", 0.0, shape=[2, 2], valuetype="float"),
    ]
    dm = {"*1": ism("ISM", ["A", "AB", "AS", "V", "FF"], BUCKETSIZE=2048)}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK)
    t.putcol("A", run_values(v, "A", n, lambda r: numeric(r, (4, 3), "float64")))
    t.putcol("AB", run_values(v, "AB", n, lambda r: numeric(r, (4, 5), "bool")))
    t.putcol(
        "AS",
        run_values(v, "AS", n, lambda r: strings(r, 8, 0, 9).reshape(4, 2)),
    )
    t.putcol("FF", run_values(v, "FF", n, lambda r: numeric(r, (4, 2, 2), "float32")))
    for row in range(0, n, 3):
        t.putcell(
            "V",
            row,
            v.get(f"V{row}", lambda r, row=row: numeric(r, 1 + row % 4, "float64")),
        )
    for row in (50, 51, 200):
        t.putcell("V", row, v.get(f"Vb{row}", lambda r: numeric(r, 2, "float64")))
    for row in (10, 100, 101, 399):
        t.putcell(
            "FF", row, v.get(f"FFb{row}", lambda r: numeric(r, (2, 2), "float32"))
        )
    t.close()


def i_rows(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    old, extra = 2000, 150
    t.addrows(extra)
    t.putcol(
        "I", run_values(v, "I", extra, lambda r: numeric(r, 5, "int32")), old, extra
    )
    t.putcol(
        "D", run_values(v, "D", extra, lambda r: numeric(r, 5, "float64")), old, extra
    )
    t.putcol(
        "S", list(run_values(v, "S", extra, lambda r: strings(r, 5, 0, 13))), old, extra
    )
    t.removerows([0, 5] + list(range(1200, 1500)) + [old + extra - 1])
    t.close()


i_rows.source = "I-scalars"


def i_rows_all(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    t.removerows(list(range(400)))
    t.addrows(10)
    t.putcol("A", v.get("A", lambda r: numeric(r, (10, 3), "float64")))
    for row in range(10):
        t.putcell("V", row, v.get(f"V{row}", lambda r: numeric(r, 2, "float64")))
    t.close()


i_rows_all.source = "I-arrays"


def i_fixture(pt, path, v, src):
    n = int(v.get("n", lambda r: np.array(read_before(pt, path, lambda t: t.nrows()))))
    array_id = v.get(
        "ARRAY_ID", lambda r: read_before(pt, path, lambda t: t.getcol("ARRAY_ID"))
    )
    t = pt.table(path, readonly=False, **LOCK)
    for c in ("SCAN_NUMBER", "STATE_ID", "FIELD_ID"):
        t.putcol(c, run_values(v, c, n, lambda r: np.arange(5, dtype=np.int32)))
    steps = run_values(v, "TIME", n, lambda r: np.array([0.0, 0.0, 8.0, 8.0, 16.0]))
    t.putcol("TIME", 5.0e9 + np.cumsum(steps))
    t.putcol(
        "INTERVAL", run_values(v, "INTERVAL", n, lambda r: numeric(r, 5, "float64"))
    )
    t.putcol(
        "EXPOSURE", run_values(v, "EXPOSURE", n, lambda r: numeric(r, 5, "float64"))
    )
    t.putcol("ARRAY_ID", array_id)
    t.putcell("FIELD_ID", 70, 3)
    t.close()


i_fixture.source = "FIXTURE"


def pointing_shape(t, column):
    return np.asarray(t.getcell(column, 0)).shape


def i_fixture_pointing(pt, path, v, src):
    p = str(Path(path) / "POINTING")
    n = int(v.get("n", lambda r: np.array(read_before(pt, p, lambda t: t.nrows()))))
    shapes = {
        c: tuple(
            int(x)
            for x in v.get(
                f"{c}.shape",
                lambda r, c=c: np.array(
                    read_before(pt, p, lambda t: pointing_shape(t, c))
                ),
            )
        )
        for c in ("DIRECTION", "TARGET", "SOURCE_OFFSET")
    }
    t = pt.table(p, readonly=False, **LOCK)
    t.putcol("NAME", list(run_values(v, "NAME", n, lambda r: strings(r, 5, 0, 12))))
    t.putcol(
        "TRACKING", run_values(v, "TRACKING", n, lambda r: np.array([True, False]))
    )
    t.putcol(
        "INTERVAL", run_values(v, "INTERVAL", n, lambda r: numeric(r, 5, "float64"))
    )
    extra = 8
    t.addrows(extra)
    t.putcol(
        "TIME", v.get("TIME.new", lambda r: 5e9 + np.arange(extra) * 4.0), n, extra
    )
    t.putcol("INTERVAL", v.get("INTERVAL.new", lambda r: np.full(extra, 4.0)), n, extra)
    t.putcol(
        "NAME", list(v.get("NAME.new", lambda r: strings(r, extra, 0, 12))), n, extra
    )
    t.putcol(
        "NUM_POLY", v.get("NUM_POLY.new", lambda r: np.zeros(extra, np.int32)), n, extra
    )
    t.putcol(
        "TIME_ORIGIN", v.get("TIME_ORIGIN.new", lambda r: np.zeros(extra)), n, extra
    )
    t.putcol(
        "TRACKING", v.get("TRACKING.new", lambda r: numeric(r, extra, "bool")), n, extra
    )
    t.putcol(
        "ANTENNA_ID",
        v.get("ANTENNA_ID.new", lambda r: (np.arange(extra) % 4).astype(np.int32)),
        n,
        extra,
    )
    for c, shape in shapes.items():
        t.putcol(
            c,
            v.get(
                f"{c}.new",
                lambda r, shape=shape: numeric(r, (extra,) + shape, "float64"),
            ),
            n,
            extra,
        )
    t.removerows([0, 1, 2, 3])
    t.close()


i_fixture_pointing.source = "FIXTURE"


def i_pointing(pt, path, v, src):
    pt.default_ms(path).close()
    t = pt.table(str(Path(path) / "POINTING"), readonly=False, **LOCK)
    n = 20
    t.addrows(n)
    steps = run_values(v, "TIME", n, lambda r: np.array([0.0, 4.0, 4.0, 8.0]))
    t.putcol("TIME", 5e9 + np.cumsum(steps))
    t.putcol(
        "ANTENNA_ID",
        v.get("ANTENNA_ID", lambda r: np.tile(np.arange(4, dtype=np.int32), 5)),
    )
    t.putcol(
        "INTERVAL", run_values(v, "INTERVAL", n, lambda r: numeric(r, 3, "float64"))
    )
    t.putcol("NAME", list(run_values(v, "NAME", n, lambda r: strings(r, 3, 0, 10))))
    t.putcol("NUM_POLY", v.get("NUM_POLY", lambda r: np.zeros(n, np.int32)))
    t.putcol(
        "TIME_ORIGIN",
        run_values(v, "TIME_ORIGIN", n, lambda r: numeric(r, 2, "float64")),
    )
    t.putcol(
        "DIRECTION", v.get("DIRECTION", lambda r: numeric(r, (n, 1, 2), "float64"))
    )
    t.putcol("TARGET", v.get("TARGET", lambda r: numeric(r, (n, 1, 2), "float64")))
    t.putcol(
        "TRACKING", run_values(v, "TRACKING", n, lambda r: np.array([True, False]))
    )
    t.close()


def i_create(pt, path, v, src):
    n = 120
    cols = [
        pt.makescacoldesc("B", False),
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("S", ""),
        pt.makescacoldesc("D", 0.0),
        pt.makescacoldesc("J", 0),
        pt.makescacoldesc("K", 0),
    ]
    dm = {
        "*1": ism("ISM1", ["B", "I", "S"]),
        "*2": ism("ISM2", ["D", "J"], PERSCACHESIZE=3),
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK)
    t.putcol("B", run_values(v, "B", n, lambda r: np.array([True, False])))
    t.putcol("I", run_values(v, "I", n, lambda r: numeric(r, 5, "int32")))
    t.putcol("S", list(run_values(v, "S", n, lambda r: strings(r, 5, 0, 20))))
    t.putcol("D", run_values(v, "D", n, lambda r: numeric(r, 5, "float64")))
    t.putcol("J", run_values(v, "J", n, lambda r: numeric(r, 5, "int32")))
    t.putcol("K", v.get("K", lambda r: numeric(r, n, "int32")))
    t.close()


# ---------------------------------------------------------------------------
# StandardStMan.


def s_remove_all(pt, path, v, src):
    n = 50
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("S", ""),
        pt.makearrcoldesc("V", 0.0, ndim=1),
    ]
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 5, 30))))
    for row in range(n):
        t.putcell("V", row, v.get(f"V{row}", lambda r: numeric(r, 3, "float64")))
    t.removerows(list(range(n)))
    t.addrows(5)
    t.putcol("I", v.get("I.new", lambda r: numeric(r, 5, "int32")))
    t.close()


def s_remove_all_luno(pt, path, v, src):
    n = int(v.get("n", lambda r: np.array(read_before(pt, path, lambda t: t.nrows()))))
    t = pt.table(path, readonly=False, **LOCK)
    t.removerows(list(range(n)))
    t.close()


s_remove_all_luno.source = "LUNO"


# ---------------------------------------------------------------------------
# Tiled.


def t_var(pt, path, v, src):
    cols = [
        pt.makearrcoldesc("V", 0.0, ndim=2, valuetype="float"),
        pt.makearrcoldesc("W", False, ndim=2),
    ]
    dm = {"*1": tiled("TiledShapeStMan", "TSS", ["V", "W"], [4, 8, 4])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=20, dminfo=dm, **LOCK)
    for row in range(20):
        if row == 5:
            continue
        shape = (8, 4) if row % 3 else (16, 2)
        t.putcell(
            "V",
            row,
            v.get(f"V{row}", lambda r, shape=shape: numeric(r, shape, "float32")),
        )
    t.putcell("W", 0, v.get("W0", lambda r: numeric(r, (16, 2), "bool")))
    t.addrows(5)
    t.putcell("V", 22, v.get("V22", lambda r: numeric(r, (8, 4), "float32")))
    t.close()


def t_reshape(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    try:
        t.putcell("V", 0, v.get("V0", lambda r: numeric(r, (4, 4), "float32")))
        refused = False
    except Exception as e:  # noqa: BLE001 - recorded, both sides must refuse
        refused = str(e)
    t.close()
    v.get("refused", lambda r: np.array(bool(refused)))
    if not refused:
        raise RuntimeError("a new shape for a TiledShapeStMan row was not refused")


t_reshape.source = "T-var"


def t_multishape(pt, path, v, src):
    desc = pt.maketabdesc([pt.makearrcoldesc("DATA", 0j, ndim=2, valuetype="complex")])
    dm = {"*1": tiled("TiledShapeStMan", "TiledData", ["DATA"], [4, 32, 8])}
    t = pt.default_ms(path, desc, dm)
    n = 30
    t.addrows(n)
    for row in range(n):
        shape = (64, 4) if row < 15 else (32, 4)
        t.putcell(
            "DATA",
            row,
            v.get(f"D{row}", lambda r, shape=shape: numeric(r, shape, "complex64")),
        )
    t.putcol(
        "DATA", v.get("D.again", lambda r: numeric(r, (15, 64, 4), "complex64")), 0, 15
    )
    t.close()


def fixture_shapes(t):
    return {
        c: np.asarray(t.getcell(c, 0)).shape
        for c in (
            "DATA",
            "FLAG",
            "WEIGHT_SPECTRUM",
            "SIGMA_SPECTRUM",
            "WEIGHT",
            "SIGMA",
            "UVW",
        )
    }


def stored_shapes(pt, path, v):
    shapes = {}
    for c in (
        "DATA",
        "FLAG",
        "WEIGHT_SPECTRUM",
        "SIGMA_SPECTRUM",
        "WEIGHT",
        "SIGMA",
        "UVW",
    ):
        s = v.get(
            f"{c}.shape",
            lambda r, c=c: np.array(read_before(pt, path, fixture_shapes)[c]),
        )
        shapes[c] = tuple(int(x) for x in s)
    return shapes


def t_fixture_add(pt, path, v, src):
    n = int(v.get("n", lambda r: np.array(read_before(pt, path, lambda t: t.nrows()))))
    shapes = stored_shapes(pt, path, v)
    t = pt.table(path, readonly=False, **LOCK)
    extra = 10
    t.addrows(extra)
    types = {
        "DATA": "complex64",
        "FLAG": "bool",
        "WEIGHT_SPECTRUM": "float32",
        "SIGMA_SPECTRUM": "float32",
        "WEIGHT": "float32",
        "SIGMA": "float32",
        "UVW": "float64",
    }
    for c, dt in types.items():
        t.putcol(
            c,
            v.get(c, lambda r, c=c, dt=dt: numeric(r, (extra,) + shapes[c], dt)),
            n,
            extra,
        )
    t.putcol("TIME", v.get("TIME", lambda r: 5e9 + np.arange(extra) * 8.0), n, extra)
    t.putcol(
        "ANTENNA1", v.get("ANTENNA1", lambda r: np.zeros(extra, np.int32)), n, extra
    )
    t.putcol(
        "ANTENNA2",
        v.get("ANTENNA2", lambda r: (1 + np.arange(extra) % 3).astype(np.int32)),
        n,
        extra,
    )
    t.putcol(
        "SCAN_NUMBER",
        v.get("SCAN_NUMBER", lambda r: np.full(extra, 9, np.int32)),
        n,
        extra,
    )
    t.putcol(
        "FLAG_ROW", v.get("FLAG_ROW", lambda r: numeric(r, extra, "bool")), n, extra
    )
    t.close()


t_fixture_add.source = "FIXTURE"


def t_fixture_flagcat(pt, path, v, src):
    shapes = stored_shapes(pt, path, v)
    t = pt.table(path, readonly=False, **LOCK)
    shape = (1,) + shapes["FLAG"]
    for row in (3, 4):
        t.putcell(
            "FLAG_CATEGORY", row, v.get(f"FC{row}", lambda r: numeric(r, shape, "bool"))
        )
    t.close()


t_fixture_flagcat.source = "FIXTURE"


def tds_desc(pt):
    td = pt.maketabdesc([pt.makearrcoldesc("D", 0.0, shape=[4, 8], valuetype="float")])
    pt.tabledefinehypercolumn(td, "TDS", 3, ["D"])
    return td


TDS_DM = {"*1": {"TYPE": "TiledDataStMan", "NAME": "TDS", "SPEC": {}, "COLUMNS": ["D"]}}


def d_tds(pt, path, v, src):
    pt.table(path, tds_desc(pt), nrow=0, dminfo=TDS_DM, **LOCK).close()


def d_tds_rows(pt, path, v, src):
    pt.table(path, tds_desc(pt), nrow=10, dminfo=TDS_DM, **LOCK).close()


# ---------------------------------------------------------------------------
# Big-endian.


def b_new(pt, path, v, src):
    n = 30
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("D", 0.0),
        pt.makescacoldesc("S", ""),
        pt.makescacoldesc("B", False),
        pt.makearrcoldesc("A", 0j, shape=[2], options=1, valuetype="complex"),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makearrcoldesc("T", 0.0, shape=[4, 8], valuetype="float"),
        pt.makearrcoldesc("U", 0.0, shape=[3]),
        pt.makescacoldesc("M", 0),
        pt.makescacoldesc("N", ""),
    ]
    dm = {
        "*1": tiled("TiledShapeStMan", "TSS", ["T"], [4, 8, 4]),
        "*2": tiled("TiledColumnStMan", "TCS", ["U"], [3, 16]),
        "*3": ism("ISM", ["M", "N"]),
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, endian="big", **LOCK)
    fill_big(t, v, 0, n)
    t.putkeyword("KD", 1.5)
    t.close()


def fill_big(t, v, old, n, key=""):
    t.putcol("I", v.get("I" + key, lambda r: numeric(r, n, "int32")), old, n)
    t.putcol("D", v.get("D" + key, lambda r: numeric(r, n, "float64")), old, n)
    t.putcol("S", list(v.get("S" + key, lambda r: strings(r, n, 0, 12))), old, n)
    t.putcol("B", v.get("B" + key, lambda r: numeric(r, n, "bool")), old, n)
    t.putcol("A", v.get("A" + key, lambda r: numeric(r, (n, 2), "complex64")), old, n)
    for row in range(old, old + n):
        t.putcell(
            "V",
            row,
            v.get(
                f"V{row}{key}", lambda r, row=row: numeric(r, 1 + row % 4, "float64")
            ),
        )
    t.putcol("T", v.get("T" + key, lambda r: numeric(r, (n, 4, 8), "float32")), old, n)
    t.putcol("U", v.get("U" + key, lambda r: numeric(r, (n, 3), "float64")), old, n)
    t.putcol("M", run_values(v, "M" + key, n, lambda r: numeric(r, 3, "int32")), old, n)
    t.putcol(
        "N", list(run_values(v, "N" + key, n, lambda r: strings(r, 3, 0, 9))), old, n
    )


def b_write(pt, path, v, src):
    n = 30
    t = pt.table(path, readonly=False, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 12))))
    t.putcol("T", v.get("T", lambda r: numeric(r, (n, 4, 8), "float32")))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 3, "int32")))
    t.putcol("N", list(run_values(v, "N", n, lambda r: strings(r, 3, 0, 9))))
    t.putcell("V", 3, v.get("V3", lambda r: numeric(r, 5, "float64")))
    t.putcolkeyword("D", "UNIT", "s")
    t.addrows(5)
    fill_big(t, v, n, 5, ".new")
    t.close()


b_write.source = "B-new"


def b_rows(pt, path, v, src):
    n = 50
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("S", ""),
        pt.makescacoldesc("M", 0),
        pt.makescacoldesc("N", ""),
    ]
    dm = {"*1": ism("ISM", ["M", "N"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, endian="big", **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 20))))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 3, "int32")))
    t.putcol("N", list(run_values(v, "N", n, lambda r: strings(r, 3, 0, 9))))
    t.removerows([1, 2, 30, 49])
    t.close()


# ---------------------------------------------------------------------------
# MemoryStMan and MultiFile.


def m_new(pt, path, v, src):
    n = 10
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("A", 0.0, shape=[3], options=1),
        pt.makescacoldesc("J", 0),
    ]
    dm = {
        "*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["I", "A"]}
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("A", v.get("A", lambda r: numeric(r, (n, 3), "float64")))
    t.putcol("J", v.get("J", lambda r: numeric(r, n, "int32")))
    t.addrows(5)
    t.close()


def f_new(pt, path, v, src):
    n = 30
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("S", ""),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makearrcoldesc("G", 0.0, ndim=1, valuetype="float"),
        pt.makearrcoldesc("T", 0.0, shape=[4, 8], valuetype="float"),
        pt.makescacoldesc("M", 0),
    ]
    dm = {
        "*1": tiled("TiledShapeStMan", "TSS", ["T"], [4, 8, 4]),
        "*2": ism("ISM", ["M"]),
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK, **mf_kw(pt))
    fill_mf(t, v, 0, n)
    t.close()


def fill_mf(t, v, old, n, key=""):
    t.putcol("I", v.get("I" + key, lambda r: numeric(r, n, "int32")), old, n)
    t.putcol("S", list(v.get("S" + key, lambda r: strings(r, n, 0, 12))), old, n)
    for row in range(old, old + n):
        t.putcell(
            "V",
            row,
            v.get(
                f"V{row}{key}", lambda r, row=row: numeric(r, 1 + row % 4, "float64")
            ),
        )
        t.putcell("G", row, v.get(f"G{row}{key}", lambda r: numeric(r, 3, "float32")))
    t.putcol("T", v.get("T" + key, lambda r: numeric(r, (n, 4, 8), "float32")), old, n)
    t.putcol("M", run_values(v, "M" + key, n, lambda r: numeric(r, 3, "int32")), old, n)


def f_write(pt, path, v, src):
    n = 30
    t = pt.table(path, readonly=False, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 12))))
    t.putcol("T", v.get("T", lambda r: numeric(r, (n, 4, 8), "float32")))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 3, "int32")))
    t.addrows(5)
    fill_mf(t, v, n, 5, ".new")
    t.close()


f_write.source = "F-new"
f_new.multifile = f_write.multifile = True

CASES = [
    ("I-scalars", i_scalars),
    ("I-arrays", i_arrays),
    ("I-rows", i_rows),
    ("I-rows-all", i_rows_all),
    ("I-fixture", i_fixture),
    ("I-fixture-pointing", i_fixture_pointing),
    ("I-pointing", i_pointing),
    ("I-create", i_create),
    ("S-remove-all", s_remove_all),
    ("S-remove-all-luno", s_remove_all_luno),
    ("T-var", t_var),
    ("T-reshape", t_reshape),
    ("T-multishape", t_multishape),
    ("T-fixture-add", t_fixture_add),
    ("T-fixture-flagcat", t_fixture_flagcat),
    ("D-tds", d_tds),
    ("D-tds-rows", d_tds_rows),
    ("B-new", b_new),
    ("B-write", b_write),
    ("B-rows", b_rows),
    ("M-new", m_new),
    ("F-new", f_new),
    ("F-write", f_write),
]
# Columns of MemoryStMan managers (not readable after the table closed).
MEMORY_COLUMNS = {"M-new": ["I", "A"]}


def run_case(pt, name, f, root, sources, stored=None):
    """Run one case writing `root/<name>` (on a copy of its source first).
    Returns (values, wall)."""
    path = Path(root) / name
    src = getattr(f, "source", None)
    if src is not None:
        copy_tree(sources[src], path)
    elif path.exists():
        shutil.rmtree(path)
    v = Values(stored)
    start = time.perf_counter()
    f(pt, str(path), v, src)
    return v.out, time.perf_counter() - start


def write_cases(out, sources, multifile):
    from casacore import tables as pt

    out = Path(out)
    (out / "casacore").mkdir(parents=True, exist_ok=True)
    (out / "values").mkdir(exist_ok=True)
    sources = dict(sources)
    sources.update({name: out / "casacore" / name for name, _ in CASES})
    record = []
    for name, f in CASES:
        if bool(getattr(f, "multifile", False)) != multifile:
            continue
        values, wall = run_case(pt, name, f, out / "casacore", sources)
        np.savez(
            out / "values" / f"{name}.npz",
            **{k: np.asarray(x) for k, x in values.items()},
        )
        record.append(
            {"name": name, "wall_s": wall, "source": getattr(f, "source", None)}
        )
        print(f"{name}: {wall:.3f} s", flush=True)
    target = out / ("cases-mf.json" if multifile else "cases.json")
    target.write_text(json.dumps(record, indent=1))


def step_write(out, fixture, luno):
    write_cases(out, {"FIXTURE": fixture, "LUNO": luno}, False)


def step_write_mf(out):
    write_cases(out, {}, True)


def dump_table(pt, path, skip=()):
    """Every cell (None: undefined) by column, keywords and info."""
    t = pt.table(path, ack=False)
    cells, meta = {}, {"nrows": t.nrows(), "info": t.info(), "columns": {}}
    meta["keywords"] = plain(t.getkeywords())
    for name in t.colnames():
        meta["columns"][name] = {"keywords": plain(t.getcolkeywords(name))}
        if name in skip:
            meta["columns"][name]["skipped"] = "MemoryStMan"
            continue
        for row in range(t.nrows()):
            if not t.iscelldefined(name, row):
                continue
            try:
                if t.isscalarcol(name):
                    value = t.getcol(name, row, 1)[0]
                else:
                    value = t.getcell(name, row)
            except Exception as e:  # noqa: BLE001 - recorded as unreadable
                meta["columns"][name]["error"] = str(e)
                break
            arr = np.asarray(value)
            if arr.dtype.kind in "USO":
                arr = np.asarray(arr, dtype=str)
            cells[f"{name}/{row}"] = arr
    t.close()
    return cells, meta


def step_readback(dump_dir, *pairs):
    from casacore import tables as pt

    dump_dir = Path(dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    for pair in pairs:
        label, path = pair.split("=", 1)
        case = label.split(".")[-1]
        tables = [Path(path)] + sorted(p.parent for p in Path(path).glob("*/table.dat"))
        for t in tables:
            sub = label if t == Path(path) else f"{label}.{t.name}"
            skip = MEMORY_COLUMNS.get(case, ()) if t == Path(path) else ()
            cells, meta = dump_table(pt, str(t), skip)
            np.savez(dump_dir / f"{sub}.npz", **cells)
            (dump_dir / f"{sub}.json").write_text(
                json.dumps(meta, indent=1, default=str)
            )


def step_read_column(out, table, column):
    """Read one column in this process and record the values or the error
    (casacore may abort afterwards, so the record is written first)."""
    from casacore import tables as pt

    t = pt.table(table, ack=False)
    try:
        value = t.getcol(column)
        result = {"values": plain(np.asarray(value))}
    except Exception as e:  # noqa: BLE001 - recorded
        result = {"error": str(e)}
    Path(out).write_text(json.dumps(result, indent=1, default=str))
    sys.stdout.flush()
    t.close()


def main(argv):
    steps = {
        "write": step_write,
        "write-mf": step_write_mf,
        "readback": step_readback,
        "read-column": step_read_column,
    }
    if len(argv) < 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    steps[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
