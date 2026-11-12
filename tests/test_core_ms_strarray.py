"""String-array columns read by the core table reader against python-casacore.

`tests/data/strarray` is a casacore table written by python-casacore 3.8.1
(`tools/oracles/strarray/fixture.py`), with `oracle.json` holding every cell as
python-casacore's `getcell` returns it. Its POLARIZATION_TYPE column is laid
out as in a MeerKAT MS's FEED table, which the reader once failed on with a
read at a garbage offset (research/feed-poltype-read.md).
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from rang import core_ms

DATA = Path(__file__).resolve().parent / "data" / "strarray"
ORACLE = json.loads((DATA / "oracle.json").read_text(encoding="utf-8"))
COLUMNS = list(ORACLE["columns"])
UNIFORM = ["POLARIZATION_TYPE", "FIXED", "DIRECT", "NAME", "UNSET_FIXED"]


@pytest.fixture
def table():
    if not core_ms.has_reader():
        pytest.skip("core library built without the Measurement Set reader")
    with core_ms.open_table(DATA / "table") as t:
        yield t


def _cell(entry):
    return np.asarray(entry["values"], dtype=object).reshape(entry["shape"])


@pytest.mark.parametrize("name", COLUMNS)
def test_every_cell_equals_casacore(table, name):
    assert table.nrows == ORACLE["nrows"]
    for row, entry in enumerate(ORACLE["columns"][name]):
        if entry is None:  # undefined in casacore: refused, not invented
            with pytest.raises(OSError, match="has no array"):
                table.getcol(name, row, 1)
            continue
        got = table.getcol(name, row, 1)
        want = _cell(entry)
        assert got.shape == (1,) + want.shape, (name, row)
        assert got.tolist() == [want.tolist()], (name, row)


@pytest.mark.parametrize("name", UNIFORM)
def test_whole_columns_equal_casacore(table, name):
    want = np.stack([_cell(e) for e in ORACLE["columns"][name]])
    got = table.getcol(name)
    assert got.shape == want.shape
    assert got.tolist() == want.tolist()
    rows = [7, 2, 3, 11, 0]
    assert table.getcol_rows(name, rows).tolist() == want[rows].tolist()


def test_feed_like_polarization_type(table):
    got = table.getcol("POLARIZATION_TYPE")
    assert got.shape == (12, 2)
    assert got[1].tolist() == ["X", "Y"] and got[0].tolist() == ["R", "L"]


def test_strings_across_buckets(table):
    # LONG's first strings (300 to 707 characters) exceed the 512-byte bucket.
    got = table.getcol("LONG", 11, 1)[0]
    assert len(got[0]) == 300 + 37 * 11 and got[1] == "t11"


def test_mixed_shapes_and_other_managers_refuse_cleanly(table):
    with pytest.raises(OSError, match="differ in shape"):
        table.getcol("VAR", 0, 2)
    with pytest.raises(OSError, match="IncrementalStMan array or string"):
        table.getcol("INCR")


def test_polarisation_basis_refuses_circular_feeds(table, tmp_path):
    from rang import cal_pol

    shutil.copytree(DATA / "table", tmp_path / "ms" / "FEED")
    types = cal_pol.feed_types(tmp_path / "ms")
    assert types[0] == ("R", "L") and types[1] == cal_pol.LINEAR_FEEDS
    with pytest.raises(ValueError, match=r"\[\['R', 'L'\]\]; P is"):
        cal_pol.receptor_angles(tmp_path / "ms")


def test_undefined_cells_row_by_row(table):
    from rang import cal_pol

    want = [
        None if e is None else tuple(e["values"])
        for e in ORACLE["columns"]["UNSET_VAR"]
    ]
    assert want[0] is None and want[1] == ("u1",)
    assert cal_pol._cells(table, "UNSET_VAR") == want
