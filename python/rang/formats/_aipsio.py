"""Read-only AipsIO decoding of a casacore table's keywords (`table.dat`).

The core reader (`rang.core_ms`) skips the keyword sets; the formats need the
table keywords of CASA calibration tables (`ParType`, `VisCal`, ...). This
decodes the `TableDesc` keyword `TableRecord` of a little- or big-endian
`table.dat` as casacore 3.x writes it (canonical, big-endian AipsIO). The
layout follows the core's Rust parser (`core/src/ms_desc.rs`,
`core/src/aipsio.rs`), which was read from the casacore 3.8.1 sources.
Values: Python scalars, `str`, NumPy arrays, `dict` for sub-records and
`"Table: <name>"` strings for table-valued keywords.
"""

import struct
from pathlib import Path

import numpy as np

MAGIC = 0xBEBEBEBE
BOOL, CHAR, UCHAR, SHORT, USHORT, INT, UINT, FLOAT, DOUBLE = range(9)
COMPLEX, DCOMPLEX, STRING, TABLE = 9, 10, 11, 12
ARRAY_STRING, RECORD, INT64, ARRAY_INT64 = 24, 25, 29, 30
SCALAR = {
    BOOL: (">?", 1),
    CHAR: (">b", 1),
    UCHAR: (">B", 1),
    SHORT: (">h", 2),
    USHORT: (">H", 2),
    INT: (">i", 4),
    UINT: (">I", 4),
    FLOAT: (">f", 4),
    DOUBLE: (">d", 8),
    INT64: (">q", 8),
}
# The NumPy type of a scalar keyword (`column_descriptions`, typed).
TYPED = {
    BOOL: "bool",
    CHAR: "int8",
    UCHAR: "uint8",
    SHORT: "int16",
    USHORT: "uint16",
    INT: "int32",
    UINT: "uint32",
    FLOAT: "float32",
    DOUBLE: "float64",
    INT64: "int64",
}
# Bytes of a scalar column's default value in its description.
DEFAULT_SIZES = {
    BOOL: 1,
    CHAR: 1,
    UCHAR: 1,
    SHORT: 2,
    USHORT: 2,
    INT: 4,
    UINT: 4,
    FLOAT: 4,
    DOUBLE: 8,
    COMPLEX: 8,
    DCOMPLEX: 16,
    INT64: 8,
}
ARRAY_DTYPES = {
    13: ">u1",
    14: ">i1",
    15: ">u1",
    16: ">i2",
    17: ">u2",
    18: ">i4",
    19: ">u4",
    20: ">f4",
    21: ">f8",
    22: ">c8",
    23: ">c16",
    30: ">i8",
}


class _Cursor:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if self.pos + n > len(self.data):
            raise ValueError("table.dat ends early")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def u32(self):
        return struct.unpack(">I", self.take(4))[0]

    def i32(self):
        return struct.unpack(">i", self.take(4))[0]

    def u64(self):
        return struct.unpack(">Q", self.take(8))[0]

    def string(self):
        return self.take(self.u32()).decode("utf-8", "replace")

    def start(self, expect=None):
        at = self.pos
        length = self.u32()
        kind = self.string()
        version = self.u32()
        if expect is not None and kind != expect:
            raise ValueError(f"expected AipsIO object {expect}, found {kind}")
        return at, length, kind, version

    def end(self, obj):
        self.pos = obj[0] + obj[1]

    def iposition(self):
        obj = self.start("IPosition")
        n = self.u32()
        fmt = ">i" if obj[3] == 1 else ">q"
        size = 4 if obj[3] == 1 else 8
        out = [struct.unpack(fmt, self.take(size))[0] for _ in range(n)]
        self.end(obj)
        return out


def _record_desc(c):
    obj = c.start("RecordDesc")
    fields = []
    for _ in range(max(c.i32(), 0)):
        name, dtype = c.string(), c.i32()
        sub = shape = None
        if dtype == RECORD:
            sub = _record_desc(c)
        elif 13 <= dtype <= 24 or dtype == ARRAY_INT64:
            shape = c.iposition()
        elif dtype == TABLE:
            c.string()
        if obj[3] >= 2:
            c.string()  # comment
        fields.append((name, dtype, sub, shape))
    c.end(obj)
    return fields


def _array(c, dtype):
    obj = c.start()
    if obj[3] == 3:
        # casacore's `putArray` (version 3): ndim, then each length.
        shape = [c.u32() for _ in range(c.u32())]
    else:
        shape = c.iposition()
    n = c.u32()
    if dtype == ARRAY_STRING:
        values = [c.string() for _ in range(n)]
        out = np.array(values, dtype=object)
    elif dtype == 13:  # Array<Bool>: bits
        raw = np.frombuffer(c.take((n + 7) // 8), np.uint8)
        out = np.unpackbits(raw, bitorder="little")[:n].astype(bool)
    else:
        dt = np.dtype(ARRAY_DTYPES[dtype])
        out = np.frombuffer(c.take(n * dt.itemsize), dt).astype(dt.newbyteorder("="))
    c.end(obj)
    # casacore shape is Fortran order; NumPy order reverses it.
    return out.reshape(tuple(shape)[::-1]) if shape else out


def _record_values(c, fields, typed=False):
    out = {}
    for name, dtype, sub, _shape in fields:
        if dtype == RECORD:
            out[name] = _record(c, typed) if not sub else _record_values(c, sub, typed)
        elif dtype == STRING:
            out[name] = c.string()
        elif dtype == TABLE:
            out[name] = "Table: " + c.string()
        elif dtype in SCALAR:
            fmt, size = SCALAR[dtype]
            value = struct.unpack(fmt, c.take(size))[0]
            out[name] = np.dtype(TYPED[dtype]).type(value) if typed else value
        elif dtype == COMPLEX:
            re, im = struct.unpack(">ff", c.take(8))
            out[name] = np.complex64(complex(re, im)) if typed else complex(re, im)
        elif dtype == DCOMPLEX:
            re, im = struct.unpack(">dd", c.take(16))
            out[name] = np.complex128(complex(re, im)) if typed else complex(re, im)
        elif 13 <= dtype <= 24 or dtype == ARRAY_INT64:
            out[name] = _array(c, dtype)
        else:
            raise ValueError(f"keyword {name!r} has unsupported type {dtype}")
    return out


def _record(c, typed=False):
    obj = c.start()
    if obj[2] not in ("TableRecord", "Record"):
        raise ValueError(f"keyword set {obj[2]} is not supported")
    fields = _record_desc(c)
    c.i32()  # record type
    values = _record_values(c, fields, typed)
    c.end(obj)
    return values


def _table_desc(path):
    """A cursor at the table keywords of `table.dat` (after the TableDesc
    name, version and comment)."""
    c = _Cursor((Path(path) / "table.dat").read_bytes())
    if c.u32() != MAGIC:
        raise ValueError("AipsIO magic value missing")
    table = c.start("Table")
    if table[3] == 2:
        c.u32()
    elif table[3] == 3:
        c.u64()
    else:
        raise ValueError(f"table.dat version {table[3]} is not supported")
    c.u32()  # endianness
    if c.string() != "PlainTable":
        raise ValueError("only PlainTable is supported")
    desc = c.start("TableDesc")
    if desc[3] != 2:
        raise ValueError(f"TableDesc version {desc[3]} is not supported")
    c.string(), c.string(), c.string()  # name, version, comment
    return c


def table_keywords(path):
    """The table keywords of the casacore table at `path` (a directory)."""
    return _record(_table_desc(path))


def column_descriptions(path):
    """{column: {"comment", "dataManagerType", "dataManagerGroup",
    "keywords"}} of the casacore table at `path`, read from `table.dat`
    (the layout of `core/src/ms_desc.rs`, `read_coldesc`). Keyword scalars
    are NumPy scalars of their stored type, so they can be written back
    with the same type."""
    c = _table_desc(path)
    _record(c)  # table keywords
    _record(c)  # private keywords
    out = {}
    for _ in range(c.u32()):
        if c.u32() != 1:
            raise ValueError("ColumnDesc version is not 1")
        kind = c.string()
        if c.u32() != 1:
            raise ValueError("BaseColumnDesc version is not 1")
        name, comment = c.string(), c.string()
        dm_type, dm_group = c.string(), c.string()
        dtype = c.i32()
        c.i32(), c.i32()  # option, ndim
        is_array = kind.startswith("ArrayColumnDesc")
        if not is_array and not kind.startswith("ScalarColumnDesc"):
            raise ValueError(f"column class {kind} of {name} is not supported")
        if is_array:
            c.iposition()
        c.u32()  # max length
        keywords = _record(c, typed=True)
        if c.u32() != 1:
            raise ValueError("column description version is not 1")
        if is_array:
            c.take(1)
        elif dtype == STRING:
            c.string()
        else:
            c.take(DEFAULT_SIZES[dtype])
        out[name] = {
            "comment": comment,
            "dataManagerType": dm_type,
            "dataManagerGroup": dm_group,
            "keywords": keywords,
        }
    return out


def table_info(path):
    """[type, subType, readme] of a table's `table.info` (empty if none)."""
    try:
        text = (Path(path) / "table.info").read_text(encoding="utf-8")
    except OSError:
        return ["", "", ""]
    head, _, readme = text.partition("\n\n")
    fields = dict(
        line.split(" = ", 1) if " = " in line else (line.rstrip(" ="), "")
        for line in head.splitlines()
    )
    return [fields.get("Type", ""), fields.get("SubType", ""), readme]
