"""The oracle side of task E4 (research/e4-table-create.md).

python-casacore 3.8.1 in `rang-ms-reader:local` (NumPy 2.5.3):

    python examples/oracle_ms_create.py write <out> <luno.ms>
    python examples/oracle_ms_create.py readback <dump-dir> <label=table> ...

CASA 6.7.6.14 in `rang-o-casa:6.7.6.14` (`/opt/casa/bin/python`):

    python examples/oracle_ms_create.py casa-solve <run> <ms>
    python examples/oracle_ms_create.py casa-apply <run> <ms> <table> ...

`write` performs every frozen N, R and D case (the module-level `CASES`)
with python-casacore, each on a fresh path under `<out>/casacore/<case>`
(R cases on copies of casacore's own N outputs or of the LUNO export), one
close per session, and stores the values it used in
`<out>/values/<case>.npz` (seeded generator, seed 20261030) and the case
list with wall times in `<out>/cases.json`. The host checker
(`examples/check_ms_create.py`) replays the same functions with
`rang.core_ms_write` as `pt`, reading the stored values. `readback` dumps
every column cell by cell (definedness included), the keywords, the
column keywords and `table.info` of the given tables. `casa-solve` makes
the K, G, B and Df tables of the C cases; `casa-apply` runs `applycal`.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

SEED = 20261030
LOCK = {"lockoptions": "permanent"}


class Values:
    """Seeded values: generated and stored on the oracle side, read back in
    the same order on the core side (`stored` given)."""

    def __init__(self, stored=None):
        self.rng = np.random.default_rng(SEED)
        self.stored = stored
        self.out = {}

    def get(self, key, make):
        if self.stored is not None:
            value = self.stored[key]
        else:
            value = np.asarray(make(self.rng))
        self.out[key] = value
        return value


def strings(rng, n, low, high):
    return np.array(
        [
            "".join(chr(97 + int(c)) for c in rng.integers(0, 26, int(k)))
            for k in rng.integers(low, high, n)
        ],
        dtype=object,
    ).astype(str)


def numeric(rng, shape, dtype):
    dtype = np.dtype(dtype)
    if dtype == bool:
        return rng.random(shape) < 0.5
    if dtype.kind in "iu":
        info = np.iinfo(dtype)
        return rng.integers(
            max(info.min, -(2**31)), min(info.max, 2**31 - 1), shape, endpoint=True
        ).astype(dtype)
    if dtype.kind == "f":
        return rng.standard_normal(shape).astype(dtype)
    return (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(dtype)


# ---------------------------------------------------------------------------
# The frozen cases. Each is `f(pt, path, v, src)`: `pt` is
# `casacore.tables` or `rang.core_ms_write`, `path` the table to write,
# `v` the Values, `src` the input copied to `path` first (R cases) or None.

SCALARS = [
    ("B", False, "bool"),
    ("UC", 0, "uchar"),
    ("SH", 0, "short"),
    ("I", 0, "int"),
    ("UI", 0, "uint"),
    ("I64", 0, "int64"),
    ("F", 0.0, "float"),
    ("D", 0.0, "double"),
    ("C", 0j, "complex"),
    ("DC", 0j, "dcomplex"),
]
NUMPY = {
    "bool": "bool",
    "uchar": "uint8",
    "short": "int16",
    "int": "int32",
    "uint": "uint32",
    "int64": "int64",
    "float": "float32",
    "double": "float64",
    "complex": "complex64",
    "dcomplex": "complex128",
}


def n_scalars(pt, path, v, src):
    n = 100
    cols = [pt.makescacoldesc(name, value, valuetype=vt) for name, value, vt in SCALARS]
    cols.append(pt.makescacoldesc("S", ""))
    cols.append(pt.makescacoldesc("SF", "", maxlen=6))
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, ack=False, **LOCK)
    fill_scalars(t, v, 0, n)
    t.putkeyword("KD", 1.5)
    t.putkeyword("KI", 7)
    t.putkeyword("KS", "a keyword")
    t.putkeyword("KA", np.array([1.0, 2.0, 3.0]))
    t.putkeyword("KSA", np.array(["a", "bc"]))
    t.putkeyword("KR", {"x": 1, "y": "z"})
    t.putcolkeyword("D", "QuantumUnits", np.array(["s"]))
    t.putcolkeyword("D", "MEASINFO", {"type": "epoch", "Ref": "UTC"})
    t.putinfo({"type": "Test", "subType": "scalars", "readme": "line one\nline two"})
    t.close()


def n_arrays(pt, path, v, src):
    n = 60
    cols = [
        pt.makearrcoldesc("DD", 0.0, shape=[3], options=1),
        pt.makearrcoldesc("DB", False, shape=[7], options=1),
        pt.makearrcoldesc("FC", 0j, shape=[8, 4], valuetype="complex"),
        pt.makearrcoldesc("VF", 0.0, ndim=2, valuetype="float"),
        pt.makearrcoldesc("VB", False, ndim=1),
        pt.makearrcoldesc("VC", 0j, ndim=2, valuetype="complex"),
    ]
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, ack=False, **LOCK)
    t.putcol("DD", v.get("DD", lambda r: numeric(r, (n, 3), "float64")))
    t.putcol("DB", v.get("DB", lambda r: numeric(r, (n, 7), "bool")))
    t.putcol("FC", v.get("FC", lambda r: numeric(r, (n, 8, 4), "complex64")))
    for row in range(n):
        if row != 5:
            shape = (1 + row % 3, 2 + row % 4)
            t.putcell(
                "VF",
                row,
                v.get(f"VF{row}", lambda r: numeric(r, shape, "float32")),  # noqa: B023 - called at once by Values.get
            )
        t.putcell(
            "VB",
            row,
            v.get(f"VB{row}", lambda r: numeric(r, 3 + row % 11, "bool")),  # noqa: B023 - called at once by Values.get
        )
        t.putcell(
            "VC",
            row,
            v.get(f"VC{row}", lambda r: numeric(r, (2, 1 + row % 2), "complex64")),  # noqa: B023 - called at once by Values.get
        )
    t.putcell("VC", 7, v.get("VC7b", lambda r: numeric(r, (3, 3), "complex64")))
    t.close()


def n_strarr(pt, path, v, src):
    n = 80
    cols = [
        pt.makearrcoldesc("SV", "", ndim=1),
        pt.makearrcoldesc("SD", "", shape=[2], options=1),
    ]
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, ack=False, **LOCK)
    for row in range(n):
        if row == 3:
            continue
        if row % 10 == 0:
            cell = np.array([], dtype=str)
        elif row == 17:
            cell = v.get("SV17", lambda r: strings(r, 3, 3000, 3001))
        elif row % 7 == 0:
            cell = v.get(f"SV{row}", lambda r: strings(r, 4, 20, 60))
        else:
            cell = v.get(f"SV{row}", lambda r: strings(r, 1 + row % 3, 0, 12))  # noqa: B023 - called at once by Values.get
        t.putcell("SV", row, cell)
    t.putcol("SD", v.get("SD", lambda r: strings(r, 2 * n, 0, 15).reshape(n, 2)))
    for row in (1, 2, 22, 50):
        t.putcell(
            "SV",
            row,
            v.get(f"SVr{row}", lambda r: strings(r, 1 + row % 2, 0, 30)),  # noqa: B023 - called at once by Values.get
        )
    t.putcell("SD", 4, v.get("SDr4", lambda r: strings(r, 2, 30, 31)))
    t.close()


def n_tiled(pt, path, v, src):
    n = 50
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("DATA", 0j, shape=[16, 4], valuetype="complex"),
        pt.makearrcoldesc("WS", 0.0, shape=[16, 4], valuetype="float"),
        pt.makearrcoldesc("FLAG", False, shape=[16, 4]),
    ]
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TCS",
            "SPEC": {"DEFAULTTILESHAPE": np.array([4, 8, 8], np.int32)},
            "COLUMNS": ["DATA"],
        },
        "*2": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TSS",
            "SPEC": {"DEFAULTTILESHAPE": np.array([4, 8, 8], np.int32)},
            "COLUMNS": ["WS", "FLAG"],
        },
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dminfo, ack=False, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("DATA", v.get("DATA", lambda r: numeric(r, (n, 16, 4), "complex64")))
    t.putcol("WS", v.get("WS", lambda r: numeric(r, (n, 16, 4), "float32")))
    t.putcol("FLAG", v.get("FLAG", lambda r: numeric(r, (n, 16, 4), "bool")))
    t.close()


def n_buckets(pt, path, v, src):
    n = 3000
    cols = [
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("D", 0.0),
        pt.makescacoldesc("S", ""),
        pt.makescacoldesc("F", 0.0, valuetype="float"),
        pt.makescacoldesc("B", False),
    ]
    dminfo = {
        "*1": {
            "TYPE": "StandardStMan",
            "NAME": "SSM1K",
            "SPEC": {"BUCKETSIZE": 1024},
            "COLUMNS": ["I", "D", "S"],
        },
        "*2": {
            "TYPE": "StandardStMan",
            "NAME": "SSM100",
            "SPEC": {"BUCKETROWS": 100},
            "COLUMNS": ["F", "B"],
        },
    }
    t = pt.table(path, pt.maketabdesc(cols), nrow=n, dminfo=dminfo, ack=False, **LOCK)
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("D", v.get("D", lambda r: numeric(r, n, "float64")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 20))))
    t.putcol("F", v.get("F", lambda r: numeric(r, n, "float32")))
    t.putcol("B", v.get("B", lambda r: numeric(r, n, "bool")))
    t.close()


def r_add_new(pt, path, v, src):
    cols = [
        pt.makescacoldesc("B", False),
        pt.makescacoldesc("I", 0),
        pt.makescacoldesc("S", ""),
        pt.makearrcoldesc("DF", 0.0, shape=[2], options=1, valuetype="float"),
        pt.makearrcoldesc("FC", 0j, shape=[2, 3], valuetype="complex"),
        pt.makearrcoldesc("VD", 0.0, ndim=1),
        pt.makearrcoldesc("SV", "", ndim=1),
    ]
    t = pt.table(path, pt.maketabdesc(cols), nrow=10, ack=False, **LOCK)
    t.addrows(45)
    n = 55
    t.putcol("B", v.get("B", lambda r: numeric(r, n, "bool")))
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")))
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 20))))
    t.putcol("DF", v.get("DF", lambda r: numeric(r, (n, 2), "float32")))
    t.putcol("FC", v.get("FC", lambda r: numeric(r, (n, 2, 3), "complex64")))
    for row in range(n):
        t.putcell(
            "VD",
            row,
            v.get(f"VD{row}", lambda r: numeric(r, 1 + row % 5, "float64")),  # noqa: B023 - called at once by Values.get
        )
        t.putcell(
            "SV",
            row,
            v.get(f"SV{row}", lambda r: strings(r, 1 + row % 3, 0, 10)),  # noqa: B023 - called at once by Values.get
        )
    t.close()


def fill_scalars(t, v, old, n):
    for name, _, vt in SCALARS:
        t.putcol(name, v.get(name, lambda r, vt=vt: numeric(r, n, NUMPY[vt])), old, n)
    t.putcol("S", list(v.get("S", lambda r: strings(r, n, 0, 41))), old, n)
    t.putcol("SF", list(v.get("SF", lambda r: strings(r, n, 0, 7))), old, n)


def fill_arrays(t, v, old, n):
    t.putcol("DD", v.get("DD", lambda r: numeric(r, (n, 3), "float64")), old, n)
    t.putcol("DB", v.get("DB", lambda r: numeric(r, (n, 7), "bool")), old, n)
    t.putcol("FC", v.get("FC", lambda r: numeric(r, (n, 8, 4), "complex64")), old, n)
    for row in range(old, old + n):
        shape = (1 + row % 3, 2 + row % 4)
        t.putcell("VF", row, v.get(f"VF{row}", lambda r: numeric(r, shape, "float32")))  # noqa: B023 - called at once by Values.get
        t.putcell(
            "VB",
            row,
            v.get(f"VB{row}", lambda r: numeric(r, 3 + row % 11, "bool")),  # noqa: B023 - called at once by Values.get
        )
        t.putcell(
            "VC",
            row,
            v.get(f"VC{row}", lambda r: numeric(r, (2, 1 + row % 2), "complex64")),  # noqa: B023 - called at once by Values.get
        )


def fill_tiled(t, v, old, n):
    t.putcol("I", v.get("I", lambda r: numeric(r, n, "int32")), old, n)
    t.putcol(
        "DATA", v.get("DATA", lambda r: numeric(r, (n, 16, 4), "complex64")), old, n
    )
    t.putcol("WS", v.get("WS", lambda r: numeric(r, (n, 16, 4), "float32")), old, n)
    t.putcol("FLAG", v.get("FLAG", lambda r: numeric(r, (n, 16, 4), "bool")), old, n)


def fill_luno(t, v, old, n):
    shapes = {
        "FLAG": ((2048, 4), "bool"),
        "FLAG_ROW": ((), "bool"),
        "TIME": ((), "float64"),
        "ANTENNA1": ((), "int32"),
        "ANTENNA2": ((), "int32"),
        "DATA": ((2048, 4), "complex64"),
        "UVW": ((3,), "float64"),
    }
    for name, (cell, dtype) in shapes.items():
        t.putcol(name, v.get(name, lambda r: numeric(r, (n,) + cell, dtype)), old, n)  # noqa: B023 - called at once by Values.get


def r_add_existing(source, extra, fill):
    def f(pt, path, v, src):
        t = pt.table(path, readonly=False, ack=False, **LOCK)
        old = t.nrows()
        t.addrows(extra)
        fill(t, v, old, extra)
        t.close()

    f.source = source
    return f


def r_remove(rows):
    def f(pt, path, v, src):
        t = pt.table(path, readonly=False, ack=False, **LOCK)
        t.removerows(rows)
        t.close()

    return f


def r_remove_tiled(pt, path, v, src):
    t = pt.table(path, readonly=False, ack=False, **LOCK)
    try:
        t.removerows([0])
        refused = False
    except Exception as e:  # noqa: BLE001 - recorded, both sides must refuse
        refused = str(e)
    t.close()
    v.get("refused", lambda r: np.array(bool(refused)))
    if not refused:
        raise RuntimeError("removing rows of a tiled table was not refused")


r_remove_tiled.source = "N-tiled"


def d_plain(pt, path, v, src):
    pt.default_ms(path).close()


def d_source(pt, path, v, src):
    pt.default_ms(path).close()
    pt.default_ms_subtable("SOURCE", str(Path(path) / "SOURCE")).close()
    t = pt.table(path, readonly=False, ack=False, **LOCK)
    t.putkeyword("SOURCE", "Table: " + str(Path(path) / "SOURCE"))
    t.close()


def d_data(pt, path, v, src):
    desc = pt.maketabdesc(
        [pt.makearrcoldesc("DATA", 0j, shape=[64, 4], valuetype="complex")]
    )
    dminfo = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TiledData",
            "SPEC": {"DEFAULTTILESHAPE": np.array([4, 32, 8], np.int32)},
            "COLUMNS": ["DATA"],
        }
    }
    t = pt.default_ms(path, desc, dminfo)
    n = 20
    t.addrows(n)
    t.putcol("DATA", v.get("DATA", lambda r: numeric(r, (n, 64, 4), "complex64")))
    t.putcol("TIME", v.get("TIME", lambda r: 5e9 + np.arange(n, dtype=np.float64)))
    t.putcol("ANTENNA1", v.get("ANTENNA1", lambda r: np.zeros(n, np.int32)))
    t.putcol(
        "ANTENNA2", v.get("ANTENNA2", lambda r: (np.arange(n) % 3 + 1).astype(np.int32))
    )
    t.putcol("UVW", v.get("UVW", lambda r: numeric(r, (n, 3), "float64")))
    t.putcol("FLAG", v.get("FLAG", lambda r: numeric(r, (n, 64, 4), "bool")))
    t.close()
    a = pt.table(str(Path(path) / "ANTENNA"), readonly=False, ack=False, **LOCK)
    a.addrows(4)
    a.putcol("NAME", ["m000", "m001", "m002", "m003"])
    a.putcol("STATION", ["M000", "M001", "M002", "M003"])
    a.putcol(
        "POSITION", v.get("POSITION", lambda r: 5e6 + numeric(r, (4, 3), "float64"))
    )
    a.putcol("DISH_DIAMETER", np.full(4, 13.5))
    a.close()


r_add_scalars = r_add_existing("N-scalars", 37, fill_scalars)
r_add_arrays = r_add_existing("N-arrays", 37, fill_arrays)
r_add_tiled = r_add_existing("N-tiled", 20, fill_tiled)
r_add_luno = r_add_existing("LUNO", 120, fill_luno)
r_rm_scalars = r_remove([0, 5, 6, 7, 99])
r_rm_scalars.source = "N-scalars"
r_rm_strarr = r_remove(list(range(10, 40)))
r_rm_strarr.source = "N-strarr"
# The BUCKETSIZE-1024 manager holds 42 rows per bucket (I, D and S take
# 24 bytes a row): rows 0-41 are its first data bucket.
r_rm_buckets = r_remove(list(range(42)))
r_rm_buckets.source = "N-buckets"
r_rm_luno = r_remove(list(range(100)))
r_rm_luno.source = "LUNO"

CASES = [
    ("N-scalars", n_scalars),
    ("N-arrays", n_arrays),
    ("N-strarr", n_strarr),
    ("N-tiled", n_tiled),
    ("N-buckets", n_buckets),
    ("R-add-new", r_add_new),
    ("R-add-scalars", r_add_scalars),
    ("R-add-arrays", r_add_arrays),
    ("R-add-tiled", r_add_tiled),
    ("R-add-luno", r_add_luno),
    ("R-remove-scalars", r_rm_scalars),
    ("R-remove-strarr", r_rm_strarr),
    ("R-remove-buckets", r_rm_buckets),
    ("R-remove-luno", r_rm_luno),
    ("R-remove-tiled", r_remove_tiled),
    ("D-plain", d_plain),
    ("D-source", d_source),
    ("D-data", d_data),
]


def copy_tree(src, dst):
    if Path(dst).exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def run_case(pt, name, f, root, sources, stored=None):
    """Run one case writing `root/<name>`; R cases first copy their source
    (`sources[label]`). Returns (values, wall)."""
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


def step_write(out, luno):
    from casacore import tables as pt

    out = Path(out)
    (out / "casacore").mkdir(parents=True, exist_ok=True)
    (out / "values").mkdir(exist_ok=True)
    sources = {"LUNO": luno}
    sources.update({name: out / "casacore" / name for name, _ in CASES})
    record = []
    for name, f in CASES:
        values, wall = run_case(pt, name, f, out / "casacore", sources)
        np.savez(
            out / "values" / f"{name}.npz",
            **{k: np.asarray(x) for k, x in values.items()},
        )
        record.append(
            {"name": name, "wall_s": wall, "source": getattr(f, "source", None)}
        )
        print(f"{name}: {wall:.3f} s", flush=True)
    (out / "cases.json").write_text(json.dumps(record, indent=1))


# ---------------------------------------------------------------------------
# Read-back dumps (python-casacore).


def plain(value):
    if isinstance(value, dict):
        return {k: plain(x) for k, x in value.items()}
    if isinstance(value, np.ndarray):
        return {
            "array": value.tolist(),
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
    if isinstance(value, (np.generic,)):
        return (
            value.item()
            if not isinstance(value, np.complexfloating)
            else [value.real, value.imag]
        )
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, str) and value.startswith("Table: "):
        return "Table: " + Path(value[7:]).name
    return value


def dump_table(pt, path):
    """Every cell (or None when undefined) by column, keywords and info."""
    t = pt.table(path, ack=False)
    cells, meta = {}, {"nrows": t.nrows(), "info": t.info(), "columns": {}}
    meta["keywords"] = plain(t.getkeywords())
    for name in t.colnames():
        meta["columns"][name] = {"keywords": plain(t.getcolkeywords(name))}
        for row in range(t.nrows()):
            if not t.iscelldefined(name, row):
                continue
            try:
                # Scalars through getcol, which keeps the column type
                # (getcell returns Python ints and floats).
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
        tables = [Path(path)] + sorted(p.parent for p in Path(path).glob("*/table.dat"))
        for t in tables:
            sub = label if t == Path(path) else f"{label}.{t.name}"
            cells, meta = dump_table(pt, str(t))
            np.savez(dump_dir / f"{sub}.npz", **cells)
            (dump_dir / f"{sub}.json").write_text(
                json.dumps(meta, indent=1, default=str)
            )


# ---------------------------------------------------------------------------
# CASA: the C cases' tables and applycal (`rang-o-casa:6.7.6.14`).

REFANT = "m000"
FIELD = "J1939-6342"  # O-CASA arm C: the 1934-638 field


def step_casa_solve(run, ms):
    from casatasks import bandpass, gaincal, polcal

    run = Path(run)
    field = FIELD
    log = {}
    tables = {k: str(run / f"x.{k}") for k in ("K", "G", "B", "Df")}

    def timed(name, task, **params):
        start = time.perf_counter()
        task(**params)
        log[name] = time.perf_counter() - start

    common = {"vis": ms, "field": field, "refant": REFANT, "minblperant": 3}
    timed(
        "gaincal_K",
        gaincal,
        caltable=tables["K"],
        solint="120s",
        combine="",
        gaintype="K",
        **common,
    )
    timed(
        "gaincal_G",
        gaincal,
        caltable=tables["G"],
        solint="120s",
        combine="",
        gaintype="G",
        calmode="ap",
        gaintable=[tables["K"]],
        interp=["linear"],
        **common,
    )
    timed(
        "bandpass_B",
        bandpass,
        caltable=tables["B"],
        solint="inf",
        combine="scan",
        bandtype="B",
        solnorm=False,
        fillgaps=70,
        gaintable=[tables["K"], tables["G"]],
        interp=["linear", "linear"],
        **common,
    )
    timed(
        "polcal_Df",
        polcal,
        caltable=tables["Df"],
        solint="inf",
        combine="scan",
        poltype="Df",
        gaintable=[tables["K"], tables["G"], tables["B"]],
        interp=["linear", "linear", "linear"],
        **common,
    )
    (run / "casa-solve.json").write_text(json.dumps(log, indent=1))


def step_casa_apply(run, ms, *tables):
    from casatasks import applycal

    start = time.perf_counter()
    applycal(
        vis=ms,
        field=FIELD,
        applymode="calflag",
        gaintable=list(tables),
        interp=["linear"] * len(tables),
        calwt=[False],
        gainfield=["nearest"] * len(tables),
        parang=False,
        flagbackup=False,
    )
    wall = time.perf_counter() - start
    with open(Path(run) / "casa-apply.json", "a") as f:
        f.write(json.dumps({"ms": ms, "tables": list(tables), "wall_s": wall}) + "\n")


def main(argv):
    steps = {
        "write": step_write,
        "readback": step_readback,
        "casa-solve": step_casa_solve,
        "casa-apply": step_casa_apply,
    }
    if len(argv) < 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    steps[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
