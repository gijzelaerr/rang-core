"""Measurement Set reads at the edge of the Rang core (research/core-e-ms-reader.md).

Opens casacore tables read-only through the core's Rust reader and returns
columns as python-casacore's `getcol` does: one leading row axis, then the
cell axes in reversed casacore order, NumPy dtypes `bool`, `int32`,
`float32`, `float64`, `complex64` and friends, and string columns as object
arrays. Only StandardStMan, IncrementalStMan (scalars), TiledShapeStMan and
TiledColumnStMan columns are readable; the description says which. The core
is reached through the extension's `MsTable` (research/core-j-packaging.md;
the C ABI handle path was removed by task P7, research/p7-architecture.md).
"""

import json
from pathlib import Path

import numpy as np

from . import core

DTYPES = {
    0: np.dtype("bool"),
    1: np.dtype("int8"),
    2: np.dtype("uint8"),
    3: np.dtype("int16"),
    4: np.dtype("uint16"),
    5: np.dtype("int32"),
    6: np.dtype("uint32"),
    7: np.dtype("float32"),
    8: np.dtype("float64"),
    9: np.dtype("complex64"),
    10: np.dtype("complex128"),
    29: np.dtype("int64"),
}
STRING = 11


def has_reader():
    """True when the extension exposes the Measurement Set reader."""
    return hasattr(core.extension(), "MsTable")


def _decode(raw, nrows, cell, dtype, nstrings):
    """A column's packed bytes (a uint8 array that owns its memory) as
    python-casacore's `getcol` returns them, without a copy."""
    shape = (int(nrows),) + tuple(cell)[::-1]
    if dtype == STRING:
        packed, strings, at = raw.tobytes(), [], 0
        for _ in range(nstrings):
            n = int.from_bytes(packed[at : at + 4], "little")
            strings.append(packed[at + 4 : at + 4 + n].decode("utf-8"))
            at += 4 + n
        return np.asarray(strings, dtype=object).reshape(shape)
    return raw.view(DTYPES[dtype]).reshape(shape)


class Table:
    """An open casacore table; use as a context manager or call `close`."""

    def __init__(self, path):
        self.path = Path(path)
        self._table = core.extension().MsTable(str(self.path))
        self.description = json.loads(self._table.describe())
        self.nrows = int(self.description["nrows"])
        self.columns = {c["name"]: c for c in self.description["columns"]}

    def close(self):
        self._table = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def colnames(self):
        return list(self.columns)

    def subtable(self, name):
        return Table(self.path / name)

    def getcol(self, name, startrow=0, nrow=None):
        """Rows `startrow` onwards (all, or `nrow` of them) of one column."""
        if self._table is None:
            raise ValueError("table is closed")
        count = 0 if nrow is None else int(nrow)
        if nrow is not None and count <= 0:
            raise ValueError("nrow must be positive")
        raw, nrows, cell, dtype, nstrings = self._table.read(name, int(startrow), count)
        return _decode(raw, nrows, cell, dtype, nstrings)


def open_table(path):
    return Table(path)
