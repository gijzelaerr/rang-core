"""QuartiCal gain stores (research/dfio-formats.md, F2).

QuartiCal 0.2.7 writes its gains with dask-ms
(`daskms.experimental.zarr.xds_to_zarr`) as zarr v2: one group per term
(`<store>/G`), one sub-group per partition (`G_0`, `G_1`, ... over field,
scan and DATA_DESC_ID), each with `.zattrs` (`DATA_DESC_ID`, `FIELD_ID`,
`FIELD_NAME`, `SCAN_NUMBER`, `NAME`, `TYPE`, `GAIN_AXES`, `GAIN_SPEC`,
`__daskms_zarr_attr__` with the dask chunks), a consolidated `.zmetadata`,
and one array per coordinate (`gain_time`, `gain_freq`, `antenna`,
`direction`, `correlation`, `time_chunk`, `freq_chunk`; parametrised terms
also `param_time`, `param_freq`, `param_name`) and data variable (`gains`,
`gain_flags`, `jhj`, `conv_iter`, `conv_perc`; `params`, `param_flags`,
...). The axes of `gains` are (gain_time, gain_freq, antenna, direction,
correlation); a `complex` term has four correlations (XX, XY, YX, YY: the
full 2x2), a `diag_complex` two.

`read(path)` decodes every array with the core's blosc decoder
(`rang.core_zarr`); `write(store, path)` writes the same metadata byte for
byte (JSON as zarr writes it) and each chunk as a valid blosc frame stored
without compression (the memcpyed flag), which numcodecs and the core both
decode. No dependency on zarr, dask-ms or QuartiCal.
"""

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import core_zarr

DAT = "__daskms_zarr_attr__"
BLOSC_CODES = {"blosclz": 0, "lz4": 1, "lz4hc": 1, "snappy": 2, "zlib": 3, "zstd": 4}


def dumps(meta):
    """zarr v2's JSON: indent 4, sorted keys, ASCII."""
    return json.dumps(
        meta, indent=4, sort_keys=True, ensure_ascii=True, separators=(",", ": ")
    )


@dataclass
class Variable:
    """One zarr array of a partition: dims, values and its attributes."""

    dims: tuple
    data: np.ndarray
    coordinate: bool = False
    array_type: str = "dask.array.core.Array"
    chunks: tuple = None
    compressor: dict = field(
        default_factory=lambda: {
            "blocksize": 0,
            "clevel": 5,
            "cname": "lz4",
            "id": "blosc",
            "shuffle": 1,
        }
    )
    attrs: dict = field(default_factory=dict)


@dataclass
class Partition:
    """One dataset (`<term>_<n>`): attributes and variables."""

    name: str
    attrs: dict
    variables: dict

    @property
    def type(self):
        return self.attrs.get("TYPE")

    def __getitem__(self, name):
        return self.variables[name].data

    @property
    def dims(self):
        out = {}
        for v in self.variables.values():
            out.update(zip(v.dims, v.data.shape))
        return out

    def gains_2x2(self):
        """gains as (time, freq, antenna, direction, 2, 2) complex128."""
        g = self["gains"]
        ncorr = g.shape[-1]
        out = np.zeros(g.shape[:-1] + (2, 2), np.complex128)
        if ncorr == 4:
            out[...] = g.reshape(g.shape[:-1] + (2, 2))
        elif ncorr == 2:
            out[..., 0, 0], out[..., 1, 1] = g[..., 0], g[..., 1]
        elif ncorr == 1:
            out[..., 0, 0] = out[..., 1, 1] = g[..., 0]
        else:
            raise ValueError(f"unsupported correlation count {ncorr}")
        return out


def _chunk_keys(shape, chunks):
    grid = [max(1, -(-s // c)) for s, c in zip(shape, chunks)]
    for index in np.ndindex(*grid) if grid else [()]:
        yield index, ".".join(str(i) for i in index) if index else "0"


def _read_array(path):
    path = Path(path)
    meta = json.loads((path / ".zarray").read_text())
    if meta.get("filters"):
        raise ValueError(f"{path}: zarr filters are not supported")
    dtype = np.dtype(meta["dtype"])
    if dtype.kind == "O":
        raise ValueError(f"{path}: object arrays are not supported")
    shape, chunks = tuple(meta["shape"]), tuple(meta["chunks"])
    order = meta.get("order", "C")
    out = np.empty(shape, dtype)
    comp = meta.get("compressor")
    for index, key in _chunk_keys(shape, chunks):
        f = path / key
        start = [i * c for i, c in zip(index, chunks)]
        sel = tuple(slice(s, min(s + c, n)) for s, c, n in zip(start, chunks, shape))
        if not f.exists():
            fill = meta.get("fill_value")
            out[sel] = 0 if fill is None else fill
            continue
        raw = f.read_bytes()
        if comp is None:
            data = raw
        elif comp.get("id") == "blosc":
            data = core_zarr.read_chunk(f)
        else:
            raise ValueError(f"{path}: compressor {comp.get('id')} is not supported")
        block = np.frombuffer(data, dtype).reshape(chunks, order=order)
        out[sel] = block[tuple(slice(0, s.stop - s.start) for s in sel)]
    return meta, out


def read_partition(path):
    path = Path(path)
    attrs = json.loads((path / ".zattrs").read_text())
    variables = {}
    for array in sorted(p.parent for p in path.glob("*/.zarray")):
        meta, data = _read_array(array)
        zattrs = json.loads((array / ".zattrs").read_text())
        info = zattrs.get(DAT, {})
        variables[array.name] = Variable(
            dims=tuple(zattrs.get("_ARRAY_DIMENSIONS", info.get("dims", ()))),
            data=data,
            coordinate=bool(info.get("coordinate", False)),
            array_type=info.get("array_type", "dask.array.core.Array"),
            chunks=tuple(meta["chunks"]),
            compressor=meta.get("compressor"),
            attrs={
                k: v for k, v in zattrs.items() if k not in ("_ARRAY_DIMENSIONS", DAT)
            },
        )
    return Partition(path.name, attrs, variables)


def read(path):
    """A gain store: {term: [Partition, ...]} in partition order."""
    path = Path(path)
    terms = {}
    for term in sorted(p for p in path.iterdir() if (p / ".zgroup").exists()):
        parts = sorted(
            (p for p in term.iterdir() if (p / ".zattrs").exists()),
            key=lambda p: int(p.name.rsplit("_", 1)[-1]),
        )
        terms[term.name] = [read_partition(p) for p in parts]
    if not terms:
        raise ValueError(f"{path} is not a QuartiCal gain store")
    return terms


def read_term(path, term):
    return read(path)[term]


# -- writing -------------------------------------------------------------------


def blosc_frame(data, typesize, compressor):
    """`data` as a blosc 1 frame stored without compression (memcpyed)."""
    nbytes = len(data)
    flags = 0x02 | (BLOSC_CODES.get(compressor.get("cname", "lz4"), 1) << 5)
    if compressor.get("shuffle", 0) == 1:
        flags |= 0x01
    elif compressor.get("shuffle", 0) == 2:
        flags |= 0x04
    header = struct.pack(
        "<BBBBIII", 2, 1, flags, min(typesize, 255), nbytes, nbytes, nbytes + 16
    )
    return header + data


def _array_meta(var):
    data = var.data
    chunks = tuple(var.chunks) if var.chunks else data.shape
    return {
        "chunks": list(chunks),
        "compressor": var.compressor,
        "dtype": data.dtype.str if data.dtype.kind != "b" else "|b1",
        "fill_value": None,
        "filters": None,
        "order": "C",
        "shape": list(data.shape),
        "zarr_format": 2,
    }


def _array_attrs(var):
    attrs = dict(var.attrs)
    attrs["_ARRAY_DIMENSIONS"] = list(var.dims)
    attrs[DAT] = {
        "array_type": var.array_type,
        "coordinate": var.coordinate,
        "dims": list(var.dims),
    }
    return attrs


def write_partition(part, path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    group = {"zarr_format": 2}
    attrs = dict(part.attrs)
    if DAT not in attrs:
        chunks = {}
        for v in part.variables.values():
            ch = v.chunks or v.data.shape
            for d, c, n in zip(v.dims, ch, v.data.shape):
                chunks[d] = [c] * (n // c) + ([n % c] if n % c else [])
        attrs[DAT] = {"chunks": chunks}
    metadata = {".zattrs": attrs, ".zgroup": group}
    (path / ".zgroup").write_text(dumps(group))
    (path / ".zattrs").write_text(dumps(attrs))
    for name, var in sorted(part.variables.items()):
        d = path / name
        d.mkdir()
        meta, zattrs = _array_meta(var), _array_attrs(var)
        (d / ".zarray").write_text(dumps(meta))
        (d / ".zattrs").write_text(dumps(zattrs))
        metadata[f"{name}/.zarray"] = meta
        metadata[f"{name}/.zattrs"] = zattrs
        data = np.ascontiguousarray(var.data)
        chunks = tuple(meta["chunks"])
        for index, key in _chunk_keys(data.shape, chunks):
            start = [i * c for i, c in zip(index, chunks)]
            sel = tuple(
                slice(s, min(s + c, n)) for s, c, n in zip(start, chunks, data.shape)
            )
            block = np.zeros(chunks, data.dtype)
            block[tuple(slice(0, s.stop - s.start) for s in sel)] = data[sel]
            raw = block.tobytes()
            if var.compressor is None:
                (d / key).write_bytes(raw)
            else:
                (d / key).write_bytes(
                    blosc_frame(raw, data.dtype.itemsize, var.compressor)
                )
    (path / ".zmetadata").write_text(
        dumps({"metadata": metadata, "zarr_consolidated_format": 1})
    )


def write(terms, path):
    """Write {term: [Partition, ...]} as a gain store at `path` (new)."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    (path / ".zgroup").write_text(dumps({"zarr_format": 2}))
    for term, parts in terms.items():
        (path / term).mkdir()
        (path / term / ".zgroup").write_text(dumps({"zarr_format": 2}))
        for i, part in enumerate(parts):
            write_partition(part, path / term / f"{term}_{i}")
    return path


def complex_partition(
    gains,
    flags,
    gain_time,
    gain_freq,
    antennas,
    *,
    name="G",
    field_id=0,
    field_name="",
    scan=0,
    ddid=0,
    jhj=None,
):
    """A `complex` (full 2x2) partition from the core's gains
    (time, freq, antenna, direction, 2, 2) on the given grid."""
    gains = np.asarray(gains, np.complex128)
    nt, nf, na, nd = gains.shape[:4]
    g = gains.reshape(nt, nf, na, nd, 4)
    spec = [[nt], [nf], [na], [nd], [4]]

    def coord(values, dims, array_type="numpy.ndarray"):
        return Variable(dims, np.asarray(values), True, array_type, (len(values),))

    full = (nt, nf, na, nd, 4)
    variables = {
        "gains": Variable(
            ("gain_time", "gain_freq", "antenna", "direction", "correlation"),
            g,
            chunks=full,
        ),
        "gain_flags": Variable(
            ("gain_time", "gain_freq", "antenna", "direction"),
            np.asarray(flags, np.int8).reshape(nt, nf, na, nd),
            chunks=full[:4],
        ),
        "jhj": Variable(
            ("gain_time", "gain_freq", "antenna", "direction", "correlation"),
            np.zeros(full, np.complex128)
            if jhj is None
            else np.asarray(jhj, np.complex128),
            chunks=full,
        ),
        "conv_iter": Variable(
            ("time_chunk", "freq_chunk"), np.zeros((1, 1), np.int64), chunks=(1, 1)
        ),
        "conv_perc": Variable(
            ("time_chunk", "freq_chunk"), np.ones((1, 1), np.float64), chunks=(1, 1)
        ),
        "gain_time": coord(np.asarray(gain_time, float), ("gain_time",)),
        "gain_freq": coord(np.asarray(gain_freq, float), ("gain_freq",)),
        "antenna": coord(np.asarray([str(a) for a in antennas]), ("antenna",)),
        "direction": coord(np.arange(nd, dtype=np.int32), ("direction",)),
        "correlation": coord(np.asarray(["XX", "XY", "YX", "YY"]), ("correlation",)),
        "time_chunk": coord(np.zeros(1, np.int64), ("time_chunk",)),
        "freq_chunk": coord(np.zeros(1, np.int64), ("freq_chunk",)),
    }
    attrs = {
        "DATA_DESC_ID": int(ddid),
        "FIELD_ID": int(field_id),
        "FIELD_NAME": field_name,
        "GAIN_AXES": ["gain_time", "gain_freq", "antenna", "direction", "correlation"],
        "GAIN_SPEC": spec,
        "NAME": name,
        "SCAN_NUMBER": int(scan),
        "TYPE": "complex",
    }
    return Partition(f"{name}_0", attrs, variables)


def summary(terms):
    out = {}
    for term, parts in terms.items():
        out[term] = [
            {
                "name": p.name,
                "type": p.type,
                "dims": p.dims,
                "field": p.attrs.get("FIELD_NAME"),
                "scan": p.attrs.get("SCAN_NUMBER"),
                "variables": sorted(p.variables),
            }
            for p in parts
        ]
    return out


__all__ = [
    "Partition",
    "Variable",
    "blosc_frame",
    "complex_partition",
    "read",
    "read_partition",
    "read_term",
    "summary",
    "write",
    "write_partition",
]
