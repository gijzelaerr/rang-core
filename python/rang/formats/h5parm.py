"""losoto/DP3 H5parm, the subset rang uses (research/dfio-formats.md, F4).

An H5parm is an HDF5 file in PyTables' layout: solution sets
`/solNNN` (attribute `h5parm_version`), each with the tables `antenna`
(`name` S16, `position` float32[3]) and `source` (`name` S128, `dir`
float32[2]) and solution tables `/solNNN/<type>NNN` whose PyTables TITLE is
the type (`amplitude`, `phase`, ...), holding `val` and `weight` with the
attribute `AXES` (here `time,freq,ant,dir,pol`) and one array per axis.
This module writes the attributes PyTables and losoto read (CLASS, TITLE,
VERSION, FLAVOR; the table FIELD_n_NAME/FILL and NROWS), copied from a file
losoto 2.7.1 made (the protocol's reference listing).

Needs h5py (the `formats` extra); imported lazily.
"""

from dataclasses import dataclass, field

import numpy as np

AXES = ("time", "freq", "ant", "dir", "pol")


def _h5py():
    try:
        import h5py
    except ImportError as err:  # pragma: no cover - the extra is missing
        raise ImportError(
            "H5parm needs h5py: pip install 'rang-core[formats]'"
        ) from err
    return h5py


@dataclass
class Soltab:
    """One solution table: its type, axes, axis values, values, weights."""

    type: str
    axes: tuple
    axis_values: dict
    val: np.ndarray
    weight: np.ndarray


@dataclass
class Solset:
    """One solution set: antennas, sources and solution tables."""

    antennas: list = field(default_factory=list)  # (name, position xyz)
    sources: list = field(default_factory=list)  # (name, (ra, dec))
    soltabs: dict = field(default_factory=dict)  # name -> Soltab


def _b(text):
    return np.bytes_(text.encode())


def _attrs(obj, **values):
    for k, v in values.items():
        obj.attrs[k] = _b(v) if isinstance(v, str) else v


def _nullterm(width):
    """A fixed-length, NUL-terminated HDF5 string type, as PyTables writes
    strings (DP3 does not match NUL-padded names; research/dfio-formats.md)."""
    h5py = _h5py()
    t = h5py.h5t.C_S1.copy()
    t.set_size(width)
    t.set_strpad(h5py.h5t.STR_NULLTERM)
    return t


def _create(group, name, data, htype, chunked=False):
    """A dataset of `data` with HDF5 type `htype`, written as given."""
    h5py = _h5py()
    shape = data.shape
    space = h5py.h5s.create_simple(
        shape, (h5py.h5s.UNLIMITED,) * len(shape) if chunked else None
    )
    plist = None
    if chunked:
        plist = h5py.h5p.create(h5py.h5p.DATASET_CREATE)
        plist.set_chunk(tuple(max(1, n) for n in shape))
    dsid = h5py.h5d.create(group.id, name.encode(), htype, space, dcpl=plist)
    if data.size:
        dsid.write(h5py.h5s.ALL, h5py.h5s.ALL, np.ascontiguousarray(data), mtype=htype)
    return group[name]


def _array(group, name, data, axes=None):
    h5py = _h5py()
    data = np.asarray(data)
    if data.dtype.kind in "US":
        if data.dtype.kind == "U":
            data = np.array([x.encode() for x in data.ravel()]).reshape(data.shape)
        width = max(1, data.dtype.itemsize)
        data = data.astype(f"S{width}")
        ds = _create(group, name, data, _nullterm(width))
    else:
        ds = _create(group, name, data, h5py.h5t.py_create(data.dtype))
    _attrs(ds, CLASS="ARRAY", FLAVOR="numpy", TITLE="", VERSION="2.4")
    if axes is not None:
        ds.attrs["AXES"] = _b(",".join(axes))
    return ds


def _table(group, name, records, title, fill):
    """A PyTables-style table: a chunked compound dataset whose string
    members are NUL-terminated."""
    h5py = _h5py()
    dt = records.dtype
    htype = h5py.h5t.create(h5py.h5t.COMPOUND, dt.itemsize)
    for fname in dt.names:
        ftype, offset = dt.fields[fname][:2]
        if ftype.kind == "S":
            member = _nullterm(ftype.itemsize)
        else:
            member = h5py.h5t.py_create(ftype)
        htype.insert(fname.encode(), offset, member)
    ds = _create(group, name, records, htype, chunked=True)
    attrs = {"CLASS": "TABLE", "TITLE": title, "VERSION": "2.7"}
    for i, (fname, fvalue) in enumerate(zip(dt.names, fill)):
        attrs[f"FIELD_{i}_NAME"] = fname
        ds.attrs[f"FIELD_{i}_FILL"] = fvalue
    _attrs(ds, **attrs)
    ds.attrs["NROWS"] = np.int64(len(records))
    return ds


def write(path, solsets):
    """Write {solset name: Solset} as an H5parm (a new file)."""
    h5py = _h5py()
    with h5py.File(path, "w-") as f:
        _attrs(f, CLASS="GROUP", PYTABLES_FORMAT_VERSION="2.1", TITLE="", VERSION="1.0")
        for ss_name, ss in solsets.items():
            g = f.create_group(ss_name)
            _attrs(g, CLASS="GROUP", TITLE="", VERSION="1.0", h5parm_version="1.0")
            ant = np.zeros(
                len(ss.antennas), [("name", "S16"), ("position", "<f4", (3,))]
            )
            for i, (n, p) in enumerate(ss.antennas):
                ant[i] = (n.encode(), p)
            _table(
                g,
                "antenna",
                ant,
                "Antenna names and positions",
                (np.bytes_(b""), np.float32(0)),
            )
            sou = np.zeros(len(ss.sources), [("name", "S128"), ("dir", "<f4", (2,))])
            for i, (n, d) in enumerate(ss.sources):
                sou[i] = (n.encode(), d)
            _table(
                g,
                "source",
                sou,
                "Source names and directions",
                (np.bytes_(b""), np.float32(0)),
            )
            for st_name, st in ss.soltabs.items():
                t = g.create_group(st_name)
                _attrs(t, CLASS="GROUP", TITLE=st.type, VERSION="1.0", parmdb_type="")
                for a in st.axes:
                    _array(t, a, st.axis_values[a])
                _array(t, "val", st.val, st.axes)
                _array(t, "weight", st.weight, st.axes)
    return path


def _text(value):
    if isinstance(value, bytes | np.bytes_):
        return value.decode()
    return str(value)


def read(path):
    """An H5parm as {solset name: Solset}; string axes as `str` arrays."""
    h5py = _h5py()
    out = {}
    with h5py.File(path, "r") as f:
        for ss_name, g in f.items():
            if not isinstance(g, h5py.Group):
                continue
            ss = Solset()
            if "antenna" in g:
                ss.antennas = [
                    (_text(r["name"]), np.asarray(r["position"]))
                    for r in g["antenna"][()]
                ]
            if "source" in g:
                ss.sources = [
                    (_text(r["name"]), np.asarray(r["dir"])) for r in g["source"][()]
                ]
            for st_name, t in g.items():
                if not isinstance(t, h5py.Group) or "val" not in t:
                    continue
                axes = tuple(_text(t["val"].attrs["AXES"]).split(","))
                values = {}
                for a in axes:
                    v = t[a][()]
                    values[a] = (
                        np.array([_text(x) for x in v]) if v.dtype.kind == "S" else v
                    )
                weight = t["weight"][()] if "weight" in t else np.ones(t["val"].shape)
                ss.soltabs[st_name] = Soltab(
                    _text(t.attrs.get("TITLE", st_name.rstrip("0123456789"))),
                    axes,
                    values,
                    t["val"][()],
                    weight,
                )
            out[ss_name] = ss
    return out


def diagonal_solset(
    gains,
    times,
    freqs,
    antennas,
    positions=None,
    directions=None,
    weights=None,
    amplitude=None,
    phase=None,
):
    """amplitude000 and phase000 (pol XX, YY) from diagonal gains
    `gains[t, f, a, d, p]` (complex), on the given axes; or, exactly as
    given, from `amplitude` and `phase` (then `gains` may be None)."""
    if gains is None:
        amplitude, phase = np.asarray(amplitude, float), np.asarray(phase, float)
        gains = amplitude * np.exp(1j * phase)
    gains = np.asarray(gains, complex)
    if amplitude is None:
        amplitude, phase = np.abs(gains), np.angle(gains)
    _, _, na, nd, npol = gains.shape
    if npol != 2:
        raise ValueError("diagonal gains have two polarisations")
    directions = directions or [("pointing", (0.0, 0.0))] * nd
    positions = np.zeros((na, 3)) if positions is None else np.asarray(positions)
    w = np.ones(gains.shape) if weights is None else np.asarray(weights, float)
    axis_values = {
        "time": np.asarray(times, float),
        "freq": np.asarray(freqs, float),
        "ant": np.array([str(a) for a in antennas]),
        "dir": np.array([d[0] for d in directions]),
        "pol": np.array(["XX", "YY"]),
    }
    ss = Solset(
        antennas=[(str(a), positions[i]) for i, a in enumerate(antennas)],
        sources=list(directions),
    )
    ss.soltabs["amplitude000"] = Soltab("amplitude", AXES, axis_values, amplitude, w)
    ss.soltabs["phase000"] = Soltab("phase", AXES, axis_values, phase, w)
    return ss


def diagonal_gains(solset):
    """amp * exp(i phase) of a solset's amplitude000 and phase000, in
    (time, freq, ant, dir, pol) order (transposed from the file's AXES)."""
    amp, ph = solset.soltabs["amplitude000"], solset.soltabs["phase000"]
    order = [amp.axes.index(a) for a in AXES]
    a = np.transpose(amp.val, order)
    p = np.transpose(ph.val, [ph.axes.index(x) for x in AXES])
    return a * np.exp(1j * p)


def summary(solsets):
    return {
        name: {
            "antennas": len(ss.antennas),
            "sources": [s[0] for s in ss.sources],
            "soltabs": {
                k: {"type": v.type, "axes": list(v.axes), "shape": list(v.val.shape)}
                for k, v in ss.soltabs.items()
            },
        }
        for name, ss in solsets.items()
    }


__all__ = [
    "AXES",
    "Solset",
    "Soltab",
    "diagonal_gains",
    "diagonal_solset",
    "read",
    "summary",
    "write",
]
