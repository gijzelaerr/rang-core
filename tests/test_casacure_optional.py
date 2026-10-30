"""casacure (optional) against the task E oracle dump and the core reader.

research/casacure-evaluation.md (task E2). casacure is not a dependency of
rang; these tests skip when it is not installed, and, like
`tests/test_core_ms.py`, when the oracle dump or the MSs in ignored
`outputs/` are absent. They pin the two behaviours the evaluation relies on:
casacure reads the fixture and LUNO MSs column-exactly, and a table written
by casacure reads back through `rangtoy.core_ms` unchanged.
"""

import json
from pathlib import Path

import numpy as np
import pytest

ct = pytest.importorskip("casacure.tables")

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "outputs/core-e-oracle-20261029-01"


def _table(label):
    if not (ORACLE / "receipt.json").is_file():
        pytest.skip("oracle dump not present")
    receipt = json.loads((ORACLE / "receipt.json").read_text())
    entry = receipt["tables"][label]
    path = ROOT / "outputs" / Path(*Path(entry["path"]).parts[2:])
    if not path.is_dir():
        pytest.skip(f"{path} not present")
    return path, entry


def _bytes_equal(actual, expected):
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.dtype == expected.dtype
    assert actual.shape == expected.shape
    assert np.array_equal(
        np.ascontiguousarray(actual).view(np.uint8),
        np.ascontiguousarray(expected).view(np.uint8),
    )


@pytest.mark.parametrize("label", ["ms0", "ms1"])
def test_casacure_reads_equal_the_oracle(label):
    path, entry = _table(label)
    arrays = np.load(ORACLE / f"{label}.npz")
    table = ct.table(str(path), ack=False)
    try:
        assert table.nrows() == entry["nrows"]
        for name in ("TIME", "ANTENNA1", "UVW", "DATA", "FLAG", "WEIGHT_SPECTRUM"):
            _bytes_equal(table.getcol(name), arrays[name])
        _bytes_equal(table.getcol("DATA", 3, 2), arrays["DATA"][3:5])
    finally:
        table.close()
    strings = json.loads((ORACLE / f"{label}.ANTENNA.strings.json").read_text())
    antenna = ct.table(str(path / "ANTENNA"), ack=False)
    try:
        # A list of str, as python-casacore returns string columns.
        assert list(antenna.getcol("NAME")) == strings["NAME"]
    finally:
        antenna.close()


def test_casacure_write_reads_back_through_core_ms(tmp_path):
    core_ms = pytest.importorskip("rangtoy.core_ms")
    if not core_ms.has_reader():
        pytest.skip("core library built without the Measurement Set reader")
    rng = np.random.default_rng(20261030)
    data = (rng.normal(size=(5, 8, 4)) + 1j * rng.normal(size=(5, 8, 4))).astype(
        np.complex64
    )
    flag = rng.random((5, 8, 4)) < 0.3
    time = np.arange(5, dtype=np.float64) * 8.0
    desc = ct.maketabdesc(
        [
            ct.makescacoldesc("TIME", 0.0),
            ct.makearrcoldesc("DATA", 0j, ndim=2, shape=[8, 4], valuetype="complex"),
            ct.makearrcoldesc("FLAG", False, ndim=2, shape=[8, 4]),
        ]
    )
    table = ct.table(str(tmp_path / "t.tab"), desc, nrow=5)
    try:
        table.putcol("TIME", time)
        table.putcol("DATA", data)
        table.putcol("FLAG", flag)
        table.flush()
    finally:
        table.close()
    with core_ms.open_table(tmp_path / "t.tab") as back:
        _bytes_equal(back.getcol("TIME"), time)
        _bytes_equal(back.getcol("DATA"), data)
        _bytes_equal(back.getcol("FLAG"), flag)
