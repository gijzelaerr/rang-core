"""Task E6 of the core table writer (research/e6-table-writer-final.md):
TiledDataStMan hypercubes, TiledCellStMan, IncrementalStMan string arrays,
MultiFile block order and header continuation, the MultiHDF5 refusal.
The byte comparisons against casacore are the checker's
(`examples/check_ms_final.py`); these tests need only the extension and
check the archived result when the frozen run is on disk."""

import json
from pathlib import Path

import numpy as np
import pytest
from rang import core

w = pytest.importorskip("rang.core_ms_write")
ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not (w.has_writer() and hasattr(core.extension().MsWriter, "add_hypercube")),
    reason="the extension has no E6 table writer",
)


def cells(path, column, n):
    return w.read_cells(path, column, 0, n)


def test_tiled_data_hypercubes(tmp_path):
    path = tmp_path / "tds"
    cols = [
        w.makearrcoldesc("DATA", 0.0, shape=[8, 4], valuetype="float"),
        w.makearrcoldesc("FREQ", 0.0, shape=[4]),
        w.makescacoldesc("TIME", 0.0),
        w.makescacoldesc("ID", 0),
    ]
    desc = w.maketabdesc(cols)
    w.tabledefinehypercolumn(desc, "TDS", 3, ["DATA"], ["FREQ", "", "TIME"], ["ID"])
    dm = {
        "*1": {
            "TYPE": "TiledDataStMan",
            "NAME": "TDS",
            "SPEC": {},
            "COLUMNS": ["DATA", "FREQ", "TIME", "ID"],
        }
    }
    freq = np.arange(4.0)
    data = np.arange(7 * 32, dtype=np.float32).reshape(7, 8, 4)
    with w.create_table(path, desc, nrow=7, dminfo=dm) as t:
        t.addhypercube(
            "TDS",
            [4, 8, 3],
            [4, 4, 2],
            {"ID": np.int32(1), "FREQ": freq, "TIME": np.array([1.0, 2, 3])},
        )
        t.addhypercube("TDS", [4, 8, 0], [4, 8, 2], {"ID": np.int32(2)})
        t.extendhypercube("TDS", 4, {"ID": np.int32(2), "TIME": np.array([7.0, 8])})
        with pytest.raises(OSError, match="Insufficient #rows"):
            t.extendhypercube("TDS", 1, {"ID": np.int32(2)})
        t.putcol("DATA", data)
        t.putcell("TIME", 4, 9.5)
    got = cells(path, "DATA", 7)
    assert all(np.array_equal(g, d) for g, d in zip(got, data))
    times = [float(x) for x in cells(path, "TIME", 7)]
    assert times == [1, 2, 3, 0, 9.5, 7, 8]
    assert np.array_equal(cells(path, "FREQ", 7)[0], freq)
    assert [int(x) for x in cells(path, "ID", 7)] == [1, 1, 1, 2, 2, 2, 2]
    assert sorted(p.name for p in path.glob("table.f0_TSM*")) == [
        "table.f0_TSM0",
        "table.f0_TSM1",
    ]


def test_tiled_cell_reshape_and_refusals(tmp_path):
    path = tmp_path / "tcs"
    cols = [w.makearrcoldesc("D", 0.0, ndim=2)]
    dm = {
        "*1": {
            "TYPE": "TiledCellStMan",
            "NAME": "TCS",
            "SPEC": {"DEFAULTTILESHAPE": np.array([4, 4], np.int32)},
            "COLUMNS": ["D"],
        }
    }
    a, b = np.ones((3, 5)), np.arange(6.0).reshape(2, 3)
    with w.create_table(path, w.maketabdesc(cols), nrow=3, dminfo=dm) as t:
        t.putcell("D", 0, a)
        t.flush()
        t.putcell("D", 0, b)
        t.putcell("D", 2, a)
    got = cells(path, "D", 3)
    assert np.array_equal(got[0], b) and got[1] is None and np.array_equal(got[2], a)
    with (
        w.open_table(path, readonly=False) as t,
        pytest.raises(OSError, match="cannot remove"),
    ):
        t.removerows([1])


def test_incremental_string_arrays(tmp_path):
    path = tmp_path / "ism"
    cols = [w.makearrcoldesc("SV", "", ndim=1), w.makearrcoldesc("SF", "", shape=[2])]
    dm = {
        "*1": {
            "TYPE": "IncrementalStMan",
            "NAME": "ISM",
            "SPEC": {},
            "COLUMNS": ["SV", "SF"],
        }
    }
    big = [f"s{i}" for i in range(5000)]
    with w.create_table(path, w.maketabdesc(cols), nrow=4, dminfo=dm) as t:
        t.putcell("SV", 0, big)
        t.putcell("SV", 2, ["a", "", "ccc"])
        t.putcol("SF", np.array([["p", "q"]] * 4))
        t.putcell("SF", 3, ["x", "yy"])
    sv = cells(path, "SV", 4)
    # A value put on the last row put holds for the rows after it.
    assert list(sv[0]) == big and list(sv[1]) == big
    assert list(sv[2]) == ["a", "", "ccc"] and list(sv[3]) == ["a", "", "ccc"]
    assert [list(x) for x in cells(path, "SF", 4)] == [["p", "q"]] * 3 + [["x", "yy"]]


def test_multifile_continuation_and_free_blocks(tmp_path):
    path = tmp_path / "mf"
    cols = [w.makescacoldesc("I", 0), w.makearrcoldesc("V", 0.0, ndim=1)]
    dm = {
        "*1": {
            "TYPE": "StandardStMan",
            "NAME": "A",
            "SPEC": {"BUCKETSIZE": 512, "PERSCACHESIZE": 2},
            "COLUMNS": ["I", "V"],
        }
    }
    n = 300
    with w.create_table(
        path, w.maketabdesc(cols), nrow=n, dminfo=dm, multifile=512
    ) as t:
        t.putcol("I", np.arange(n, dtype=np.int32))
        for r in range(n):
            t.putcell("V", r, np.arange(1 + r % 7, dtype=float))
        t.flush()
        t.removerows(list(range(n)))
        t.addrows(20)
        t.putcol("I", np.arange(20, dtype=np.int32))
    assert core.extension().ms_multifile_check(str(path)) == []
    head = (path / "table.mf").read_bytes()[:64]
    assert int.from_bytes(head[40:48], "big") == 512
    assert [int(x) for x in cells(path, "I", 20)] == list(range(20))


def test_multihdf5_and_other_managers_are_not_supported(tmp_path):
    arr = w.makearrcoldesc("A", 0.0, shape=[4], valuetype="float")
    with pytest.raises(ValueError, match="MultiHDF5 tables are not supported"):
        w.create_table(tmp_path / "h5", [arr], 3, multifile="multihdf5")
    other = {"*1": {"TYPE": "Adios2StMan", "NAME": "X", "SPEC": {}, "COLUMNS": ["A"]}}
    with pytest.raises(OSError, match="not supported"):
        w.create_table(tmp_path / "ad", [arr], 3, other)
    assert not (tmp_path / "h5" / "table.dat").exists()


def test_two_dimensional_array_keywords_in_c_order(tmp_path):
    """W4-4: a 2x3 string keyword is stored a,b,c,d,e,f (python-casacore)."""
    path = tmp_path / "kw"
    with w.create_table(path, [w.makescacoldesc("I", 0)], nrow=1) as t:
        t.putkeyword("S", np.array([["a", "b", "c"], ["d", "e", "f"]]))
    dat = (path / "table.dat").read_bytes()
    order = [dat.find(f"\x00\x00\x00\x01{c}".encode()) for c in "abcdef"]
    assert all(x > 0 for x in order) and order == sorted(order)


def test_archived_check_passes_when_present():
    runs = sorted((ROOT / "outputs").glob("e6-*-01/result.json"))
    archive = ROOT / "research" / "results" / "e6-table-writer-final.json"
    if not runs or not archive.exists():
        pytest.skip("no E6 oracle run on disk")
    assert json.loads(runs[-1].read_text()) == json.loads(archive.read_text())["result"]
