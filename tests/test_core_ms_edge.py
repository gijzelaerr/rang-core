"""IncrementalStMan arrays and strings, per-column refusal and TiledCellStMan
in the core table reader (research/msv2-edge-cases.md, R1 to R3).

`tests/data/msv2-edge` holds three cases of the MSv2 edge-case set, written
by python-casacore 3.8.1, with arcae 0.5.9's cells in `oracle.json`
(`tools/oracles/msv2-edge/fixture.py`). The writer round trips below cover
forms the case set lacks (Direct ISM arrays, undefined ISM and TiledCellStMan
cells, several ISM buckets, big-endian, no rows); they are checked against
ra-ng's own table writer, whose bytes were compared with casacore's
(research/e5-table-writer-rest.md), not against arcae.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from rang import core, core_ms
from rang import core_ms_write as w

DATA = Path(__file__).resolve().parent / "data" / "msv2-edge"
ORACLE = json.loads((DATA / "oracle.json").read_text(encoding="utf-8"))["tables"]
CASES = [(t, c) for t, e in ORACLE.items() for c in e["columns"]]

pytestmark = pytest.mark.skipif(
    not core_ms.has_reader(), reason="core library built without the reader"
)


def _want(entry):
    if entry["dtype"] == "str":
        return np.asarray(entry["values"], dtype=object).reshape(entry["shape"])
    return np.asarray(entry["values"], dtype=entry["dtype"]).reshape(entry["shape"])


def _same(got, want):
    """Exact equality; arcae's booleans are uint8 0 and 1."""
    got = np.asarray(got)
    if want.dtype == np.uint8 and got.dtype == bool:
        got = got.astype(np.uint8)
    if want.dtype == object:
        return got.shape == want.shape and got.tolist() == want.tolist()
    return (
        got.shape == want.shape
        and got.dtype == want.dtype
        and got.tobytes() == want.tobytes()
    )


@pytest.mark.parametrize("case,name", CASES)
def test_every_cell_equals_arcae(case, name):
    cells = ORACLE[case]["columns"][name]
    with core_ms.open_table(DATA / case) as t:
        assert t.nrows == ORACLE[case]["nrows"]
        assert t.columns[name]["supported"]
        for row, entry in enumerate(cells):
            if entry is None:
                with pytest.raises(OSError, match="has no (tiled )?array"):
                    t.getcol(name, row, 1)
                continue
            assert _same(t.getcol(name, row, 1)[0], _want(entry)), (case, name, row)
        defined = [r for r, e in enumerate(cells) if e is not None][::-1]
        shapes = {tuple(cells[r]["shape"]) for r in defined}
        if len(shapes) == 1:
            got = t.getcol_rows(name, defined)
            for i, r in enumerate(defined):
                assert _same(got[i], _want(cells[r])), (case, name, r)
        else:
            with pytest.raises(OSError, match="differ in shape"):
                t.getcol_rows(name, defined)


def test_incremental_scalars_read_beside_arrays():
    """R1: scalars of a manager that also holds a string and an array."""
    with core_ms.open_table(DATA / "t06-ism") as t:
        assert t.getcol("I32").tolist() == [1, 1, 1, 1, 2, 2, 2, 3, 3, 3]
        assert t.getcol("B", 3, 3).tolist() == [True, False, False]
        assert t.getcol("S", 6, 2).tolist() == ["value 2", "value 3"]
        assert t.getcol("ARR", 2, 3).tolist() == [[1.0] * 3] * 2 + [[2.0] * 3]


def test_tiled_cell_sliced_read():
    """R3: a cell slice of a TiledCellStMan cell of several tiles."""
    entry = ORACLE["t05-tcellsm"]["columns"]["F32"][2]
    with core_ms.open_table(DATA / "t05-tcellsm") as t:
        got = t.getcol("F32", 2, 1, chans=slice(1, 3))[0]
    assert np.array_equal(got, _want(entry)[1:3])


# ---------------------------------------------------------------------------
# Round trips through ra-ng's table writer.

writer = pytest.mark.skipif(
    not (w.has_writer() and hasattr(core.extension(), "ms_describe")),
    reason="extension without the E5 table writer",
)


def ism(columns, **spec):
    return {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": spec, "COLUMNS": columns}


def _check_all(path, names):
    """Every cell the reader returns equals the writer's own read."""
    nrows, _ = w.describe(path)
    with core_ms.open_table(path) as t:
        for name in names:
            assert t.columns[name]["supported"], name
            want = w.read_cells(path, name, 0, nrows)
            for row, cell in enumerate(want):
                if cell is None:
                    with pytest.raises(OSError, match="has no (tiled )?array"):
                        t.getcol(name, row, 1)
                    continue
                got = t.getcol(name, row, 1)[0]
                if cell.dtype == object:
                    assert np.asarray(got).tolist() == cell.tolist(), (name, row)
                else:
                    assert np.asarray(got).tobytes() == cell.tobytes(), (name, row)
                    assert np.shape(got) == cell.shape, (name, row)


@writer
@pytest.mark.parametrize("endian", ["little", "big"])
def test_incremental_every_form_round_trips(tmp_path, endian):
    path = tmp_path / "ism"
    cols = [
        w.makescacoldesc("I", 0),
        w.makescacoldesc("S", ""),
        w.makescacoldesc("B", False),
        w.makearrcoldesc("A", 0.0, shape=[3], options=1),
        w.makearrcoldesc("AB", False, shape=[2, 5], options=1),
        w.makearrcoldesc("AS", "", shape=[3], options=1),
        w.makearrcoldesc("AS1", "", shape=[1], options=1),
        w.makearrcoldesc("V", 0.0, ndim=1),
        w.makearrcoldesc("VS", "", ndim=2),
        w.makearrcoldesc("F", 0j, shape=[2], valuetype="complex"),
    ]
    names = [c["name"] for c in cols]
    n = 120
    with w.create_table(
        path, cols, nrow=n, dminfo={"*1": ism(names, BUCKETSIZE=512)}, endian=endian
    ) as t:
        for row in range(0, n, 3):
            t.putcell("I", row, row // 9)
            t.putcell("S", row, f"string {row // 6}" + "x" * (row % 11))
            t.putcell("B", row, bool(row % 2))
            t.putcell("A", row, np.arange(3.0) + row // 4)
            t.putcell("AB", row, (np.arange(10).reshape(2, 5) + row) % 3 == 0)
            t.putcell("AS", row, np.array([f"a{row}", "", "é" * (row % 4)]))
            t.putcell("AS1", row, np.array([f"one {row // 5}"]))
            t.putcell("F", row, np.array([row + 1j, -row * 1j], np.complex64))
        for row in range(7, n, 13):  # V and VS undefined before row 7
            t.putcell("V", row, np.arange(1.0 + row % 4))
            t.putcell("VS", row, np.array([["p", f"q{row}"]] * (1 + row % 2)))
    _check_all(path, names)
    with core_ms.open_table(path) as t:
        assert t.getcol("AB").shape == (n, 2, 5)
        assert t.getcol("AS", 30, 40).shape == (40, 3)
        assert t.getcol("A", 5, 20, chans=slice(1, 2)).shape == (20, 1)
        with pytest.raises(OSError, match="has no array"):
            t.getcol("V")
        with pytest.raises(OSError, match="differ in shape"):
            t.getcol("V", 7, 20)


@writer
def test_incremental_table_of_no_rows(tmp_path):
    path = tmp_path / "empty"
    cols = [
        w.makescacoldesc("T", 0.0),
        w.makescacoldesc("N", ""),
        w.makearrcoldesc("D", 0.0, ndim=2),
    ]
    with w.create_table(path, cols, dminfo={"*1": ism(["T", "N", "D"])}):
        pass
    with core_ms.open_table(path) as t:
        assert t.nrows == 0
        for name in ("T", "N", "D"):
            assert t.columns[name]["supported"]
            assert len(t.getcol(name)) == 0


@writer
def test_tiled_cell_undefined_rows_round_trip(tmp_path):
    path = tmp_path / "tcell"
    cols = [
        w.makearrcoldesc("C", 0j, ndim=2, valuetype="complex"),
        w.makearrcoldesc("B", False, ndim=2),
    ]
    dm = {
        "*1": {
            "TYPE": "TiledCellStMan",
            "NAME": "TC",
            "SPEC": {"DEFAULTTILESHAPE": [2, 3]},
            "COLUMNS": ["C", "B"],
        }
    }
    rng = np.random.default_rng(5)
    with w.create_table(path, cols, nrow=6, dminfo=dm) as t:
        for row, shape in ((0, (5, 4)), (2, (1, 7)), (3, (5, 4)), (5, (3, 3))):
            v = rng.normal(size=shape) + 1j * rng.normal(size=shape)
            t.putcell("C", row, v.astype(np.complex64))
            t.putcell("B", row, rng.normal(size=shape) > 0)
    _check_all(path, ["C", "B"])
    with core_ms.open_table(path) as t:
        assert t.getcol_rows("B", [3, 0]).shape == (2, 5, 4)
        with pytest.raises(OSError, match="has no tiled array"):
            t.getcol("C", 1, 1)
