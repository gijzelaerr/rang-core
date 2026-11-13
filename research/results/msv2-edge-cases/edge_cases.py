# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: BLE001  (an oracle harness: every failure is recorded, never raised)
"""MSv2 edge cases: ra-ng's reader against arcae and xarray-ms
(research/msv2-edge-cases.md; the case set and the comparison are frozen there).

    python edge_cases.py make DIR            # WSL, python-casacore: write the cases
    python edge_cases.py dump-casacore DIR   # WSL, python-casacore (triage only)
    python edge_cases.py dump-arcae DIR      # WSL, arcae (the oracle)
    python edge_cases.py dump-xms DIR        # WSL, xarray-ms on the MSs
    python edge_cases.py check DIR OUT.json  # Windows, rang.core_ms

python-casacore and arcae run in separate processes (arcae's casacore and
python-casacore's must not share one). Dumps are pickles in DIR/dumps, written
and read only by this script.
"""

import json
import pickle
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np

SEED = 20261113
UNWRITTEN = ("has no array", "has no tiled array")
UNIX_MJD = 3506716800.0  # 1970-01-01 in MJD seconds

# ---------------------------------------------------------------------------
# make (python-casacore)


def _arr(name, value, **kw):
    import casacore.tables as pt

    return pt.makearrcoldesc(name, value, **kw)


def _sca(name, value, **kw):
    import casacore.tables as pt

    return pt.makescacoldesc(name, value, **kw)


def _cell(rng, dtype, shape):
    dtype = np.dtype(dtype)
    if dtype == np.bool_:
        return rng.random(shape) > 0.5
    if dtype.kind == "c":
        return (rng.standard_normal(shape) + 1j * rng.standard_normal(shape)).astype(
            dtype
        )
    if dtype.kind == "i":
        return rng.integers(-1000, 1000, shape).astype(dtype)
    return rng.standard_normal(shape).astype(dtype)


def _table(path, cols, nrow, groups=None, **kw):
    import casacore.tables as pt

    desc = pt.maketabdesc(cols)
    dminfo = pt.makedminfo(desc, groups or {})
    return pt.table(str(path), desc, nrow=nrow, dminfo=dminfo, ack=False, **kw)


def _put(t, col, rows, cells):
    for r, c in zip(rows, cells):
        t.putcell(col, int(r), c)


def make_tables(root, rng):
    root.mkdir(parents=True, exist_ok=True)
    tsg = "TiledShapeStMan"

    # t01: StandardStMan indirect, variable shape, partly written.
    t = _table(
        root / "t01-ssm-var-partial",
        [
            _arr("F32", 0.0, ndim=2, valuetype="float"),
            _arr("C64", 0j, ndim=2, valuetype="complex"),
            _arr("I32", 0, ndim=1, valuetype="int"),
        ],
        8,
    )
    for col, dt in (("F32", "f4"), ("C64", "c8")):
        _put(t, col, [0, 1], [_cell(rng, dt, (4, 2)) for _ in range(2)])
        _put(t, col, [3, 4], [_cell(rng, dt, (8, 2)) for _ in range(2)])
    _put(t, "I32", [0, 2, 3, 7], [_cell(rng, "i4", (n,)) for n in (3, 3, 5, 0)])
    t.close()

    # t02: StandardStMan fixed shape, direct and indirect, odd rows unwritten.
    t = _table(
        root / "t02-ssm-fixed-unwritten",
        [
            _arr("DIRECT", 0.0, shape=[4, 2], valuetype="float", options=5),
            _arr("INDIRECT", 0.0, shape=[4, 2], valuetype="float", options=4),
        ],
        6,
    )
    for col in ("DIRECT", "INDIRECT"):
        _put(t, col, [0, 2, 4], [_cell(rng, "f4", (4, 2)) for _ in range(3)])
    t.close()

    # t03: TiledShapeStMan, two hypercubes and unwritten rows.
    t = _table(
        root / "t03-tssm-partial",
        [
            _arr(
                "F32",
                0.0,
                ndim=2,
                valuetype="float",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
            _arr(
                "C64",
                0j,
                ndim=2,
                valuetype="complex",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
            _arr(
                "B",
                False,
                ndim=2,
                valuetype="boolean",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
            _arr(
                "F64",
                0.0,
                ndim=3,
                valuetype="double",
                datamanagertype=tsg,
                datamanagergroup="G3",
            ),
        ],
        8,
        {
            "G2": {"DEFAULTTILESHAPE": np.int32([2, 4, 2])},
            "G3": {"DEFAULTTILESHAPE": np.int32([2, 2, 2, 2])},
        },
    )
    for col, dt in (("F32", "f4"), ("C64", "c8"), ("B", "bool")):
        _put(t, col, [0, 1, 2], [_cell(rng, dt, (4, 2)) for _ in range(3)])
        _put(t, col, [4, 6], [_cell(rng, dt, (8, 2)) for _ in range(2)])
    _put(t, "F64", [1, 2, 5], [_cell(rng, "f8", (3, 4, 2)) for _ in range(3)])
    t.close()

    # t04: TiledColumnStMan fixed shape, half of the rows written.
    t = _table(
        root / "t04-tcsm-partial",
        [
            _arr(
                "C64",
                0j,
                shape=[4, 2],
                valuetype="complex",
                datamanagertype="TiledColumnStMan",
                datamanagergroup="TC",
            ),
            _arr(
                "B",
                False,
                shape=[4, 2],
                valuetype="boolean",
                datamanagertype="TiledColumnStMan",
                datamanagergroup="TC",
            ),
        ],
        8,
        {"TC": {"DEFAULTTILESHAPE": np.int32([2, 4, 4])}},
    )
    for col, dt in (("C64", "c8"), ("B", "bool")):
        _put(t, col, [0, 1, 2, 3], [_cell(rng, dt, (4, 2)) for _ in range(4)])
    t.close()

    # t05: TiledCellStMan, a different shape per row.
    t = _table(
        root / "t05-tcellsm",
        [
            _arr(
                "F32",
                0.0,
                ndim=2,
                valuetype="float",
                datamanagertype="TiledCellStMan",
                datamanagergroup="TL",
            )
        ],
        4,
        {"TL": {"DEFAULTTILESHAPE": np.int32([2, 2])}},
    )
    _put(
        t,
        "F32",
        range(4),
        [_cell(rng, "f4", s) for s in [(2, 2), (3, 2), (4, 3), (1, 1)]],
    )
    t.close()

    # t06: IncrementalStMan scalars set at a few rows; a fixed-shape array.
    ism = {"datamanagertype": "IncrementalStMan", "datamanagergroup": "IS"}
    t = _table(
        root / "t06-ism",
        [
            _sca("I32", 0, valuetype="int", **ism),
            _sca("F64", 0.0, valuetype="double", **ism),
            _sca("B", False, valuetype="boolean", **ism),
            _sca("S", "", valuetype="string", **ism),
            _arr("ARR", 0.0, shape=[3], valuetype="float", **ism),
        ],
        10,
    )
    for r, v in ((0, 1), (4, 2), (7, 3)):
        t.putcell("I32", r, v)
        t.putcell("F64", r, v / 3)
        t.putcell("B", r, bool(v % 2))
        t.putcell("S", r, f"value {v}")
        t.putcell("ARR", r, np.full(3, v, "f4"))
    t.close()

    # t07: string arrays.
    t = _table(
        root / "t07-strings",
        [
            _arr("VAR", "", ndim=1, valuetype="string"),
            _arr("FIXED", "", shape=[2], valuetype="string", options=4),
            _arr("DIRECT", "", shape=[2], valuetype="string", options=5),
            _arr(
                "ISM",
                "",
                shape=[2],
                valuetype="string",
                datamanagertype="IncrementalStMan",
                datamanagergroup="IS",
            ),
        ],
        6,
    )
    _put(
        t, "VAR", [0, 1, 3], [np.array(v) for v in (["X", "Y"], ["R", "L", "é"], [""])]
    )
    _put(t, "FIXED", [1, 2], [np.array(v) for v in (["a", "b"], ["cc", ""])])
    _put(t, "DIRECT", range(6), [np.array([f"d{r}", "e" * r]) for r in range(6)])
    _put(t, "ISM", [0, 3], [np.array(v) for v in (["p", "q"], ["r", "s"])])
    t.close()

    # t08: TiledShapeStMan with shapes that alternate row by row (hypercubes
    # reused, a row map that is not contiguous per cube), and ndim 1.
    t = _table(
        root / "t08-tssm-alternating",
        [
            _arr(
                "F32",
                0.0,
                ndim=2,
                valuetype="float",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
            _arr(
                "V1",
                0.0,
                ndim=1,
                valuetype="double",
                datamanagertype=tsg,
                datamanagergroup="G1",
            ),
        ],
        6,
        {
            "G2": {"DEFAULTTILESHAPE": np.int32([2, 4, 2])},
            "G1": {"DEFAULTTILESHAPE": np.int32([4, 2])},
        },
    )
    _put(
        t,
        "F32",
        range(6),
        [_cell(rng, "f4", (4, 2) if r % 2 == 0 else (8, 2)) for r in range(6)],
    )
    _put(
        t, "V1", range(6), [_cell(rng, "f8", (3,) if r < 3 else (5,)) for r in range(6)]
    )
    t.close()

    # t09: a big-endian table.
    t = _table(
        root / "t09-big-endian",
        [
            _sca("I32", 0, valuetype="int"),
            _sca("F64", 0.0, valuetype="double", **ism),
            _arr("VAR", 0.0, ndim=1, valuetype="float"),
            _arr(
                "TILED",
                0j,
                ndim=2,
                valuetype="complex",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
        ],
        4,
        {"G2": {"DEFAULTTILESHAPE": np.int32([2, 4, 2])}},
        endian="big",
    )
    t.putcol("I32", np.arange(4, dtype="i4") - 2)
    t.putcell("F64", 1, 2.5)
    _put(t, "VAR", [0, 2], [_cell(rng, "f4", (n,)) for n in (3, 5)])
    _put(t, "TILED", [0, 1, 3], [_cell(rng, "c8", (4, 2)) for _ in range(3)])
    t.close()

    # t10: no rows.
    t = _table(
        root / "t10-empty",
        [
            _sca("SSM", 0, valuetype="int"),
            _sca("ISM", 0.0, valuetype="double", **ism),
            _arr("VAR", 0.0, ndim=1, valuetype="float"),
            _arr("FIXED", 0.0, shape=[3], valuetype="double"),
            _arr("STR", "", ndim=1, valuetype="string"),
            _arr(
                "TSSM",
                0j,
                ndim=2,
                valuetype="complex",
                datamanagertype=tsg,
                datamanagergroup="G2",
            ),
            _arr(
                "TCSM",
                0j,
                shape=[4, 2],
                valuetype="complex",
                datamanagertype="TiledColumnStMan",
                datamanagergroup="TC",
            ),
        ],
        0,
        {
            "G2": {"DEFAULTTILESHAPE": np.int32([2, 4, 2])},
            "TC": {"DEFAULTTILESHAPE": np.int32([2, 4, 4])},
        },
    )
    t.close()


NANT, NTIME = 4, 3
BASELINES = [(a, b) for a in range(NANT) for b in range(a + 1, NANT)]


def _ms(path, rng, spws, extra, groups, ws="all", subtables_empty=(), nrows=None):
    """An MS from default_ms: `spws` the channel counts (one data description
    each), `extra` added column descriptions, `ws` which WEIGHT_SPECTRUM cells
    are written ("all", "none", "first-time")."""
    import casacore.tables as pt

    desc = pt.maketabdesc(extra) if extra else None
    dminfo = pt.makedminfo(desc, groups) if extra else None
    t = pt.default_ms(str(path), desc, dminfo)
    names = t.colnames()
    rows = [
        (ti, d, a, b)
        for ti in range(NTIME)
        for d in range(len(spws))
        for (a, b) in BASELINES
    ]
    if nrows is not None:
        rows = rows[:nrows]
    t.addrows(len(rows))
    if rows:
        time = np.array([5.0e9 + 8.0 * r[0] for r in rows])
        t.putcol("TIME", time)
        t.putcol("TIME_CENTROID", time)
        t.putcol("INTERVAL", np.full(len(rows), 8.0))
        t.putcol("EXPOSURE", np.full(len(rows), 8.0))
        t.putcol("DATA_DESC_ID", np.array([r[1] for r in rows], "i4"))
        t.putcol("ANTENNA1", np.array([r[2] for r in rows], "i4"))
        t.putcol("ANTENNA2", np.array([r[3] for r in rows], "i4"))
        t.putcol("SCAN_NUMBER", np.ones(len(rows), "i4"))
        t.putcol("UVW", rng.standard_normal((len(rows), 3)) * 100)
        t.putcol("WEIGHT", np.ones((len(rows), 4), "f4"))
        t.putcol("SIGMA", np.ones((len(rows), 4), "f4"))
        for i, (ti, d, _, _) in enumerate(rows):
            nchan = spws[d]
            t.putcell("DATA", i, _cell(rng, "c8", (nchan, 4)))
            t.putcell("FLAG", i, rng.random((nchan, 4)) > 0.8)
            if "WEIGHT_SPECTRUM" in names and (
                ws == "all" or (ws == "first-time" and ti == 0)
            ):
                t.putcell(
                    "WEIGHT_SPECTRUM", i, rng.random((nchan, 4)).astype("f4") + 0.5
                )
    t.close()

    def sub(name):
        return pt.table(str(path / name), readonly=False, ack=False)

    with sub("ANTENNA") as a:
        a.addrows(NANT)
        a.putcol("NAME", [f"A{i}" for i in range(NANT)])
        a.putcol("STATION", [f"S{i}" for i in range(NANT)])
        a.putcol("TYPE", ["GROUND-BASED"] * NANT)
        a.putcol("MOUNT", ["ALT-AZ"] * NANT)
        a.putcol("DISH_DIAMETER", np.full(NANT, 13.5))
        a.putcol("POSITION", 5.0e6 + rng.standard_normal((NANT, 3)) * 100)
    with sub("SPECTRAL_WINDOW") as s:
        s.addrows(len(spws))
        for i, n in enumerate(spws):
            freq = 1.0e9 + 1.0e8 * i + 1.0e6 * np.arange(n)
            s.putcell("NUM_CHAN", i, n)
            s.putcell("NAME", i, f"spw{i}")
            s.putcell("CHAN_FREQ", i, freq)
            for c in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
                s.putcell(c, i, np.full(n, 1.0e6))
            s.putcell("REF_FREQUENCY", i, freq[0])
            s.putcell("TOTAL_BANDWIDTH", i, 1.0e6 * n)
            s.putcell("MEAS_FREQ_REF", i, 5)
    with sub("POLARIZATION") as p:
        p.addrows(1)
        p.putcell("NUM_CORR", 0, 4)
        p.putcell("CORR_TYPE", 0, np.array([9, 10, 11, 12], "i4"))
        p.putcell("CORR_PRODUCT", 0, np.array([[0, 0], [0, 1], [1, 0], [1, 1]], "i4"))
    with sub("DATA_DESCRIPTION") as d:
        d.addrows(len(spws))
        d.putcol("SPECTRAL_WINDOW_ID", np.arange(len(spws), dtype="i4"))
        d.putcol("POLARIZATION_ID", np.zeros(len(spws), "i4"))
    with sub("FIELD") as f:
        f.addrows(1)
        f.putcell("NAME", 0, "F0")
        for c in ("PHASE_DIR", "DELAY_DIR", "REFERENCE_DIR"):
            f.putcell(c, 0, np.array([[0.5, -0.5]]))
    with sub("OBSERVATION") as o:
        o.addrows(1)
        o.putcell("TELESCOPE_NAME", 0, "MeerKAT")
        o.putcell("TIME_RANGE", 0, np.array([5.0e9, 5.0e9 + 8.0 * NTIME]))
    with sub("FEED") as f:
        f.addrows(NANT)
        f.putcol("ANTENNA_ID", np.arange(NANT, dtype="i4"))
        f.putcol("SPECTRAL_WINDOW_ID", np.full(NANT, -1, "i4"))
        f.putcol("NUM_RECEPTORS", np.full(NANT, 2, "i4"))
        for i in range(NANT):
            f.putcell("POLARIZATION_TYPE", i, np.array(["X", "Y"]))
            f.putcell("BEAM_OFFSET", i, np.zeros((2, 2)))
            f.putcell("POL_RESPONSE", i, np.eye(2, dtype="c8"))
            f.putcell("RECEPTOR_ANGLE", i, np.zeros(2))
    for name in subtables_empty:
        st = pt.default_ms_subtable(name, str(path / name))
        st.close()
        with pt.table(str(path), readonly=False, ack=False) as main:
            main.putkeyword(name, "Table: " + str(path / name))


def make_mss(root, rng):
    import casacore.tables as pt

    root.mkdir(parents=True, exist_ok=True)
    tsg = "TiledShapeStMan"

    def data(mgr="TiledShapeStMan"):
        if mgr == "StandardStMan":
            return _arr(
                "DATA",
                0j,
                ndim=2,
                valuetype="complex",
                datamanagertype="StandardStMan",
                datamanagergroup="SSMD",
            )
        return _arr(
            "DATA",
            0j,
            ndim=2,
            valuetype="complex",
            datamanagertype=mgr,
            datamanagergroup="TD",
        )

    def ws(**kw):
        return _arr("WEIGHT_SPECTRUM", 0.0, valuetype="float", **kw)

    tiles = {
        "TD": {"DEFAULTTILESHAPE": np.int32([4, 4, 8])},
        "TW": {"DEFAULTTILESHAPE": np.int32([4, 4, 8])},
    }
    tw = {"datamanagertype": tsg, "datamanagergroup": "TW"}
    _ms(
        root / "m01-ws-unwritten-tssm",
        rng,
        [4],
        [data(), ws(ndim=2, **tw)],
        tiles,
        "none",
    )
    _ms(
        root / "m02-ws-unwritten-ssm",
        rng,
        [4],
        [data(), ws(ndim=2, datamanagertype="StandardStMan", datamanagergroup="SSMW")],
        tiles,
        "none",
    )
    _ms(
        root / "m03-ws-partial-tssm",
        rng,
        [4],
        [data(), ws(ndim=2, **tw)],
        tiles,
        "first-time",
    )
    _ms(
        root / "m04-ws-fixed-tcsm",
        rng,
        [4],
        [
            data(),
            ws(shape=[4, 4], datamanagertype="TiledColumnStMan", datamanagergroup="TW"),
        ],
        tiles,
        "none",
    )
    _ms(root / "m05-var-spw-tssm", rng, [4, 8], [data(), ws(ndim=2, **tw)], tiles)
    _ms(
        root / "m06-var-spw-ssm",
        rng,
        [4, 8],
        [data("StandardStMan"), ws(ndim=2, **tw)],
        tiles,
    )
    _ms(
        root / "m07-empty-subtables",
        rng,
        [4, 8],
        [data(), ws(ndim=2, **tw)],
        tiles,
        subtables_empty=("SOURCE", "SYSCAL"),
    )
    _ms(root / "m08-no-rows", rng, [4], [data(), ws(ndim=2, **tw)], tiles, nrows=0)
    del pt


def make(root):
    rng = np.random.default_rng(SEED)
    make_tables(root / "tables", rng)
    make_mss(root / "ms", rng)


# ---------------------------------------------------------------------------
# dumps


def all_tables(root):
    """(case, relative table name, path) of every table: the standalone
    tables, and each MS's main table and subtables (directories that hold a
    table.dat)."""
    out = []
    for kind in ("tables", "ms"):
        for case in sorted((root / kind).iterdir()):
            out.append((case.name, "", case))
            for sub in sorted(case.iterdir()):
                if (sub / "table.dat").exists():
                    out.append((case.name, sub.name, sub))
    return out


def _err(e):
    return f"{type(e).__name__}: {e}"


def _norm(value):
    """A cell as a NumPy array (strings as an object array)."""
    if isinstance(value, dict) and "array" in value:  # python-casacore strings
        return np.array(value["array"], dtype=object).reshape(value["shape"])
    a = np.asarray(value)
    if a.dtype.kind in "USO":
        return np.array(a.tolist(), dtype=object).reshape(a.shape)
    return a


def dump_casacore(root):
    import casacore.tables as pt

    out = {}
    for case, name, path in all_tables(root):
        with pt.table(str(path), ack=False) as t:
            entry = {"nrows": t.nrows(), "columns": {}}
            for col in t.colnames():
                desc = t.getcoldesc(col)
                cells = []
                for r in range(t.nrows()):
                    if not t.iscelldefined(col, r):
                        cells.append(None)
                        continue
                    try:
                        cells.append(_norm(t.getcell(col, r)))
                    except Exception as e:
                        cells.append({"error": _err(e)})
                entry["columns"][col] = {"desc": desc, "cells": cells}
            out[(case, name)] = entry
    _save(
        root, "casacore", out, {"python-casacore": __import__("casacore").__version__}
    )


def dump_arcae(root):
    import arcae
    import pyarrow as pa

    out = {}
    for case, name, path in all_tables(root):
        try:
            t = arcae.table(str(path))
        except Exception as e:
            out[(case, name)] = {"error": _err(e)}
            continue
        nrows = t.nrow()
        entry = {"nrows": nrows, "columns": {}}
        for col in t.columns():
            desc = t.getcoldesc(col)
            is_array = "ndim" in desc or "shape" in desc
            c = {"desc": desc, "is_array": is_array}
            mask = [True] * nrows
            if is_array and nrows:
                try:
                    shapes = t.row_shapes(col)
                    if isinstance(shapes, pa.NullArray):
                        mask = [False] * nrows
                    else:
                        mask = [shapes[r].is_valid for r in range(nrows)]
                except Exception as e:
                    c["row_shapes_error"] = _err(e)
            c["defined"] = mask
            cells = []
            for r in range(nrows):
                if not mask[r]:
                    cells.append(None)
                    continue
                try:
                    v = t.getcol(col, index=(np.array([r]),))
                    cells.append(_norm(v[0]) if is_array else _norm(v)[0])
                except Exception as e:
                    cells.append({"error": _err(e)})
            c["cells"] = cells
            try:
                c["whole"] = _norm(t.getcol(col))
            except Exception as e:
                c["whole"] = {"error": _err(e)}
            rows = np.array([r for r in range(nrows) if mask[r]][::-1], dtype=np.int64)
            c["rev_rows"] = rows.tolist()
            if len(rows):
                try:
                    c["rev"] = _norm(t.getcol(col, index=(rows,)))
                except Exception as e:
                    c["rev"] = {"error": _err(e)}
            entry["columns"][col] = c
        out[(case, name)] = entry
        t.close()
    _save(root, "arcae", out, {"arcae": arcae.__version__, "pyarrow": pa.__version__})


def dump_xms(root):
    import importlib.metadata as md

    import xarray as xr

    out = {}
    for case in sorted((root / "ms").iterdir()):
        entry = {}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                dt = xr.open_datatree(str(case), engine="xarray-ms:msv2")
            except Exception as e:
                entry["error"] = _err(e)
                dt = None
            datasets = []
            if dt is not None:
                for node in dt.subtree:
                    ds = node.dataset
                    if "VISIBILITY" not in ds.data_vars:
                        continue
                    d = {
                        "path": node.path,
                        "time": ds["time"].values,
                        "ant1": [str(x) for x in ds["baseline_antenna1_name"].values],
                        "ant2": [str(x) for x in ds["baseline_antenna2_name"].values],
                        "frequency": ds["frequency"].values,
                        "vars": {},
                    }
                    for v in ("VISIBILITY", "FLAG", "WEIGHT", "SIGMA_SPECTRUM", "UVW"):
                        if v not in ds.data_vars:
                            d["vars"][v] = {"absent": True}
                            continue
                        try:
                            d["vars"][v] = {"values": np.asarray(ds[v].values)}
                        except Exception as e:
                            d["vars"][v] = {"error": _err(e)}
                    datasets.append(d)
            entry["datasets"] = datasets
        entry["warnings"] = [f"{w.category.__name__}: {w.message}" for w in caught]
        out[case.name] = entry
    _save(
        root,
        "xms",
        out,
        {"xarray-ms": md.version("xarray-ms"), "xarray": xr.__version__},
    )


def _save(root, name, data, versions):
    (root / "dumps").mkdir(parents=True, exist_ok=True)
    with open(root / "dumps" / f"{name}.pkl", "wb") as f:
        pickle.dump({"versions": versions, "data": data}, f, protocol=5)
    print(f"{name}: {len(data)} entries, {versions}")


def _load(root, name):
    with open(root / "dumps" / f"{name}.pkl", "rb") as f:
        return pickle.load(f)


# ---------------------------------------------------------------------------
# check (rang.core_ms)

VALUE_TYPES = {
    "boolean": "bool",
    "byte": "uint8",
    "uChar": "uint8",
    "short": "int16",
    "ushort": "uint16",
    "int": "int32",
    "uint": "uint32",
    "int64": "int64",
    "float": "float32",
    "double": "float64",
    "complex": "complex64",
    "dcomplex": "complex128",
    "string": "object",
}


def equal(a, b):
    """Exact equality: shape, dtype and bytes; strings element by element."""
    a, b = _norm(a), _norm(b)
    if a.shape != b.shape:
        return False
    if a.dtype == object or b.dtype == object:
        return a.dtype == b.dtype and a.ravel().tolist() == b.ravel().tolist()
    return a.dtype == b.dtype and a.tobytes() == b.tobytes()


def _is_error(x):
    return isinstance(x, dict) and "error" in x


def _rang_read(fn):
    """('values', array) / ('unwritten', msg) / ('refused', msg)."""
    try:
        return "values", fn()
    except Exception as e:
        msg = _err(e)
        if any(u in msg for u in UNWRITTEN):
            return "unwritten", msg
        return "refused", msg


RANK = {"mismatch": 3, "refusal": 2, "ra-ng only": 1, "match": 0}


def check_column(rt, col, oracle):
    """Outcome of one column, with the details that decide it."""
    if oracle["desc"].get("valueType") == "boolean":
        oracle = _arcae_bools(oracle)
    nrows = len(oracle["cells"])
    notes, outcome = [], "match"
    rang_cells = []

    def worse(o, note):
        nonlocal outcome
        notes.append(note)
        if RANK[o] > RANK[outcome]:
            outcome = o

    for r in range(nrows):
        kind, value = _rang_read(lambda r=r: rt.getcol(col, r, 1)[0])
        rang_cells.append((kind, value))
        want = oracle["cells"][r]
        if _is_error(want):
            if kind == "values":
                worse("ra-ng only", f"row {r}: arcae {want['error']}")
            elif kind == "refused":
                notes.append(f"row {r}: both refuse")
            continue
        if want is None:
            if kind == "values":
                worse(
                    "mismatch", f"row {r}: ra-ng returns a cell arcae calls unwritten"
                )
            elif kind == "refused":
                worse("refusal", f"row {r}: unwritten; ra-ng {value}")
            continue
        if kind == "unwritten":
            worse("mismatch", f"row {r}: ra-ng calls a written cell unwritten: {value}")
        elif kind == "refused":
            worse("refusal", f"row {r}: {value}")
        elif not equal(value, want):
            worse(
                "mismatch",
                f"row {r}: values differ (ra-ng {_summ(value)}, arcae {_summ(want)})",
            )

    for label, rang_fn, want in (
        ("whole", lambda: rt.getcol(col), oracle.get("whole")),
        (
            "reverse rows",
            lambda: rt.getcol_rows(col, oracle["rev_rows"]),
            oracle.get("rev"),
        ),
    ):
        if want is None:
            continue
        kind, value = _rang_read(rang_fn)
        if _is_error(want):
            if kind == "values":
                worse("ra-ng only", f"{label}: arcae {want['error']}")
            else:
                notes.append(
                    f"{label}: both refuse (ra-ng {value}; arcae {want['error']})"
                )
        elif kind != "values":
            if nrows == 0 and label == "whole":
                worse("refusal", f"{label} of no rows: {value}")
            else:
                worse("refusal", f"{label}: {value}")
        elif not equal(value, want):
            worse(
                "mismatch",
                f"{label}: values differ (ra-ng {_summ(value)}, arcae {_summ(want)})",
            )
    return outcome, notes, rang_cells


def _arcae_bools(oracle):
    """Post hoc (2026-11-13): arcae returns boolean cells as uint8 0/1
    (python-casacore as bool); read them as bool. A value other than 0 or 1
    is left as it is, so it still fails the comparison."""

    def conv(x):
        if x is None or _is_error(x):
            return x
        a = np.asarray(x)
        if a.dtype == np.uint8 and np.isin(a, (0, 1)).all():
            return a.astype(bool)
        return x

    out = dict(oracle)
    out["cells"] = [conv(x) for x in oracle["cells"]]
    for k in ("whole", "rev"):
        if k in oracle:
            out[k] = conv(oracle[k])
    return out


def _summ(v):
    a = _norm(v)
    return f"{a.dtype}{list(a.shape)}"


def check_description(rt, oracle):
    """Differences between ra-ng's description and arcae's."""
    diffs = []
    if rt.nrows != oracle["nrows"]:
        diffs.append(f"nrows {rt.nrows} != {oracle['nrows']}")
    if set(rt.columns) != set(oracle["columns"]):
        diffs.append(f"columns {sorted(set(rt.columns) ^ set(oracle['columns']))}")
    for col, o in oracle["columns"].items():
        c = rt.columns.get(col)
        if c is None:
            continue
        want = VALUE_TYPES.get(o["desc"]["valueType"], o["desc"]["valueType"])
        got = (
            "object" if c["dtype"] in ("str", "string", "object", "<U0") else c["dtype"]
        )
        if got != want:
            diffs.append(f"{col} dtype {c['dtype']} != {o['desc']['valueType']}")
        shape = o["desc"].get("shape")
        # Both are casacore descriptions: the shape in casacore axis order.
        # Post hoc (2026-11-13): getcoldesc (arcae and python-casacore) gives
        # the shape in NumPy order, ra-ng's description in casacore order.
        fixed = o["desc"].get("option", 0) & 4 and shape is not None
        if fixed and list(c["shape"])[::-1] != list(shape):
            diffs.append(f"{col} fixed shape {c['shape']} != {shape}")
    return diffs


def check_xms(case, entry, main_cells, rt_main):
    """Outcome per xarray-ms variable of one MS."""
    if "error" in entry:
        return {"open": entry["error"]}
    out = {}
    if not entry["datasets"]:
        return {"datasets": "none"}
    names = list(rt_main.subtable("ANTENNA").getcol("NAME"))
    spw = rt_main.subtable("SPECTRAL_WINDOW")
    freqs = [spw.getcol("CHAN_FREQ", r, 1)[0] for r in range(spw.nrows)]
    ddid_spw = list(rt_main.subtable("DATA_DESCRIPTION").getcol("SPECTRAL_WINDOW_ID"))
    if rt_main.nrows:
        time = rt_main.getcol("TIME")
        a1, a2 = rt_main.getcol("ANTENNA1"), rt_main.getcol("ANTENNA2")
        dd = rt_main.getcol("DATA_DESC_ID")
    for d in entry["datasets"]:
        s = next(i for i, f in enumerate(freqs) if equal(f, d["frequency"]))
        ddid = ddid_spw.index(s)
        index = {}
        for r in range(rt_main.nrows):
            if dd[r] == ddid:
                index[(float(time[r]), names[a1[r]], names[a2[r]])] = r
        for var, got in d["vars"].items():
            key = f"{d['path']}:{var}"
            if got.get("absent"):
                out[key] = "not exposed"
                continue
            if "error" in got:
                out[key] = f"xarray-ms fails: {got['error']}"
                continue
            column = {"VISIBILITY": "DATA", "WEIGHT": "WEIGHT_SPECTRUM"}.get(var, var)
            if column not in main_cells:
                column = "WEIGHT" if var == "WEIGHT" else column
            if column not in main_cells:
                # Post hoc (2026-11-13): xarray-ms derives the variable from
                # another column (SIGMA_SPECTRUM from SIGMA); not compared.
                out[key] = "derived by xarray-ms (no such column)"
                continue
            cells = main_cells[column]
            values = got["values"]
            bad = []
            for ti, t in enumerate(d["time"]):
                for bi, (n1, n2) in enumerate(zip(d["ant1"], d["ant2"])):
                    x = values[ti, bi]
                    # Post hoc (2026-11-13): xarray-ms's time is Unix seconds,
                    # TIME is MJD seconds; the epochs differ by 3506716800 s.
                    r = index.get((float(t) + UNIX_MJD, n1, n2))
                    fill = np.ones_like(x) if var == "FLAG" else np.full_like(x, np.nan)
                    if r is None:
                        if not np.array_equal(x, fill, equal_nan=True):
                            bad.append(f"no row at {ti},{bi} but values")
                        continue
                    kind, v = cells[r]
                    if kind == "refused":
                        bad.append(f"row {r}: ra-ng refuses: {v}")
                    elif kind == "unwritten":
                        if not np.array_equal(x, fill, equal_nan=True):
                            bad.append(
                                f"row {r}: ra-ng unwritten, xarray-ms not the fill"
                            )
                    else:
                        v = (
                            np.broadcast_to(np.asarray(v), x.shape)
                            if column == "WEIGHT"
                            else v
                        )
                        v = np.asarray(v).astype(x.dtype)
                        if v.shape != x.shape or not np.array_equal(
                            v, x, equal_nan=True
                        ):
                            bad.append(f"row {r}: values differ")
            refusals = [b for b in bad if "refuses" in b]
            if not bad:
                out[key] = "match"
            elif refusals and len(refusals) == len(bad):
                out[key] = f"refusal ({len(bad)} cells): {refusals[0]}"
            else:
                out[key] = f"mismatch ({len(bad)} cells): {bad[0]}"
    return out


def check(root, out_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
    import rang
    import rang._core
    from rang import core_ms

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()
    print("extension:", rang._core.__file__, "commit:", head)
    arcae, casa, xms = _load(root, "arcae"), _load(root, "casacore"), _load(root, "xms")
    result = {
        "note": "research/msv2-edge-cases.md",
        "versions": {
            **arcae["versions"],
            **casa["versions"],
            **xms["versions"],
            "extension": str(Path(rang._core.__file__).name),
            "commit": head,
        },
        "tables": [],
        "oracle_disagreements": [],
        "xarray_ms": {},
    }
    main_cells = {}
    for (case, name), oracle in arcae["data"].items():
        path = root / ("ms" if case.startswith("m") else "tables") / case / name
        label = f"{case}/{name}" if name else case
        row = {"table": label, "columns": {}}
        # Triage: arcae against python-casacore.
        cc = casa["data"].get((case, name), {}).get("columns", {})
        for col, o in oracle.get("columns", {}).items():
            if o["desc"].get("valueType") == "boolean":
                o = _arcae_bools(o)
            for r, (a, c) in enumerate(
                zip(o["cells"], cc.get(col, {}).get("cells", []))
            ):
                # Post hoc (2026-11-13): python-casacore returns scalar cells
                # as Python numbers (int64, float64): compare scalars by value.
                if a is None or _is_error(a) or _is_error(c):
                    same = True
                elif o["is_array"]:
                    same = equal(a, c)
                else:
                    same = np.asarray(a).tolist() == np.asarray(c).tolist()
                if (a is None) != (c is None) or not same:
                    result["oracle_disagreements"].append(f"{label} {col} row {r}")
        if "error" in oracle:
            row["oracle_open"] = oracle["error"]
            result["tables"].append(row)
            continue
        try:
            rt = core_ms.Table(path)
        except Exception as e:
            row["open"] = _err(e)
            for col in oracle["columns"]:
                row["columns"][col] = {
                    "outcome": "refusal",
                    "notes": [f"open: {_err(e)}"],
                }
            result["tables"].append(row)
            continue
        row["description"] = check_description(rt, oracle)
        for col, o in oracle["columns"].items():
            if col not in rt.columns:
                row["columns"][col] = {
                    "outcome": "mismatch",
                    "notes": ["absent in ra-ng"],
                }
                continue
            outcome, notes, cells = check_column(rt, col, o)
            o_manager = o["desc"].get("dataManagerType", "")
            row["columns"][col] = {
                "outcome": outcome,
                "manager": o_manager,
                "notes": notes[:6],
            }
            if case.startswith("m") and name == "":
                main_cells.setdefault(case, {})[col] = cells
        if row["description"]:
            row["outcome"] = "mismatch"
        result["tables"].append(row)
    for case, entry in xms["data"].items():
        rt = core_ms.Table(root / "ms" / case)
        result["xarray_ms"][case] = {
            "outcomes": check_xms(case, entry, main_cells.get(case, {}), rt),
            "warnings": entry["warnings"][:8],
        }
    counts = {}
    for t in result["tables"]:
        for c in t["columns"].values():
            counts[c["outcome"]] = counts.get(c["outcome"], 0) + 1
    result["counts"] = counts
    Path(out_path).write_text(json.dumps(result, indent=1, default=str) + "\n")
    for t in result["tables"]:
        bad = {k: v for k, v in t["columns"].items() if v["outcome"] != "match"}
        flag = (
            " DESCRIPTION " + "; ".join(t.get("description", []))
            if t.get("description")
            else ""
        )
        print(
            f"{t['table']}: {len(t['columns']) - len(bad)}/{len(t['columns'])} match{flag}"
        )
        for k, v in bad.items():
            print(f"   {k} [{v.get('manager', '')}] {v['outcome']}: {v['notes'][:2]}")
    print(
        "xarray-ms:",
        json.dumps(
            {k: v["outcomes"] for k, v in result["xarray_ms"].items()}, indent=1
        ),
    )
    print(
        "oracle disagreements:",
        len(result["oracle_disagreements"]),
        result["oracle_disagreements"][:10],
    )
    print("counts:", counts)


def main(argv):
    cmd, root = argv[1], Path(argv[2])
    if cmd == "make":
        make(root)
    elif cmd == "dump-casacore":
        dump_casacore(root)
    elif cmd == "dump-arcae":
        dump_arcae(root)
    elif cmd == "dump-xms":
        dump_xms(root)
    elif cmd == "check":
        check(root, argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
