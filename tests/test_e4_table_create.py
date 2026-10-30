"""Table creation, rows, string arrays, default_ms and caltables (E4).

research/e4-table-create.md. These tests use only the core (they skip when
the extension lacks the E4 calls); the byte comparisons against casacore
3.8.1 and CASA 6.7.6 need Docker and the oracle images and are made by
`examples/check_ms_create.py`; their archived verdict is checked when the
run directory is present.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms_write as w

pytestmark = pytest.mark.skipif(
    not (w.has_writer() and w.has_creator()),
    reason="extension without the E4 table creation",
)

ROOT = Path(__file__).resolve().parents[1]


def test_new_table_values_read_back(tmp_path):
    path = tmp_path / "t"
    cols = [
        w.makescacoldesc("I", 0),
        w.makescacoldesc("S", ""),
        w.makearrcoldesc("D", 0.0, shape=[3], options=1),
        w.makearrcoldesc("V", 0.0, ndim=1, valuetype="float"),
        w.makearrcoldesc("SA", "", ndim=1),
        w.makearrcoldesc("SD", "", shape=[2], options=1),
    ]
    t = w.create_table(path, cols, nrow=5)
    t.putcol("I", np.arange(5, dtype=np.int32))
    t.putcol("S", ["", "a", "abcdefghij", "x" * 300, "z"])
    t.putcol("D", np.arange(15.0).reshape(5, 3))
    for row in (0, 2, 4):
        t.putcell("V", row, np.arange(row + 1, dtype=np.float32))
    for row in range(5):
        t.putcell("SA", row, np.array(["s"] * row))
    t.putcol("SD", np.array([["p", "q" * r] for r in range(5)]))
    t.putinfo({"type": "Test", "subType": "e4", "readme": "one"})
    t.putkeyword("K", 1.5)
    t.close()
    assert (path / "table.info").read_text() == "Type = Test\nSubType = e4\n\none\n"
    assert np.array_equal(w.read_cells(path, "I", 0, 5)[3], np.int32(3))
    v = w.read_cells(path, "V", 0, 5)
    assert v[1] is None and v[3] is None
    assert np.array_equal(v[4], np.arange(5, dtype=np.float32))
    sa = w.read_cells(path, "SA", 0, 5)
    assert list(sa[3]) == ["s"] * 3 and sa[0].shape == (0,)
    assert list(w.read_cells(path, "SD", 4, 1)[0]) == ["p", "qqqq"]
    with w.open_table(path) as r:
        assert list(r.getcol("S")) == ["", "a", "abcdefghij", "x" * 300, "z"]


def test_rows_are_added_and_removed(tmp_path):
    path = tmp_path / "t"
    cols = [
        w.makescacoldesc("I", 0),
        w.makescacoldesc("B", False),
        w.makescacoldesc("S", ""),
    ]
    t = w.create_table(path, cols, nrow=40)
    t.putcol("I", np.arange(40, dtype=np.int32))
    t.putcol("B", np.arange(40) % 3 == 0)
    t.putcol("S", [f"row {i} " * (i % 4) for i in range(40)])
    t.addrows(30)
    t.putcol("I", np.arange(40, 70, dtype=np.int32), 40, 30)
    t.putcol("B", np.arange(40, 70) % 3 == 0, 40, 30)
    t.putcol("S", [f"row {i} " * (i % 4) for i in range(40, 70)], 40, 30)
    t.removerows([0, 5, 69, 33])
    t.close()
    keep = [i for i in range(70) if i not in (0, 5, 33, 69)]
    with w.open_table(path) as r:
        assert r.nrows == 66
        assert list(r.getcol("I")) == keep
        assert list(r.getcol("B")) == [i % 3 == 0 for i in keep]
        assert list(r.getcol("S")) == [f"row {i} " * (i % 4) for i in keep]


def test_tiled_tables_extend_and_refuse_removal(tmp_path):
    path = tmp_path / "t"
    cols = [w.makearrcoldesc("DATA", 0j, shape=[16, 4], valuetype="complex")]
    dminfo = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "T",
            "SPEC": {"DEFAULTTILESHAPE": [4, 8, 8]},
            "COLUMNS": ["DATA"],
        }
    }
    data = (np.arange(10 * 64) * (1 + 1j)).astype(np.complex64).reshape(10, 16, 4)
    t = w.create_table(path, cols, nrow=4, dminfo=dminfo)
    t.addrows(6)
    t.putcol("DATA", data)
    with pytest.raises(OSError, match="cannot remove rows"):
        t.removerows([0])
    t.close()
    with w.open_table(path) as r:
        assert np.array_equal(r.getcol("DATA"), data)


@pytest.mark.parametrize("kind", ["IncrementalStMan", "MemoryStMan", "TiledDataStMan"])
def test_deferred_managers_refuse_with_e5(tmp_path, kind):
    cols = [w.makescacoldesc("I", 0)]
    dminfo = {"*1": {"TYPE": kind, "NAME": "X", "SPEC": {}, "COLUMNS": ["I"]}}
    with pytest.raises(OSError, match="E5"):
        w.create_table(tmp_path / "t", cols, nrow=2, dminfo=dminfo)
    assert not (tmp_path / "t" / "table.dat").exists()


def test_variable_tiled_big_endian_and_multifile_refuse(tmp_path):
    var = [w.makearrcoldesc("V", 0.0, ndim=1)]
    dminfo = {
        "*1": {
            "TYPE": "TiledShapeStMan",
            "NAME": "T",
            "SPEC": {"DEFAULTTILESHAPE": [4, 8]},
            "COLUMNS": ["V"],
        }
    }
    with pytest.raises(OSError, match="E5"):
        w.create_table(tmp_path / "a", var, 1, dminfo)
    with pytest.raises(OSError, match="E5"):
        w.create_table(tmp_path / "b", [w.makescacoldesc("I", 0)], 1, endian="big")
    with pytest.raises(OSError, match="E5"):
        w.create_table(tmp_path / "c", [w.makescacoldesc("I", 0)], 1, multifile=True)


def test_default_ms_has_the_subtables_and_info(tmp_path):
    path = tmp_path / "x.ms"
    w.default_ms(path).close()
    names = sorted(p.parent.name for p in path.glob("*/table.dat"))
    assert names == sorted(
        [
            "ANTENNA",
            "DATA_DESCRIPTION",
            "FEED",
            "FIELD",
            "FLAG_CMD",
            "HISTORY",
            "OBSERVATION",
            "POINTING",
            "POLARIZATION",
            "PROCESSOR",
            "SPECTRAL_WINDOW",
            "STATE",
        ]
    )
    assert (path / "table.info").read_text().startswith("Type = Measurement Set\n")
    with w.open_table(path) as r:
        assert r.nrows == 0 and "DATA" not in r.columns and "UVW" in r.columns
    with pytest.raises(OSError, match="E5"):
        t = w.open_table(path / "POINTING", readonly=False)
        try:
            t.addrows(1)
        finally:
            t.close()


def test_caltable_is_written_and_read(tmp_path):
    path = tmp_path / "x.G"
    gains = [np.array([[1 + 1j, 2 - 1j]], np.complex64) for _ in range(3)]
    main = {
        "TIME": [5e9, 5e9, 5e9],
        "FIELD_ID": [0, 0, 0],
        "SPECTRAL_WINDOW_ID": [0, 0, 0],
        "ANTENNA1": [2, 0, 1],
        "ANTENNA2": [0, 0, 0],
        "INTERVAL": [0.0] * 3,
        "SCAN_NUMBER": [1] * 3,
        "OBSERVATION_ID": [0] * 3,
        "CPARAM": gains,
        "PARAMERR": [np.zeros((1, 2), np.float32)] * 3,
        "FLAG": [np.zeros((1, 2), bool)] * 3,
        "SNR": [np.ones((1, 2), np.float32)] * 3,
        "WEIGHT": [None] * 3,
    }
    ant = {"NAME": ["a", "b", "c"], "POSITION": [np.zeros(3)] * 3}
    w.create_caltable(path, "G Jones", main, {"ANTENNA": ant}, "x.ms")
    assert (
        path / "table.info"
    ).read_text() == "Type = Calibration\nSubType = G Jones\n\n"
    assert [int(x) for x in w.read_cells(path, "ANTENNA1", 0, 3)] == [0, 1, 2]
    assert w.read_cells(path, "WEIGHT", 0, 3) == [None, None, None]
    with w.open_table(path / "ANTENNA") as r:
        assert list(r.getcol("NAME")) == ["a", "b", "c"]
    with pytest.raises(ValueError, match="duplicate"):
        main["ANTENNA1"] = [0, 0, 1]
        w.create_caltable(tmp_path / "y.G", "G Jones", main, {}, "x.ms")


def test_archived_check_passes_when_present():
    result = ROOT / "outputs" / "e4-20261030-01" / "result.json"
    if not result.exists():
        pytest.skip("no E4 check run in outputs/")
    assert json.loads(result.read_text())["all_pass"] is True
