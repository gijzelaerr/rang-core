"""IncrementalStMan, last-row removal, tiled hypercubes, big-endian,
MemoryStMan, TiledDataStMan and MultiFile tables in the core writer (E5).

research/e5-table-writer-rest.md. These tests use only the core (they skip
when the extension lacks the E5 calls); the byte comparisons against
casacore 3.8.1 need Docker and the oracle image and are made by
`examples/check_ms_rest.py`; their archived verdict is checked when the run
directory is present.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from rang import core
from rang import core_ms_write as w

pytestmark = pytest.mark.skipif(
    not (w.has_writer() and hasattr(core.extension(), "ms_describe")),
    reason="extension without the E5 table writer",
)

ROOT = Path(__file__).resolve().parents[1]


def ism(name, columns, **spec):
    return {"TYPE": "IncrementalStMan", "NAME": name, "SPEC": spec, "COLUMNS": columns}


def column(path, name):
    nrows, _ = w.describe(path)
    return w.read_cells(path, name, 0, nrows)


def test_incremental_values_rows_and_strings(tmp_path):
    path = tmp_path / "ism"
    cols = [
        w.makescacoldesc("I", 0),
        w.makescacoldesc("D", 0.0),
        w.makescacoldesc("S", ""),
        w.makearrcoldesc("A", 0.0, shape=[3], options=1),
        w.makearrcoldesc("V", 0.0, ndim=1),
    ]
    dm = {"*1": ism("ISM", ["I", "D", "S", "A", "V"], BUCKETSIZE=512)}
    ints = np.repeat(np.arange(25, dtype=np.int32), 8)
    strings = [f"s{i // 3}" for i in range(200)]
    with w.create_table(path, cols, nrow=200, dminfo=dm) as t:
        t.putcol("I", ints)
        t.putcol("D", ints.astype(float) / 2)
        t.putcol("S", strings)
        t.putcol("A", np.repeat(np.arange(200.0)[:, None] // 10, 3, axis=1))
        for row in range(0, 200, 7):
            t.putcell("V", row, np.arange(1 + row % 3, dtype=float))
        t.putcell("I", 100, 999)
    expect = ints.copy()
    expect[100] = 999
    assert np.array_equal([c for c in column(path, "I")], expect)
    assert [str(c) for c in column(path, "S")] == strings
    v = column(path, "V")
    # Rows after a put share its array until the next put (ISM semantics).
    assert np.array_equal(v[8], np.arange(1 + 7 % 3, dtype=float))
    with w.open_table(path, readonly=False) as t:
        t.addrows(10)
        t.putcol("I", np.full(10, 7, np.int32), 200, 10)
        t.removerows([0, 1, 150, 209])
    nrows, _ = w.describe(path)
    assert nrows == 206
    i = column(path, "I")
    assert np.array_equal(i[:2], expect[2:4]) and int(i[-1]) == 7
    with w.open_table(path, readonly=False) as t:
        t.removerows(list(range(206)))
        t.addrows(3)
        t.putcol("I", np.array([4, 4, 5], np.int32))
    assert np.array_equal(column(path, "I"), [4, 4, 5])


def test_last_standard_row_is_removed(tmp_path):
    path = tmp_path / "ssm"
    cols = [w.makescacoldesc("I", 0), w.makescacoldesc("S", "")]
    with w.create_table(path, cols, nrow=40) as t:
        t.putcol("I", np.arange(40, dtype=np.int32))
        t.putcol("S", [f"a longer string {i}" for i in range(40)])
        t.removerows(list(range(40)))
        t.addrows(2)
        t.putcol("I", np.array([3, 9], np.int32))
        t.putcol("S", ["x", "a string of more than eight"])
    assert np.array_equal(column(path, "I"), [3, 9])
    assert [str(s) for s in column(path, "S")] == ["x", "a string of more than eight"]


def test_tiled_shape_hypercubes_and_undefined_rows(tmp_path):
    path = tmp_path / "tss"
    cols = [w.makearrcoldesc("V", 0.0, ndim=2, valuetype="float")]
    dm = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TSS",
            "SPEC": {"DEFAULTTILESHAPE": [4, 8, 4]},
            "COLUMNS": ["V"],
        }
    }
    a = np.arange(32, dtype=np.float32).reshape(8, 4)
    b = np.arange(32, dtype=np.float32).reshape(16, 2)
    with w.create_table(path, cols, nrow=6, dminfo=dm) as t:
        t.putcell("V", 0, a)
        t.putcell("V", 1, b)
        t.putcell("V", 3, a + 1)
        with pytest.raises(OSError, match="cannot change shape"):
            t.putcell("V", 0, b)
        assert not t.iscelldefined("V", 2)
    cells = column(path, "V")
    assert np.array_equal(cells[0], a) and np.array_equal(cells[1], b)
    assert cells[2] is None and np.array_equal(cells[3], a + 1)


def test_big_endian_table_round_trips(tmp_path):
    path = tmp_path / "be"
    cols = [
        w.makescacoldesc("I", 0),
        w.makescacoldesc("S", ""),
        w.makearrcoldesc("V", 0.0, ndim=1),
        w.makearrcoldesc("T", 0.0, shape=[4, 8], valuetype="float"),
        w.makescacoldesc("M", 0),
    ]
    dm = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "TSS",
            "SPEC": {"DEFAULTTILESHAPE": [4, 8, 4]},
            "COLUMNS": ["T"],
        },
        "*2": ism("ISM", ["M"]),
    }
    tiles = np.arange(5 * 32, dtype=np.float32).reshape(5, 4, 8)
    with w.create_table(path, cols, nrow=5, dminfo=dm, endian="big") as t:
        t.putcol("I", np.arange(5, dtype=np.int32) - 2)
        t.putcol("S", ["a", "bb", "", "a string longer than 8", "e"])
        for row in range(5):
            t.putcell("V", row, np.arange(row + 1.0))
        t.putcol("T", tiles)
        t.putcol("M", np.array([1, 1, 2, 2, 2], np.int32))
    assert np.array_equal(column(path, "I"), np.arange(5) - 2)
    assert np.array_equal(np.stack(column(path, "T")), tiles)
    assert np.array_equal(column(path, "V")[3], np.arange(4.0))
    assert np.array_equal(column(path, "M"), [1, 1, 2, 2, 2])


def test_multifile_table_round_trips_and_leaves_no_staging(tmp_path):
    path = tmp_path / "mf"
    cols = [w.makescacoldesc("I", 0), w.makearrcoldesc("V", 0.0, ndim=1)]
    with w.create_table(path, cols, nrow=4, multifile=True) as t:
        t.putcol("I", np.arange(4, dtype=np.int32))
        for row in range(4):
            t.putcell("V", row, np.full(row + 1, float(row)))
    names = sorted(p.name for p in path.iterdir())
    assert names == ["table.dat", "table.info", "table.lock", "table.mf"]
    with w.open_table(path, readonly=False) as t:
        t.addrows(1)
        t.putcol("I", np.array([9], np.int32), 4, 1)
    assert np.array_equal(column(path, "I"), [0, 1, 2, 3, 9])
    assert np.array_equal(column(path, "V")[2], [2.0, 2.0, 2.0])
    assert core.extension().ms_multifile_check(str(path)) == []


def test_memory_and_tiled_data_managers(tmp_path):
    path = tmp_path / "msm"
    cols = [w.makescacoldesc("I", 0), w.makescacoldesc("J", 0)]
    dm = {"*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["I"]}}
    with w.create_table(path, cols, nrow=3, dminfo=dm) as t:
        t.putcol("I", np.arange(3, dtype=np.int32))
        t.putcol("J", np.arange(3, dtype=np.int32))
    assert not (path / "table.f0").exists()
    with pytest.raises(OSError, match="MemoryStMan"):
        w.read_cells(path, "I", 0, 3)
    assert np.array_equal(column(path, "J"), [0, 1, 2])
    tds = tmp_path / "tds"
    td = w.maketabdesc([w.makearrcoldesc("D", 0.0, shape=[4, 8], valuetype="float")])
    w.tabledefinehypercolumn(td, "TDS", 3, ["D"])
    dmi = {
        "*1": {"TYPE": "TiledDataStMan", "NAME": "TDS", "SPEC": {}, "COLUMNS": ["D"]}
    }
    with (
        w.create_table(tds, td, nrow=2, dminfo=dmi) as t,
        pytest.raises(OSError, match="E6"),
    ):
        t.putcol("D", np.zeros((2, 4, 8), np.float32))
    assert w.read_cells(tds, "D", 0, 2) == [None, None]


def test_archived_check_passes_when_present():
    runs = sorted((ROOT / "outputs").glob("e5-*-01/result.json"))
    if not runs:
        pytest.skip("no E5 oracle run on disk")
    archive = json.loads(
        (ROOT / "research" / "results" / "e5-table-writer-rest.json").read_text()
    )
    result = json.loads(runs[-1].read_text())
    assert result == archive["result"]
