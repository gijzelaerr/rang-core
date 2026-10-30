"""Writes into existing casacore tables at the edge of the Rang core.

research/e3-table-writer.md. `open_table(path, readonly=False)` returns a
`Table` that holds casacore's write lock on `table.lock` until `close()` (or
the end of a `with` block) and writes as casacore 3.8.1 does: `putcol` and
`putcell` of StandardStMan, TiledColumnStMan and TiledShapeStMan columns,
table and column keywords, and `addcols` into the first StandardStMan (the
python-casacore default binding) or as a new tiled data manager. Values are
given as python-casacore takes them: one leading row axis, then the cell
axes in reversed casacore order. Everything is written on `flush()` and on
close, once, as casacore flushes; reads (`getcol`) go through
`rang.core_ms` and see what has been flushed.

A separate module from `core_ms` so that the task E reader stays unchanged.
Not done here (E4/E5): new tables, adding rows, IncrementalStMan writes,
string arrays, big-endian tables.
"""

from pathlib import Path

import numpy as np

from . import core, core_ms

CODES = {
    np.dtype("bool"): 0,
    np.dtype("int8"): 1,
    np.dtype("uint8"): 2,
    np.dtype("int16"): 3,
    np.dtype("uint16"): 4,
    np.dtype("int32"): 5,
    np.dtype("uint32"): 6,
    np.dtype("float32"): 7,
    np.dtype("float64"): 8,
    np.dtype("complex64"): 9,
    np.dtype("complex128"): 10,
    np.dtype("int64"): 29,
}
STRING = 11
VALUETYPES = {
    "bool": 0,
    "boolean": 0,
    "uchar": 2,
    "byte": 2,
    "short": 3,
    "ushort": 4,
    "int": 5,
    "integer": 5,
    "uint": 6,
    "float": 7,
    "double": 8,
    "complex": 9,
    "dcomplex": 10,
    "string": 11,
    "int64": 29,
}
MANAGERS = {"TiledColumnStMan": 1, "TiledShapeStMan": 2, "StandardStMan": 3}


def has_writer():
    """True when the extension exposes the table writer."""
    return hasattr(core.extension(), "MsWriter")


def _value_type(value):
    if isinstance(value, str):
        return "string"
    dtype = np.asarray(value).dtype
    if dtype.kind in "US":
        return "string"
    names = {
        v: k for k, v in VALUETYPES.items() if k not in ("boolean", "byte", "integer")
    }
    return names[CODES[dtype]]


def makescacoldesc(
    columnname,
    value,
    datamanagertype="",
    datamanagergroup="",
    options=0,
    maxlen=0,
    comment="",
    valuetype="",
):
    """A scalar column description, as python-casacore's function of the name;
    `value` is the column's default value."""
    vtype = valuetype or _value_type(value)
    return {
        "name": columnname,
        "desc": {
            "valueType": vtype,
            "default": value,
            "dataManagerType": datamanagertype,
            "dataManagerGroup": datamanagergroup,
            "option": options,
            "maxlen": maxlen,
            "comment": comment,
        },
    }


def makearrcoldesc(
    columnname,
    value,
    ndim=0,
    shape=(),
    datamanagertype="",
    datamanagergroup="",
    options=0,
    maxlen=0,
    comment="",
    valuetype="",
):
    """An array column description, as python-casacore's function of the
    name: a shape (NumPy order) forces FixedShape, Direct forces it too."""
    vtype = valuetype or _value_type(value)
    shape = [int(s) for s in shape]
    if shape and ndim <= 0:
        ndim = len(shape)
    return {
        "name": columnname,
        "desc": {
            "valueType": vtype,
            "ndim": ndim,
            "shape": shape,
            "dataManagerType": datamanagertype,
            "dataManagerGroup": datamanagergroup,
            "option": options,
            "maxlen": maxlen,
            "comment": comment,
            "_c_order": True,
        },
    }


def maketabdesc(descs):
    """A table description: a list of column descriptions."""
    return list(descs) if isinstance(descs, (list, tuple)) else [descs]


def _canonical_default(code, value):
    if code == STRING:
        b = str(value).encode()
        return list(len(b).to_bytes(4, "big") + b)
    dtype = next(d for d, c in CODES.items() if c == code)
    v = np.asarray(value, dtype=dtype)
    if code in (9, 10):
        part = np.dtype(">f4") if code == 9 else np.dtype(">f8")
        return list(np.array([v.real, v.imag], dtype=part).tobytes())
    return list(v.astype(dtype.newbyteorder(">")).tobytes())


class Table:
    """A casacore table open for writing; use as a context manager."""

    def __init__(self, path, lock_attempts=10, lock_wait=1.0):
        self.path = Path(path)
        # Describe the table before taking the lock: the reader opens and
        # closes table.lock, which would drop a lock already held (POSIX).
        with core_ms.open_table(self.path) as reader:
            self._columns = {name: dict(c) for name, c in reader.columns.items()}
        self._writer = core.extension().MsWriter(
            str(self.path), int(lock_attempts), int(lock_wait * 1000)
        )

    # -- bookkeeping ---------------------------------------------------------
    def nrows(self):
        return int(self._writer.nrows())

    def colnames(self):
        return list(self._columns)

    def _code(self, name):
        try:
            dtype = self._columns[name]["dtype"]
        except KeyError:
            raise ValueError(f"column {name} does not exist") from None
        return STRING if dtype == "str" else CODES[np.dtype(dtype)]

    # -- data ----------------------------------------------------------------
    def putcol(self, columnname, value, startrow=0, nrow=-1):
        """Write rows `startrow` onwards (all of `value`'s rows)."""
        code = self._code(columnname)
        is_array = self._columns[columnname]["is_array"]
        if code == STRING:
            values = np.asarray(value, dtype=object).reshape(-1)
            if nrow is not None and nrow >= 0:
                values = values[:nrow]
            self._writer.put_strings(
                columnname, int(startrow), [str(v) for v in values]
            )
            return
        dtype = next(d for d, c in CODES.items() if c == code)
        arr = np.ascontiguousarray(value, dtype=dtype)
        if nrow is not None and nrow >= 0:
            arr = arr[:nrow]
        cell = list(arr.shape[1:])[::-1] if is_array else []
        if not is_array and arr.ndim != 1:
            raise ValueError(f"{columnname}: scalar column needs a 1-D array")
        count = arr.shape[0]
        if count == 0:
            return
        self._writer.put(
            columnname, int(startrow), int(count), cell, arr.reshape(-1).view(np.uint8)
        )

    def putcell(self, columnname, rownr, value):
        """Write one row."""
        if self._code(columnname) == STRING:
            self.putcol(columnname, [value], rownr, 1)
        elif self._columns[columnname]["is_array"]:
            self.putcol(columnname, np.asarray(value)[None, ...], rownr, 1)
        else:
            self.putcol(columnname, np.asarray([value]), rownr, 1)

    def getcol(self, columnname, startrow=0, nrow=None):
        """Flush, then read with the core reader through the writer (an
        extra flush that python-casacore would not do). Opening the table
        with `core_ms` or python-casacore in this process instead would
        close a descriptor of `table.lock` and so drop this process's lock
        (POSIX); the writer re-takes it before writing."""
        count = 0 if nrow is None else int(nrow)
        raw, nrows, cell, dtype, nstrings = self._writer.read(
            columnname, int(startrow), count
        )
        return core_ms._decode(raw, nrows, cell, dtype, nstrings)

    # -- keywords --------------------------------------------------------------
    def _put_keyword(self, column, path, value):
        if isinstance(value, dict):
            self._writer.put_keyword(column, path, 4, 0, [], b"", [])
            for key, sub in value.items():
                self._put_keyword(column, path + [key], sub)
            return
        if isinstance(value, str):
            self._writer.put_keyword(column, path, 1, 0, [], value.encode(), [])
            return
        if isinstance(value, bool):
            value = np.bool_(value)
        elif isinstance(value, int):
            value = np.int32(value) if -(2**31) <= value < 2**31 else np.int64(value)
        elif isinstance(value, float):
            value = np.float64(value)
        elif isinstance(value, complex):
            value = np.complex128(value)
        arr = np.asarray(value)
        if arr.dtype.kind in "USO":
            strings = [str(s) for s in arr.reshape(-1, order="F")]
            self._writer.put_keyword(
                column, path, 3, STRING, list(arr.shape)[::-1], b"", strings
            )
            return
        code = CODES[arr.dtype]
        if arr.ndim == 0:
            self._writer.put_keyword(column, path, 0, code, [], arr.tobytes(), [])
        else:
            data = np.ascontiguousarray(arr).tobytes()
            self._writer.put_keyword(
                column, path, 2, code, list(arr.shape)[::-1], data, []
            )

    def putkeyword(self, keyword, value):
        """Define a table keyword; `a.b` names field `b` of sub-record `a`."""
        self._put_keyword(None, keyword.split("."), value)

    def putcolkeyword(self, columnname, keyword, value):
        self._put_keyword(columnname, keyword.split("."), value)

    def removekeyword(self, keyword):
        self._writer.remove_keyword(None, keyword.split("."))

    def removecolkeyword(self, columnname, keyword):
        self._writer.remove_keyword(columnname, keyword.split("."))

    # -- columns ---------------------------------------------------------------
    def addcols(self, desc, dminfo=None):
        """Add columns: without `dminfo` they go to the first StandardStMan
        as python-casacore binds them; with `dminfo` (`TYPE` StandardStMan,
        TiledColumnStMan or TiledShapeStMan, `NAME`, `SPEC`) to a new data
        manager. As in python-casacore, `DEFAULTTILESHAPE` is taken as given,
        in casacore axis order (rows last); a tiled column needs a shape."""
        manager, name, tile = 0, "", []
        if dminfo:
            if dminfo.get("TYPE") not in MANAGERS:
                raise ValueError(f"data manager {dminfo.get('TYPE')} is not added (E4)")
            manager = MANAGERS[dminfo["TYPE"]]
            name = dminfo["NAME"]
            spec = dminfo.get("SPEC", {})
            if manager == 3:
                tile = [
                    int(spec.get(k, 0))
                    for k in ("BUCKETROWS", "BUCKETSIZE", "PERSCACHESIZE")
                ]
            else:
                # python-casacore passes DEFAULTTILESHAPE through unchanged, so
                # it is in casacore (Fortran) axis order, rows last.
                tile = [int(t) for t in spec["DEFAULTTILESHAPE"]]
        for column in maketabdesc(desc):
            d = column["desc"]
            code = VALUETYPES[d["valueType"].lower()]
            array = "ndim" in d
            shape = [int(s) for s in d.get("shape", [])][::-1]
            option = int(d.get("option", 0))
            if shape or option & 1:
                option |= 4
            default = [] if array else _canonical_default(code, d.get("default", 0))
            self._writer.add_column(
                column["name"],
                code,
                array,
                int(d.get("ndim", 0)),
                shape,
                option,
                int(d.get("maxlen", 0)),
                d.get("comment", ""),
                d.get("dataManagerType", ""),
                d.get("dataManagerGroup", ""),
                default,
                manager,
                name,
                tile,
            )
            dtype = (
                "str"
                if code == STRING
                else next(k for k, v in CODES.items() if v == code).name
            )
            self._columns[column["name"]] = {"dtype": dtype, "is_array": array}

    # -- lifetime --------------------------------------------------------------
    def flush(self):
        self._writer.flush()

    def close(self):
        if self._writer is not None:
            try:
                self._writer.close()
            finally:
                self._writer = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_table(path, readonly=True, lock_attempts=10, lock_wait=1.0):
    """The core reader's table when `readonly`, else a writable `Table`."""
    if readonly:
        return core_ms.open_table(path)
    return Table(path, lock_attempts, lock_wait)
