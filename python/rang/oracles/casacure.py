"""casacure as a read-only second oracle for the core's casacore tables.

research/t1-casacure-ci.md (task T1), after research/casacure-evaluation.md
(task E2, verdict (c)): casacure (Tim Molteno's pure-Rust casacore tables,
LGPL-3.0-or-later) reads every column we have column-exactly, on Linux,
Windows and macOS, but its writes are not trusted, so this adapter exposes
reads only. It returns values in the conventions of `rang.core_ms`: one
leading row axis, then the cell axes in reversed casacore order (as
python-casacore), string columns as object arrays, string-array columns as
object arrays of the column's shape, per-row cells (`getcells`) as a list.

The pin is exact (`casacure==3.8.35`, the `casacure` extra): casacure
releases often and has changed behaviour between patch releases, so any
other installed version is refused. casacure memory-maps table files: close
a table before anything writes the same files (a file shrunk under the
mapping kills the process with SIGBUS, E2 candidate 4; Windows refuses
writes to a mapped file).
"""

from importlib import metadata

import numpy as np

PIN = "3.8.35"


def installed_version():
    """The installed casacure version, or None."""
    try:
        return metadata.version("casacure")
    except metadata.PackageNotFoundError:
        return None


def available():
    """True when the pinned casacure is installed."""
    return installed_version() == PIN


def _tables():
    version = installed_version()
    if version != PIN:
        raise RuntimeError(
            f"casacure {version} installed, the oracle is pinned to {PIN}"
        )
    import casacure.tables

    return casacure.tables


def _plain(value):
    """Keyword values as plain Python: NumPy scalars to Python scalars,
    arrays to (nested) lists, records recursively."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _strings(value):
    """A string column or string-array record as an object array."""
    if isinstance(value, dict):  # {'shape': [nrow, ...], 'array': [...]}
        shape = tuple(int(n) for n in value["shape"])
        return np.asarray(list(value["array"]), dtype=object).reshape(shape)
    return np.asarray(list(value), dtype=object)


class Table:
    """A casacore table opened read-only by casacure."""

    def __init__(self, path):
        self.path = path
        self._table = _tables().table(str(path), readonly=True, ack=False)

    def close(self):
        if self._table is not None:
            self._table.close()
            self._table = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def nrows(self):
        return int(self._table.nrows())

    def colnames(self):
        return list(self._table.colnames())

    def coldesc(self, name):
        return _plain(self._table.getcoldesc(name))

    def is_string(self, name):
        return self._table.getcoldesc(name)["valueType"] == "string"

    def getcol(self, name, startrow=0, nrow=None):
        """Rows `startrow` onwards (all, or `nrow` of them) of one column."""
        if nrow is None:
            value = self._table.getcol(name, int(startrow))
        else:
            value = self._table.getcol(name, int(startrow), int(nrow))
        if self.is_string(name):
            return _strings(value)
        return np.asarray(value)

    def getcells(self, name, startrow=0, nrow=None):
        """One entry per row (any cell shape), as python-casacore's
        `getvarcol`; string cells as object arrays."""
        count = self.nrows - int(startrow) if nrow is None else int(nrow)
        record = self._table.getvarcol(name, int(startrow), count)
        # Keys are r1, r2, ... (casacure 3.8.35 counts from the first row
        # read; python-casacore from row 0): take them in numeric order.
        keys = sorted(record, key=lambda k: int(k[1:]))
        if len(keys) != count:
            raise RuntimeError(
                f"{name}: getvarcol returned {len(keys)} of {count} rows"
            )
        cells = [record[k] for k in keys]
        if self.is_string(name):
            return [np.asarray(list(c), dtype=object) for c in cells]
        return [np.asarray(c) for c in cells]

    def keywords(self):
        return _plain(self._table.getkeywords())

    def colkeywords(self, name):
        return _plain(self._table.getcolkeywords(name))

    def subtables(self):
        """{keyword: target path} of the table's `Table:` keywords."""
        return {
            key: value[len("Table: ") :]
            for key, value in self.keywords().items()
            if isinstance(value, str) and value.startswith("Table: ")
        }

    def managers(self):
        """{column: data manager TYPE} from `getdminfo`."""
        out = {}
        for info in self._table.getdminfo().values():
            for column in info["COLUMNS"]:
                out[column] = info["TYPE"]
        return out


def open_table(path):
    return Table(path)
