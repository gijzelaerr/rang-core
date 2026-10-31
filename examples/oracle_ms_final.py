"""The oracle side of task E6 (research/e6-table-writer-final.md).

python-casacore 3.8.1 in `rang-ms-reader:local` (NumPy 2.5.3):

    python examples/oracle_ms_final.py write <out>
    CASARCFILES=<rc> python examples/oracle_ms_final.py write-mf <out> <block>
    python examples/oracle_ms_final.py readback <dump-dir> <label=table> ...

and on any Python with NumPy (the host):

    python examples/oracle_ms_final.py prepare <out>

`write` performs the frozen O-py cases but the MultiFile ones (`CASES`
with `oracle == "py"`) with python-casacore, each on a fresh path under
`<out>/casacore/<case>` (a case with a `source` on a copy of casacore's own
output of that case), one close per session, and stores the values it used
in `<out>/values/<case>.npz` (seeded generator, seed 20261031) and the case
list with wall times in `<out>/cases.json`. `write-mf` does the MultiFile
cases of one block size (`table.storage.blocksize` of the aipsrc file
named by `CASARCFILES`; 0 for casacore's default). `prepare` makes the
values of the O-cpp cases (TiledDataStMan hypercubes, X-371, H-mfh5) by
running the case functions without a table system, and writes them as
`<out>/values/<case>.npz` and as raw little-endian files
`<out>/cpp/<case>/<key>.bin` for `tools/oracles/casacore-cpp/oracle.cc`.
No case reads a table inside its write session. The host checker
(`examples/check_ms_final.py`) replays the same functions with
`rang.core_ms_write` as `pt`. `readback` is E5's.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import oracle_ms_create
import oracle_ms_rest
from oracle_ms_create import copy_tree, numeric, strings
from oracle_ms_rest import runs

SEED = 20261031
LOCK = {"lockoptions": "permanent", "ack": False}


class Values(oracle_ms_create.Values):
    """E5's seeded values with E6's seed."""

    def __init__(self, stored=None):
        super().__init__(stored)
        self.rng = np.random.default_rng(SEED)


def is_core(pt):
    return hasattr(pt, "create_table")


def mf_kw(pt, block):
    """The core is given the MultiFile block size; casacore takes it from
    aipsrc."""
    return {"multifile": block or True} if is_core(pt) else {}


def run_values(v, key, n, alphabet):
    a = v.get(key + ".alphabet", alphabet)
    idx = v.get(key + ".runs", lambda r: runs(r, n, len(a)))
    return a[idx]


def tiled(kind, name, columns, tile=None):
    spec = {} if tile is None else {"DEFAULTTILESHAPE": np.array(tile, np.int32)}
    return {"TYPE": kind, "NAME": name, "SPEC": spec, "COLUMNS": columns}


def ism(name, columns, **spec):
    return {"TYPE": "IncrementalStMan", "NAME": name, "SPEC": spec, "COLUMNS": columns}


def ssm(name, columns, **spec):
    return {"TYPE": "StandardStMan", "NAME": name, "SPEC": spec, "COLUMNS": columns}


def cell(v, key, shape, dtype):
    return v.get(key, lambda r: numeric(r, shape, dtype))


# ---------------------------------------------------------------------------
# TiledDataStMan (O-cpp: tools/oracles/casacore-cpp/oracle.cc performs the
# same calls; keep the two in step).


def tds_desc(pt):
    cols = [
        pt.makearrcoldesc("DATA", 0.0, shape=[8, 4], valuetype="float"),
        pt.makearrcoldesc("FLAG", False, shape=[8, 4]),
        pt.makearrcoldesc("FREQ", 0.0, shape=[4]),
        pt.makescacoldesc("TIME", 0.0),
        pt.makescacoldesc("ID", 0),
    ]
    desc = pt.maketabdesc(cols)
    pt.tabledefinehypercolumn(desc, "TDS", 3, ["DATA", "FLAG"], ["FREQ", "", "TIME"], ["ID"])
    return desc


TDS_DM = {
    "*1": {
        "TYPE": "TiledDataStMan",
        "NAME": "TDS",
        "SPEC": {},
        "COLUMNS": ["DATA", "FLAG", "FREQ", "TIME", "ID"],
    }
}


def d_cubes(pt, path, v, src, endian="little"):
    t = pt.table(path, tds_desc(pt), nrow=11, dminfo=TDS_DM, endian=endian, **LOCK)
    t.addhypercube(
        "TDS",
        [4, 8, 3],
        [4, 4, 2],
        {
            "ID": np.int32(7),
            "FREQ": cell(v, "FREQ.a", 4, "float64"),
            "TIME": cell(v, "TIME.a", 3, "float64"),
        },
    )
    t.addhypercube("TDS", [4, 8, 0], [2, 8, 2], {"ID": np.int32(9)})
    t.extendhypercube(
        "TDS", 2, {"ID": np.int32(9), "TIME": cell(v, "TIME.b", 2, "float64")}
    )
    t.extendhypercube("TDS", 4, {"ID": np.int32(9)})
    t.addhypercube(
        "TDS",
        [4, 8, 2],
        [4, 8, 1],
        {
            "ID": np.int32(11),
            "FREQ": cell(v, "FREQ.c", 4, "float64"),
            "TIME": cell(v, "TIME.c", 2, "float64"),
        },
    )
    t.putcol("DATA", cell(v, "DATA", (11, 8, 4), "float32"))
    t.putcol("FLAG", cell(v, "FLAG", (11, 8, 4), "bool"))
    t.putcell("TIME", 4, float(cell(v, "TIME4", (), "float64")))
    t.putcell("FREQ", 3, cell(v, "FREQ3", 4, "float64"))
    t.close()


def d_reopen(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    t.addrows(4)
    t.extendhypercube(
        "TDS", 4, {"ID": np.int32(9), "TIME": cell(v, "TIME.d", 4, "float64")}
    )
    t.putcol("DATA", cell(v, "DATA", (4, 8, 4), "float32"), 11, 4)
    t.putcol("FLAG", cell(v, "FLAG", (4, 8, 4), "bool"), 11, 4)
    t.close()


d_reopen.source = "D-cubes"


def d_multiaxis(pt, path, v, src):
    cols = [
        pt.makearrcoldesc("DATA", 0j, ndim=2, valuetype="complex"),
        pt.makescacoldesc("X", 0.0),
        pt.makescacoldesc("TIME", 0.0),
    ]
    desc = pt.maketabdesc(cols)
    pt.tabledefinehypercolumn(desc, "TDM", 4, ["DATA"], ["", "", "X", "TIME"])
    dm = {
        "*1": {
            "TYPE": "TiledDataStMan",
            "NAME": "TDM",
            "SPEC": {},
            "COLUMNS": ["DATA", "X", "TIME"],
        }
    }
    t = pt.table(path, desc, nrow=0, dminfo=dm, **LOCK)
    t.addrows(9)
    t.addhypercube("TDM", [4, 2, 3, 0], [4, 2, 2, 2], {"X": cell(v, "X", 3, "float64")})
    t.extendhypercube("TDM", 3, {"TIME": cell(v, "TIME", 3, "float64")})
    t.putcol("DATA", cell(v, "DATA", (9, 2, 4), "complex64"))
    t.putcell("X", 4, float(cell(v, "X4", (), "float64")))
    t.close()


def d_be(pt, path, v, src):
    d_cubes(pt, path, v, src, endian="big")


# ---------------------------------------------------------------------------
# TiledCellStMan (O-py; X-371 by O-cpp).


def c_var(pt, path, v, src, endian="little"):
    cols = [
        pt.makearrcoldesc("D", 0.0, ndim=2),
        pt.makearrcoldesc("F", 0.0, ndim=2, valuetype="float"),
    ]
    dm = {"*1": tiled("TiledCellStMan", "TCS", ["D", "F"], [4, 4])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=6, dminfo=dm, endian=endian, **LOCK)
    t.putcell("D", 0, cell(v, "D0", (3, 4), "float64"))
    t.putcell("F", 0, cell(v, "F0", (3, 4), "float32"))
    t.putcell("D", 2, cell(v, "D2", (5, 8), "float64"))
    t.putcell("D", 3, cell(v, "D3", (2, 2), "float64"))
    t.putcell("D", 0, cell(v, "D0b", (2, 3), "float64"))
    t.addrows(2)
    t.putcell("D", 7, cell(v, "D7", (2, 2), "float64"))
    t.putcell("F", 7, cell(v, "F7", (2, 2), "float32"))
    t.close()


def c_fixed(pt, path, v, src):
    cols = [pt.makearrcoldesc("D", 0.0, shape=[3, 5])]
    dm = {"*1": tiled("TiledCellStMan", "TCS", ["D"], [2, 2])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=4, dminfo=dm, **LOCK)
    t.putcol("D", cell(v, "D", (4, 3, 5), "float64"))
    t.addrows(3)
    # Deviation (research/e6-table-writer-final.md): the frozen `putcol` of
    # rows 4-6 makes casacore raise (`TSMShape::offset - shapes do not
    # conform`: `accessColumnCells` takes a row axis a TiledCellStMan cube
    # does not have), so the new rows are put one by one.
    new = cell(v, "D.new", (3, 3, 5), "float64")
    for k in range(3):
        t.putcell("D", 4 + k, new[k])
    t.close()


def c_write(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    t.putcell("D", 2, cell(v, "D2", (5, 8), "float64"))
    t.putcell("D", 4, cell(v, "D4", (6, 6), "float64"))
    t.putcell("D", 3, cell(v, "D3", (4, 4), "float64"))
    t.addrows(1)
    t.putcell("D", 8, cell(v, "D8", (1, 7), "float64"))
    t.close()


c_write.source = "C-var"


def c_be(pt, path, v, src):
    c_var(pt, path, v, src, endian="big")


def c_notile(pt, path, v, src):
    cols = [pt.makearrcoldesc("D", 0.0, ndim=2)]
    dm = {"*1": tiled("TiledCellStMan", "TCS", ["D"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=3, dminfo=dm, **LOCK)
    t.putcell("D", 1, cell(v, "D1", (20, 20), "float64"))
    t.putcell("D", 2, cell(v, "D2", (200, 300), "float64"))
    t.close()


# ---------------------------------------------------------------------------
# IncrementalStMan string arrays (O-py).


def str_cell(v, key, shape):
    n = int(np.prod(shape))
    return v.get(key, lambda r: strings(r, n, 0, 13).reshape(shape))


def is_arrays(pt, path, v, src):
    n = 300
    cols = [
        pt.makescacoldesc("K", 0),
        pt.makearrcoldesc("SV", "", ndim=1),
        pt.makearrcoldesc("SF", "", shape=[2, 2]),
    ]
    dm = {"*1": ism("ISM", ["K", "SV", "SF"], BUCKETSIZE=2048)}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK)
    t.putcol("K", run_values(v, "K", n, lambda r: numeric(r, 5, "int32")))
    sf = run_values(v, "SF", n, lambda r: strings(r, 20, 0, 13).reshape(5, 2, 2))
    t.putcol("SF", sf)
    for row in range(0, n, 3):
        t.putcell("SV", row, str_cell(v, f"SV{row}", (1 + row % 4,)))
    for row in (10, 11, 50, 51, 52, 120, 200, 201):
        t.putcell("SF", row, str_cell(v, f"SF{row}.edit", (2, 2)))
    for row in (3, 4, 30, 99):
        t.putcell("SV", row, str_cell(v, f"SV{row}.edit", (2,)))
    t.addrows(20)
    t.putcol("SF", str_cell(v, "SF.new", (20, 2, 2)), n, 20)
    for row in (300, 310):
        t.putcell("SV", row, str_cell(v, f"SV{row}", (3,)))
    t.removerows([0, 5] + list(range(150, 200)))
    t.close()


def is_big(pt, path, v, src):
    cols = [pt.makearrcoldesc("SV", "", ndim=1)]
    dm = {"*1": ism("ISM", ["SV"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=10, dminfo=dm, **LOCK)
    for key, row, count in (
        ("SV0", 0, 5000),
        ("SV1", 1, 9000),
        ("SV2", 2, 3),
        ("SV0b", 0, 4097),
        ("SV5", 5, 4096),
    ):
        t.putcell("SV", row, str_cell(v, key, (count,)))
    t.close()


# ---------------------------------------------------------------------------
# Tiled managers without a default tile shape (O-py).


def t_notile(pt, path, v, src):
    cols = [pt.makearrcoldesc("D", 0.0, ndim=2)]
    dm = {"*1": tiled("TiledShapeStMan", "TSS", ["D"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=4, dminfo=dm, **LOCK)
    for row, shape in enumerate([(3, 4), (20, 20), (3, 4), (1, 1000)]):
        t.putcell("D", row, cell(v, f"D{row}", shape, "float64"))
    t.addrows(2)
    t.putcell("D", 5, cell(v, "D5", (7, 9), "float64"))
    t.close()


def t_notile_fixed(pt, path, v, src):
    cols = [pt.makearrcoldesc("F", 0.0, shape=[16, 4], valuetype="float")]
    dm = {"*1": tiled("TiledShapeStMan", "TSS", ["F"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=50, dminfo=dm, **LOCK)
    t.putcol("F", cell(v, "F", (50, 16, 4), "float32"))
    t.close()


def t_notile_column(pt, path, v, src):
    cols = [pt.makearrcoldesc("D", 0.0, shape=[16, 4])]
    dm = {"*1": tiled("TiledColumnStMan", "TCOL", ["D"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=50, dminfo=dm, **LOCK)
    t.putcol("D", cell(v, "D", (50, 16, 4), "float64"))
    t.addrows(30)
    t.putcol("D", cell(v, "D.new", (30, 16, 4), "float64"), 50, 30)
    t.close()


# ---------------------------------------------------------------------------
# MultiFile (O-py; the block size from aipsrc).


def f_multi(pt, path, v, src):
    n = 2000
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("D", 0.0),
        pt.makescacoldesc("S", ""),
        pt.makescacoldesc("L", 0, valuetype="int64"),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makescacoldesc("M", 0),
    ]
    dm = {
        "*1": ssm("A", ["I", "D", "S"], BUCKETSIZE=512, PERSCACHESIZE=2),
        "*2": ssm("B", ["L", "V"], BUCKETSIZE=1024, PERSCACHESIZE=2),
        "*3": ism("M", ["M"], BUCKETSIZE=512),
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK, **mf_kw(pt, 4096))
    t.putcol("I", cell(v, "I", n, "int32"))
    t.putcol("L", cell(v, "L", n, "int64"))
    t.putcol("D", cell(v, "D", n, "float64"))
    for row in range(0, n, 3):
        t.putcell("V", row, cell(v, f"V{row}", 1 + row % 7, "float64"))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 13))))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 5, "int32")))
    t.flush()
    t.addrows(1000)
    t.putcol("I", cell(v, "I.new", 1000, "int32"), n, 1000)
    t.putcol("L", cell(v, "L.new", 1000, "int64"), n, 1000)
    t.putcol("D", cell(v, "D.new", 1000, "float64"), n, 1000)
    t.putcol("M", run_values(v, "M.new", 1000, lambda r: numeric(r, 5, "int32")), n, 1000)
    for row in range(n, n + 1000, 5):
        t.putcell("V", row, cell(v, f"V{row}", 1 + row % 7, "float64"))
    t.close()


f_multi.multifile = 4096


def f_multi_write(pt, path, v, src):
    t = pt.table(path, readonly=False, **LOCK)
    t.putcol("I", cell(v, "I", 500, "int32"), 0, 500)
    t.putcell("V", 3, cell(v, "V3", 1 + 3 % 7, "float64"))
    t.close()


f_multi_write.source = "F-multi"
f_multi_write.multifile = 4096


def f_cont(pt, path, v, src):
    n = 400
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makescacoldesc("S", ""),
        pt.makearrcoldesc("T", 0.0, ndim=1, valuetype="float"),
        pt.makescacoldesc("M", 0),
    ]
    dm = {
        "*1": ssm("A", ["I", "V", "S"], BUCKETSIZE=512, PERSCACHESIZE=2),
        "*2": tiled("TiledShapeStMan", "T", ["T"], [8, 4]),
        "*3": ism("M", ["M"], BUCKETSIZE=512),
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK, **mf_kw(pt, 512))
    t.putcol("I", cell(v, "I", n, "int32"))
    for row in range(n):
        t.putcell("V", row, cell(v, f"V{row}", 1 + row % 9, "float64"))
        if row % 3 == 0:
            t.putcell("T", row, cell(v, f"T{row}", 1 + row % 8, "float32"))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 5, "int32")))
    t.flush()
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 13))))
    t.addrows(100)
    t.putcol("I", cell(v, "I.new", 100, "int32"), n, 100)
    for row in range(n, n + 100):
        t.putcell("T", row, cell(v, f"T{row}", 1 + row % 13, "float32"))
    t.flush()
    t.putcol("M", run_values(v, "M.all", n + 100, lambda r: numeric(r, 5, "int32")))
    t.close()


f_cont.multifile = 512


def f_free(pt, path, v, src):
    n = 200
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("V", 0.0, ndim=1),
        pt.makescacoldesc("M", 0),
    ]
    dm = {"*1": ssm("A", ["I", "V"], BUCKETSIZE=512), "*2": ism("M", ["M"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK, **mf_kw(pt, 1024))
    t.putcol("I", cell(v, "I", n, "int32"))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 5, "int32")))
    for row in range(n):
        t.putcell("V", row, cell(v, f"V{row}", 1 + row % 5, "float64"))
    t.flush()
    t.removerows(list(range(n)))
    t.addrows(50)
    t.putcol("I", cell(v, "I.new", 50, "int32"))
    t.putcol("M", run_values(v, "M.new", 50, lambda r: numeric(r, 5, "int32")))
    for row in range(50):
        t.putcell("V", row, cell(v, f"V{row}.new", 1 + row % 5, "float64"))
    t.close()


f_free.multifile = 1024


def f_default(pt, path, v, src):
    n = 9000
    cols = [
        pt.makearrcoldesc("W", 0.0, shape=[64], options=1),
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("M", 0),
    ]
    dm = {"*1": ism("M", ["M"])}
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dm, **LOCK, **mf_kw(pt, 0))
    t.putcol("W", cell(v, "W", (n, 64), "float64"))
    t.putcol("I", cell(v, "I", n, "int32"))
    t.putcol("M", run_values(v, "M", n, lambda r: numeric(r, 5, "int32")))
    t.addrows(1000)
    t.putcol("W", cell(v, "W.new", (1000, 64), "float64"), n, 1000)
    t.putcol("I", cell(v, "I.new", 1000, "int32"), n, 1000)
    t.close()


f_default.multifile = 0  # casacore's default block size (4 MiB)


# ---------------------------------------------------------------------------
# W4-4 (absorbed by E6, added 2026-10-31 after the protocol was frozen): 2-D
# string and numeric array keywords (research/e6-table-writer-final.md).


def k_arrays(pt, path, v, src):
    cols = [pt.makescacoldesc("I", 0)]
    t = pt.table(path, pt.maketabdesc(cols), nrow=2, **LOCK)
    t.putcol("I", cell(v, "I", 2, "int32"))
    t.putkeyword("S23", np.array([["a", "b", "c"], ["d", "e", "f"]]))
    t.putkeyword("D23", cell(v, "D23", (2, 3), "float64"))
    t.putkeyword("I32", cell(v, "I32", (3, 2), "int32"))
    t.putkeyword("S222", str_cell(v, "S222", (2, 2, 2)))
    t.putcolkeyword("I", "CS", np.array([["x", "yy"], ["zzz", ""], ["p", "q"]]))
    t.putcolkeyword("I", "CF", cell(v, "CF", (2, 4), "float32"))
    t.close()


# ---------------------------------------------------------------------------
# Inputs of the refusals (O-cpp).


def h_mfh5(pt, path, v, src):
    """H-mfh5: a 20-row MultiHDF5 table (only casacore makes it)."""
    cell(v, "I", 20, "int32")


for f in (d_cubes, d_reopen, d_multiaxis, d_be, h_mfh5):
    f.oracle = "cpp"

CASES = [
    ("D-cubes", d_cubes),
    ("D-reopen", d_reopen),
    ("D-multiaxis", d_multiaxis),
    ("D-be", d_be),
    ("C-var", c_var),
    ("C-fixed", c_fixed),
    ("C-write", c_write),
    ("C-be", c_be),
    ("C-notile", c_notile),
    ("X-371", c_var),
    ("IS-arrays", is_arrays),
    ("IS-big", is_big),
    ("T-notile", t_notile),
    ("T-notile-fixed", t_notile_fixed),
    ("T-notile-column", t_notile_column),
    ("F-multi", f_multi),
    ("F-multi-write", f_multi_write),
    ("F-cont", f_cont),
    ("F-free", f_free),
    ("F-default", f_default),
    ("K-arrays", k_arrays),
]
# X-371 is C-var's sequence by casacore 3.7.1.
CPP_CASES = {"D-cubes", "D-reopen", "D-multiaxis", "D-be", "X-371"}
INPUTS = [("H-mfh5", h_mfh5)]


def oracle_of(name, f):
    return "cpp" if name in CPP_CASES else "py"


def run_case(pt, name, f, root, sources, stored=None):
    """Run one case writing `root/<name>` (on a copy of its source first).
    Returns (values, wall)."""
    path = Path(root) / name
    src = getattr(f, "source", None)
    if src is not None:
        copy_tree(sources[src], path)
    elif path.exists():
        import shutil

        shutil.rmtree(path)
    v = Values(stored)
    start = time.perf_counter()
    f(pt, str(path), v, src)
    return v.out, time.perf_counter() - start


def write_cases(out, block):
    from casacore import tables as pt

    out = Path(out)
    (out / "casacore").mkdir(parents=True, exist_ok=True)
    (out / "values").mkdir(exist_ok=True)
    sources = {name: out / "casacore" / name for name, _ in CASES}
    record = []
    for name, f in CASES:
        if oracle_of(name, f) != "py" or getattr(f, "multifile", None) != block:
            continue
        values, wall = run_case(pt, name, f, out / "casacore", sources)
        np.savez(
            out / "values" / f"{name}.npz",
            **{k: np.asarray(x) for k, x in values.items()},
        )
        record.append({"name": name, "wall_s": wall, "source": getattr(f, "source", None)})
        print(f"{name}: {wall:.3f} s", flush=True)
    label = "" if block is None else f"-mf{block}"
    (out / f"cases{label}.json").write_text(json.dumps(record, indent=1))


def step_write(out):
    write_cases(out, None)


def step_write_mf(out, block):
    write_cases(out, int(block))


class _Null:
    """A table system that does nothing (values only)."""

    def __getattr__(self, name):
        return self

    def __call__(self, *args, **kwargs):
        return self


def step_prepare(out):
    """Values of the O-cpp cases: npz for the core, raw files for C++."""
    out = Path(out)
    (out / "values").mkdir(parents=True, exist_ok=True)
    null = _Null()
    for name, f in CASES + INPUTS:
        if name not in CPP_CASES and (name, f) not in INPUTS:
            continue
        v = Values()
        f(null, "", v, None)
        np.savez(out / "values" / f"{name}.npz", **{k: np.asarray(x) for k, x in v.out.items()})
        d = out / "cpp" / name
        d.mkdir(parents=True, exist_ok=True)
        for k, x in v.out.items():
            a = np.ascontiguousarray(x)
            a.astype(a.dtype.newbyteorder("<")).tofile(d / f"{k}.bin")
        print(f"{name}: {len(v.out)} values", flush=True)


def main(argv):
    steps = {
        "write": step_write,
        "write-mf": step_write_mf,
        "prepare": step_prepare,
        "readback": oracle_ms_rest.step_readback,
    }
    if len(argv) < 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    steps[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
