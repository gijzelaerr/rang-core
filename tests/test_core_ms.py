"""The core Measurement Set reader against the python-casacore oracle dump.

The oracle (`outputs/core-e-oracle-20261029-01`, research/core-e-ms-reader.md)
and the MSs it reads live in ignored `outputs/`; the tests skip when they or
the reader symbols are absent, so they run after the coordinator adds the
module lines to `core/src/lib.rs`.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core_ms

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "outputs/core-e-oracle-20261029-01"


def _skip_unless_available():
    if not core_ms.has_reader():
        pytest.skip("core library built without the Measurement Set reader")
    if not (ORACLE / "receipt.json").is_file():
        pytest.skip("oracle dump not present")


def _table(label):
    receipt = json.loads((ORACLE / "receipt.json").read_text())
    entry = receipt["tables"][label]
    path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
    if not path.is_dir():
        pytest.skip(f"{path} not present")
    return path, entry


@pytest.mark.parametrize("label", ["ms0", "ms1"])
def test_main_columns_equal_the_oracle(label):
    _skip_unless_available()
    path, entry = _table(label)
    arrays = np.load(ORACLE / f"{label}.npz")
    with core_ms.open_table(path) as table:
        assert table.nrows == entry["nrows"]
        for name in (
            "TIME",
            "ANTENNA1",
            "UVW",
            "DATA",
            "FLAG",
            "FLAG_ROW",
            "WEIGHT_SPECTRUM",
        ):
            expected = arrays[name]
            actual = table.getcol(name)
            assert actual.dtype == expected.dtype
            assert actual.shape == expected.shape
            assert np.array_equal(actual.view(np.uint8), expected.view(np.uint8))
        assert np.array_equal(table.getcol("DATA", 3, 2), arrays["DATA"][3:5])


def test_subtable_strings_and_arrays():
    _skip_unless_available()
    path, _ = _table("ms1")
    strings = json.loads((ORACLE / "ms1.ANTENNA.strings.json").read_text())
    arrays = np.load(ORACLE / "ms1.ANTENNA.npz")
    with core_ms.open_table(path).subtable("ANTENNA") as antenna:
        assert antenna.getcol("NAME").tolist() == strings["NAME"]
        np.testing.assert_array_equal(antenna.getcol("POSITION"), arrays["POSITION"])


def test_errors_are_reported():
    _skip_unless_available()
    path, _ = _table("ms1")
    with pytest.raises(OSError):
        core_ms.open_table(path / "no-such-table")
    with core_ms.open_table(path) as table:
        with pytest.raises(OSError, match="does not exist"):
            table.getcol("NO_SUCH_COLUMN")
        with pytest.raises(OSError, match="exceed"):
            table.getcol("TIME", table.nrows, 1)
