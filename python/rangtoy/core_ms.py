"""Measurement Set reads at the edge of the Rang core (research/core-e-ms-reader.md).

Opens casacore tables read-only through the core's Rust reader and returns
columns as python-casacore's `getcol` does: one leading row axis, then the
cell axes in reversed casacore order, NumPy dtypes `bool`, `int32`,
`float32`, `float64`, `complex64` and friends, and string columns as object
arrays. Only StandardStMan, IncrementalStMan (scalars), TiledShapeStMan and
TiledColumnStMan columns are readable; the description says which.
"""

import ctypes
import json
from pathlib import Path

import numpy as np

from . import core

_SHAPE = ctypes.c_int64 * 8


class _Column(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("nbytes", ctypes.c_size_t),
        ("nrows", ctypes.c_uint64),
        ("ndim", ctypes.c_size_t),
        ("shape", _SHAPE),
        ("dtype", ctypes.c_int32),
        ("nstrings", ctypes.c_size_t),
    ]


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


def _lib():
    lib = core.library()
    if not getattr(lib, "_rang_ms_ready", False):
        if not hasattr(lib, "rang_core_ms_open"):
            raise RuntimeError(
                "the core library has no Measurement Set reader; "
                "core/src/lib.rs must declare `pub mod ms;` and `pub mod ffi_ms;`"
            )
        lib.rang_core_ms_open.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        lib.rang_core_ms_open.restype = ctypes.c_int
        lib.rang_core_ms_close.argtypes = [ctypes.c_void_p]
        lib.rang_core_ms_close.restype = None
        lib.rang_core_ms_describe.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]
        lib.rang_core_ms_describe.restype = ctypes.c_size_t
        lib.rang_core_ms_read.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.POINTER(_Column),
        ]
        lib.rang_core_ms_read.restype = ctypes.c_int
        lib.rang_core_ms_free.argtypes = [ctypes.POINTER(_Column)]
        lib.rang_core_ms_free.restype = None
        lib.rang_core_ms_last_error.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.rang_core_ms_last_error.restype = ctypes.c_size_t
        lib._rang_ms_ready = True
    return lib


def _last_error(lib):
    needed = lib.rang_core_ms_last_error(None, 0)
    buf = ctypes.create_string_buffer(needed + 1)
    lib.rang_core_ms_last_error(buf, needed)
    return buf.raw[:needed].decode("utf-8", "replace")


def has_reader():
    """True when the built core library exposes the reader symbols."""
    return hasattr(core.library(), "rang_core_ms_open")


class Table:
    """An open casacore table; use as a context manager or call `close`."""

    def __init__(self, path):
        self.path = Path(path)
        lib = _lib()
        handle = ctypes.c_void_p()
        status = lib.rang_core_ms_open(str(self.path).encode(), ctypes.byref(handle))
        if status:
            raise OSError(_last_error(lib) if status == 1 else "core panic in open")
        self._handle = handle
        needed = lib.rang_core_ms_describe(self._handle, None, 0)
        buf = ctypes.create_string_buffer(needed + 1)
        lib.rang_core_ms_describe(self._handle, buf, needed)
        self.description = json.loads(buf.raw[:needed].decode("utf-8"))
        self.nrows = int(self.description["nrows"])
        self.columns = {c["name"]: c for c in self.description["columns"]}

    def close(self):
        if getattr(self, "_handle", None) is not None:
            _lib().rang_core_ms_close(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        if getattr(self, "_handle", None) is not None:
            self.close()

    def colnames(self):
        return list(self.columns)

    def subtable(self, name):
        return Table(self.path / name)

    def getcol(self, name, startrow=0, nrow=None):
        """Rows `startrow` onwards (all, or `nrow` of them) of one column."""
        if self._handle is None:
            raise ValueError("table is closed")
        lib = _lib()
        count = 0 if nrow is None else int(nrow)
        if nrow is not None and count <= 0:
            raise ValueError("nrow must be positive")
        out = _Column()
        status = lib.rang_core_ms_read(
            self._handle, name.encode(), int(startrow), count, ctypes.byref(out)
        )
        if status:
            raise OSError(_last_error(lib) if status == 1 else "core panic in read")
        try:
            raw = (
                np.ctypeslib.as_array(out.data, shape=(out.nbytes,))
                if out.nbytes
                else np.zeros(0, np.uint8)
            )
            cell = tuple(int(out.shape[i]) for i in range(out.ndim))
            shape = (int(out.nrows),) + cell[::-1]
            if out.dtype == STRING:
                packed, strings, at = raw.tobytes(), [], 0
                for _ in range(out.nstrings):
                    n = int.from_bytes(packed[at : at + 4], "little")
                    strings.append(packed[at + 4 : at + 4 + n].decode("utf-8"))
                    at += 4 + n
                return np.asarray(strings, dtype=object).reshape(shape)
            values = raw.view(DTYPES[out.dtype]).copy()
            return values.reshape(shape)
        finally:
            lib.rang_core_ms_free(ctypes.byref(out))


def open_table(path):
    return Table(path)
