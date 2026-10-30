"""Writes casacore tables at the edge of the Rang core.

research/e3-table-writer.md and research/e4-table-create.md.
`open_table(path, readonly=False)` returns a `Table` that holds casacore's
write lock on `table.lock` until `close()` (or the end of a `with` block)
and writes as casacore 3.8.1 does: `putcol` and `putcell` of StandardStMan
(scalars, Direct and indirect arrays, strings and string arrays),
TiledColumnStMan and TiledShapeStMan columns, table and column keywords,
`table.info`, `addcols`, `addrows` and `removerows`. `create_table` makes a
new table from a description (python-casacore's `table(name, desc, nrow,
dminfo=...)`), `default_ms` and `default_ms_subtable` a MeasurementSet as
python-casacore does, and `create_caltable` a CASA calibration table (G, B,
K, Df, ...) as CASA writes one. Values are given as python-casacore takes
them: one leading row axis, then the cell axes in reversed casacore order.
Everything is written on `flush()` and on close, once, as casacore
flushes; reads (`getcol`, `getcell`) see what has been flushed.

A separate module from `core_ms` so that the task E reader stays unchanged.
Not done here (E5): IncrementalStMan writes (so rows of a table that has
one), big-endian tables, variable-shape tiled columns, MultiFile tables,
MemoryStMan and TiledDataStMan.
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
DTYPES = {code: dtype for dtype, code in CODES.items()}
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
CAL_SUBTABLES = ("OBSERVATION", "ANTENNA", "FIELD", "SPECTRAL_WINDOW", "HISTORY")
# The columns of the calibration subtables (the required MS descriptions).
CAL_COLUMNS = {
    "OBSERVATION": (
        "TIME_RANGE",
        "LOG",
        "SCHEDULE",
        "FLAG_ROW",
        "OBSERVER",
        "PROJECT",
        "RELEASE_DATE",
        "SCHEDULE_TYPE",
        "TELESCOPE_NAME",
    ),
    "ANTENNA": (
        "OFFSET",
        "POSITION",
        "TYPE",
        "DISH_DIAMETER",
        "FLAG_ROW",
        "MOUNT",
        "NAME",
        "STATION",
    ),
    "FIELD": (
        "DELAY_DIR",
        "PHASE_DIR",
        "REFERENCE_DIR",
        "CODE",
        "FLAG_ROW",
        "NAME",
        "NUM_POLY",
        "SOURCE_ID",
        "TIME",
    ),
    "SPECTRAL_WINDOW": (
        "MEAS_FREQ_REF",
        "CHAN_FREQ",
        "REF_FREQUENCY",
        "CHAN_WIDTH",
        "EFFECTIVE_BW",
        "RESOLUTION",
        "FLAG_ROW",
        "FREQ_GROUP",
        "FREQ_GROUP_NAME",
        "IF_CONV_CHAIN",
        "NAME",
        "NET_SIDEBAND",
        "NUM_CHAN",
        "TOTAL_BANDWIDTH",
    ),
    "HISTORY": (
        "APP_PARAMS",
        "CLI_COMMAND",
        "APPLICATION",
        "MESSAGE",
        "OBJECT_ID",
        "OBSERVATION_ID",
        "ORIGIN",
        "PRIORITY",
        "TIME",
    ),
}


def has_writer():
    """True when the extension exposes the table writer."""
    return hasattr(core.extension(), "MsWriter")


def has_creator():
    """True when the extension exposes table creation (E4)."""
    return hasattr(core.extension(), "ms_create_table")


def _value_type(value):
    """python-casacore's value type of a default value: Python scalars as
    bool, int, double and dcomplex; NumPy values by their dtype."""
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if isinstance(value, complex):
        return "dcomplex"
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
    dtype = DTYPES[code]
    v = np.asarray(value, dtype=dtype)
    if code in (9, 10):
        part = np.dtype(">f4") if code == 9 else np.dtype(">f8")
        return list(np.array([v.real, v.imag], dtype=part).tobytes())
    return list(v.astype(dtype.newbyteorder(">")).tobytes())


def _column_args(column):
    """The binding's column tuple of a `makescacoldesc`/`makearrcoldesc`."""
    d = column["desc"]
    code = VALUETYPES[d["valueType"].lower()]
    array = "ndim" in d
    shape = [int(s) for s in d.get("shape", [])][::-1]
    option = int(d.get("option", 0))
    if array and (shape or option & 1):
        option |= 4
    return (
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
    )


def _manager_args(dminfo):
    """python-casacore's `dminfo` record (`*1`, `*2`, ... in order) as the
    binding's manager tuples."""
    if not dminfo:
        return []

    def order(key):
        return int(key[1:]) if key.startswith("*") and key[1:].isdigit() else 0

    out = []
    for key in sorted(dminfo, key=order):
        dm = dminfo[key]
        spec = dm.get("SPEC", {})
        out.append(
            (
                dm["TYPE"],
                dm["NAME"],
                list(dm.get("COLUMNS", [])),
                int(spec.get("BUCKETSIZE", 0)),
                int(spec.get("BUCKETROWS", 0)),
                int(spec.get("PERSCACHESIZE", 0)),
                [int(t) for t in spec.get("DEFAULTTILESHAPE", [])],
            )
        )
    return out


def _table_link(table, value):
    """The name casacore stores for a table keyword `Table: <path>`: a
    subtable of the table as `././NAME`, any other table absolute."""
    target = Path(value[len("Table: ") :]).resolve()
    if target.parent == Path(table).resolve():
        return "././" + target.name
    return str(target)


def _cell(kind, shape, raw, strings, code):
    if kind == 0:
        return None
    shape = tuple(shape)[::-1]
    if kind == 2:
        return np.asarray(strings, dtype=object).reshape(shape)
    return np.frombuffer(raw, dtype=DTYPES[code]).reshape(shape).copy()


class Table:
    """A casacore table open for writing; use as a context manager."""

    def __init__(self, path, lock_attempts=10, lock_wait=1.0, _writer=None):
        self.path = Path(path)
        self._info = None
        if _writer is not None:
            # A table made in this process: its columns from the writer.
            self._writer = _writer
            self._columns = {
                name: {
                    "dtype": "str" if code == STRING else DTYPES[code].name,
                    "is_array": array,
                }
                for name, code, array in _writer.columns()
            }
            return
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
        if code == STRING and is_array:
            arr = np.asarray(value, dtype=object)
            if nrow is not None and nrow >= 0:
                arr = arr[:nrow]
            if arr.shape[0] == 0:
                return
            self._writer.put_string_cells(
                columnname,
                int(startrow),
                int(arr.shape[0]),
                list(arr.shape[1:])[::-1],
                [str(s) for s in arr.reshape(-1)],
            )
            return
        if code == STRING:
            values = np.asarray(value, dtype=object).reshape(-1)
            if nrow is not None and nrow >= 0:
                values = values[:nrow]
            self._writer.put_strings(
                columnname, int(startrow), [str(v) for v in values]
            )
            return
        dtype = DTYPES[code]
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
        """Write one row (an array cell may change shape when the column is
        not FixedShape)."""
        is_array = self._columns[columnname]["is_array"]
        if self._code(columnname) == STRING and not is_array:
            self.putcol(columnname, [value], rownr, 1)
        elif is_array:
            if self._code(columnname) == STRING:
                value = np.asarray(value, dtype=object)
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

    def getcell(self, columnname, rownr):
        """Flush, then read one cell (None when it is undefined)."""
        code = self._code(columnname)
        if self._columns[columnname]["is_array"]:
            kind, shape, raw, strings = self._writer.read_cells(
                columnname, int(rownr), 1
            )[0]
            return _cell(kind, shape, raw, strings, code)
        return self.getcol(columnname, rownr, 1)[0]

    def iscelldefined(self, columnname, rownr):
        return bool(self._writer.is_defined(columnname, int(rownr)))

    # -- rows ------------------------------------------------------------------
    def addrows(self, nrows=1):
        """Add rows (not initialised, as python-casacore's `addrows`)."""
        self._writer.add_rows(int(nrows))

    add_rows = addrows

    def removerows(self, rownrs):
        """Remove rows (any order; removed from the last one down)."""
        self._writer.remove_rows([int(r) for r in np.atleast_1d(rownrs)])

    remove_rows = removerows

    # -- keywords and info -------------------------------------------------------
    def _put_keyword(self, column, path, value):
        if isinstance(value, dict):
            self._writer.put_keyword(column, path, 4, 0, [], b"", [])
            for key, sub in value.items():
                self._put_keyword(column, path + [key], sub)
            return
        if isinstance(value, str):
            if value.startswith("Table: "):
                name = _table_link(self.path, value)
                self._writer.put_keyword(column, path, 5, 0, [], name.encode(), [])
                return
            self._writer.put_keyword(column, path, 1, 0, [], value.encode(), [])
            return
        if isinstance(value, bool):
            value = np.bool_(value)
        elif isinstance(value, int):
            # python-casacore 3.8.1 stores a Python int keyword as Int64.
            value = np.int64(value)
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
        """Define a table keyword; `a.b` names field `b` of sub-record `a`;
        a string `Table: <path>` defines a table keyword (a subtable link)."""
        self._put_keyword(None, keyword.split("."), value)

    def putcolkeyword(self, columnname, keyword, value):
        self._put_keyword(columnname, keyword.split("."), value)

    def removekeyword(self, keyword):
        self._writer.remove_keyword(None, keyword.split("."))

    def removecolkeyword(self, columnname, keyword):
        self._writer.remove_keyword(columnname, keyword.split("."))

    def putinfo(self, value):
        """Set `table.info` from python-casacore's info dict (`type`,
        `subType`, `readme`; a field not given is kept). As
        `TableProxy::putTableInfo`, a non-empty readme is one added line."""
        info = _read_info(self.path) if self._info is None else self._info
        if "type" in value:
            info[0] = str(value["type"])
        if "subType" in value:
            info[1] = str(value["subType"])
        if "readme" in value:
            readme = str(value["readme"])
            info[2] = readme + "\n" if readme else ""
        self._info = info
        self._writer.put_info(*info)

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
                raise ValueError(f"data manager {dminfo.get('TYPE')} is not added (E5)")
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
            dtype = "str" if code == STRING else DTYPES[code].name
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


def _read_info(path):
    """[type, subType, readme] of a table's `table.info` (empty if none)."""
    try:
        text = (Path(path) / "table.info").read_text()
    except OSError:
        return ["", "", ""]
    head, _, readme = text.partition("\n\n")
    fields = dict(
        line.split(" = ", 1) if " = " in line else (line.rstrip(" ="), "")
        for line in head.splitlines()
    )
    return [fields.get("Type", ""), fields.get("SubType", ""), readme]


def open_table(path, readonly=True, lock_attempts=10, lock_wait=1.0):
    """The core reader's table when `readonly`, else a writable `Table`."""
    if readonly:
        return core_ms.open_table(path)
    return Table(path, lock_attempts, lock_wait)


def create_table(
    path, tabledesc, nrow=0, dminfo=None, info=None, endian="little", multifile=False
):
    """A new table (python-casacore's `table(path, tabledesc, nrow,
    dminfo=dminfo)`): StandardStMan for unbound columns, the managers of
    `dminfo` (StandardStMan, TiledColumnStMan, TiledShapeStMan with
    FixedShape columns) for bound ones; `nrow` rows, not initialised.
    Returned open for writing. IncrementalStMan, MemoryStMan,
    TiledDataStMan, big-endian and MultiFile tables are refused (E5)."""
    columns = [_column_args(c) for c in maketabdesc(tabledesc)]
    info = info or {}
    writer = core.extension().ms_create_table(
        str(path),
        ("", "", ""),
        columns,
        _manager_args(dminfo),
        (info.get("type", ""), info.get("subType", ""), info.get("readme", "")),
        int(nrow),
        endian == "big",
        bool(multifile),
    )
    t = Table(path, _writer=writer)
    t._info = [info.get("type", ""), info.get("subType", ""), info.get("readme", "")]
    return t


def table(tablename, tabledesc=None, nrow=0, readonly=True, dminfo=None, ack=True, **_):
    """python-casacore's `table`: create when a description is given, else
    open (read-only through the core reader unless `readonly=False`)."""
    if tabledesc is not None:
        return create_table(tablename, tabledesc, nrow, dminfo)
    return open_table(tablename, readonly=readonly)


def default_ms(name, tabdesc=None, dminfo=None):
    """python-casacore's `default_ms`: MAIN (the required columns and those
    of `tabdesc`, bound by `dminfo`) and the default subtables (not
    SOURCE); MAIN is returned open for writing."""
    columns = [_column_args(c) for c in maketabdesc(tabdesc or [])]
    writer = core.extension().ms_default_ms(str(name), columns, _manager_args(dminfo))
    return Table(name, _writer=writer)


def default_ms_subtable(subtable, name=None, tabdesc=None, dminfo=None):
    """python-casacore's `default_ms_subtable` (SOURCE included)."""
    columns = [_column_args(c) for c in maketabdesc(tabdesc or [])]
    path = name if name else "MeasurementSet.ms"
    writer = core.extension().ms_default_ms_subtable(
        subtable.upper(), str(path), columns, _manager_args(dminfo)
    )
    return Table(path, _writer=writer)


def read_cells(path, columnname, startrow=0, nrow=1):
    """Cells of a column of a table nobody writes in this process
    (undefined cells as None, rows of any shape), without writing."""
    with core_ms.open_table(path) as reader:
        info = reader.columns[columnname]
    code = STRING if info["dtype"] == "str" else CODES[np.dtype(info["dtype"])]
    cells = core.extension().ms_read_cells(
        str(path), columnname, int(startrow), int(nrow)
    )
    return [_cell(k, s, r, st, code) for k, s, r, st in cells]


# -- CASA calibration tables ---------------------------------------------------


def _write_rows(t, columns, nrows):
    """Row by row, each row's cells in column order (casacore's
    `TableCopy::copyRows`); None leaves a cell undefined."""
    names = [n for n in t.colnames() if n in columns]
    for row in range(nrows):
        for name in names:
            value = columns[name][row]
            if value is not None:
                t.putcell(name, row, value)


def create_caltable(
    path,
    vis_cal,
    main,
    subtables,
    ms_name,
    pol_basis="unknown",
    casa_version="6.7.6-14",
    float_param=None,
):
    """A CASA calibration table written as CASA 6.7.6 writes one
    (`NewCalTable::writeToDisk`): the MAIN rows sorted by
    (SPECTRAL_WINDOW_ID, TIME, ANTENNA1, ANTENNA2) (duplicate keys are
    refused: CASA's heap sort is not stable), MAIN made with all rows,
    filled row by row and flushed, then each subtable the same way, then
    the subtable links of MAIN defined and flushed.

    `main` maps MAIN column names to per-row values (a sequence; None for an
    undefined cell, as CASA leaves WEIGHT); `subtables` maps OBSERVATION,
    ANTENNA, FIELD, SPECTRAL_WINDOW and HISTORY to such mappings (a missing
    or empty one has no rows). FPARAM instead of CPARAM when `float_param`
    (default: when `main` has FPARAM)."""
    if float_param is None:
        float_param = "FPARAM" in main
    nrows = len(main["TIME"]) if "TIME" in main else 0
    keys = [
        (
            int(main["SPECTRAL_WINDOW_ID"][r]),
            float(main["TIME"][r]),
            int(main["ANTENNA1"][r]),
            int(main["ANTENNA2"][r]),
        )
        for r in range(nrows)
    ]
    if len(set(keys)) != len(keys):
        raise ValueError(
            "duplicate (SPECTRAL_WINDOW_ID, TIME, ANTENNA1, ANTENNA2) rows"
        )
    order = sorted(range(nrows), key=lambda r: keys[r])
    rows = {name: [values[r] for r in order] for name, values in main.items()}
    ext = core.extension()
    path = Path(path)
    main_table = Table(
        path,
        _writer=ext.ms_caltable_main(
            str(path),
            vis_cal,
            bool(float_param),
            ms_name,
            pol_basis,
            casa_version,
            nrows,
        ),
    )
    try:
        _write_rows(main_table, rows, nrows)
        main_table.flush()
        for name in CAL_SUBTABLES:
            values = subtables.get(name) or {}
            n = len(next(iter(values.values()))) if values else 0
            sub = Table(
                path / name,
                _writer=ext.ms_caltable_subtable(str(path / name), name, n),
            )
            try:
                # deepCopy: copyRows (and its flush), then copySubTables,
                # which takes every column's keyword set for writing
                # (`rwKeywordSet` marks the table changed) and flushes.
                _write_rows(sub, values, n)
                sub.flush()
                sub._writer.mark_changed()
                sub.flush()
            finally:
                sub.close()
        for name in CAL_SUBTABLES:
            main_table.putkeyword(name, "Table: " + str(path.resolve() / name))
        main_table.flush()
    finally:
        main_table.close()
