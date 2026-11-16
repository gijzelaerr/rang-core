# SPDX-License-Identifier: GPL-3.0-or-later
"""MSv4 processing sets into the core's row layout (research/msv4-interop.md).

Opens an xradio processing set (an xarray DataTree, a Zarr store by default,
`schema_version` 4.x) and yields, per partition, row chunks in the layout
`rang.meerkat.MvfLoader` yields (the keys and dtypes of
`core_fetch.decode_slice`):

- `TIME`: MJD seconds, the MSv4 `time` (Unix seconds) plus 3506716800 s;
- `ANTENNA1`, `ANTENNA2`: int32 indices into the partition's
  `antenna_xds.antenna_name` (`Partition.antenna_names`);
- `FLAG_ROW`: false (MSv4 has no row flag). Neither xradio 1.3.1 nor
  xarray-ms 0.5.14 carries an MSv2 `FLAG_ROW` into the store (the note's
  M3, case c10), so OR `FLAG_ROW` into `FLAG` before converting;
- `DATA` complex64, `FLAG` bool, `WEIGHT_SPECTRUM` float32, each
  `(row, channel, corr)`, from the data group's correlated data, flag and
  weight; `UVW` float64 `(row, 3)`. A uint8 `FLAG` (xarray-ms writes one) is
  read as bool when every value read is 0 or 1, and refused otherwise (the
  note's section 9);
- `FIELD_NAME`, `SCAN_NAME`: the per-time names, per row.

Rows are time-major in `baseline_id` order. A `(time, baseline)` cell whose
`UVW` and `VISIBILITY` are all NaN is a pad (xradio and xarray-ms fill
missing MSv2 rows so; their `FLAG` pads differ) and is dropped. Channels and
correlations are in the store's order (xradio sorts channels by frequency).

The schema is read as is; no telescope is assumed. xarray, zarr 3 and
numcodecs come from the optional `[msv4]` extra and are imported only when a
store is opened.
"""

from pathlib import Path

import numpy as np

UNIX_TO_MJD_SECONDS = 3506716800.0
GRID = ("time", "baseline_id", "frequency", "polarization")
DTYPES = {
    "correlated_data": (np.dtype("complex64"),),
    "flag": (np.dtype("bool"), np.dtype("uint8")),
    "weight": (np.dtype("float32"),),
    "uvw": (np.dtype("float64"),),
}


def has_msv4():
    """True when the `[msv4]` extra is installed."""
    try:
        import xarray  # noqa: F401
        import zarr  # noqa: F401
    except ImportError:
        return False
    return True


def open_processing_set(source):
    """A `ProcessingSet` from a store path or an opened `xarray.DataTree`."""
    if isinstance(source, (str, Path)):
        import xarray

        tree = xarray.open_datatree(str(source), engine="zarr", chunks=None)
        return ProcessingSet(tree, str(source))
    return ProcessingSet(source, getattr(source, "name", None))


def _schema_major(attrs):
    version = str(attrs.get("schema_version", ""))
    return version.split(".")[0] if version else ""


class ProcessingSet:
    """The partitions of a processing set; `refused` names those not read."""

    def __init__(self, tree, source=None):
        self.tree = tree
        self.source = source
        self.names = []
        self.refused = {}
        for name, node in tree.children.items():
            attrs = node.attrs
            if "data_groups" not in attrs:
                continue
            major = _schema_major(attrs)
            if major != "4":
                self.refused[name] = f"schema_version {attrs.get('schema_version')!r}"
            elif attrs.get("type") != "visibility":
                self.refused[name] = f"type {attrs.get('type')!r}, not visibility"
            else:
                self.names.append(name)

    def partition(self, name, data_group="base"):
        if name in self.refused:
            raise ValueError(f"{name}: {self.refused[name]}")
        return Partition(self.tree[name], name, data_group)

    def partitions(self, data_group="base"):
        return [self.partition(name, data_group) for name in self.names]


class Partition:
    """One MSv4 of a processing set: its grid and its rows."""

    def __init__(self, node, name, data_group="base"):
        self.name = name
        self.node = node
        ds = node.ds
        groups = node.attrs["data_groups"]
        if data_group not in groups:
            raise ValueError(f"{name}: no data group {data_group!r} in {list(groups)}")
        group = groups[data_group]
        self.data_group = data_group
        self.variables = {}
        for role, dtypes in DTYPES.items():
            var = group.get(role)
            if var is None or var not in ds:
                raise ValueError(f"{name}: data group {data_group!r} has no {role}")
            array = ds[var]
            want = GRID if role != "uvw" else ("time", "baseline_id", "uvw_label")
            if tuple(array.dims) != want:
                raise ValueError(
                    f"{name}: {var} has dimensions {array.dims}, not {want}"
                )
            if array.dtype not in dtypes:
                want_dtype = " or ".join(str(d) for d in dtypes)
                raise ValueError(f"{name}: {var} is {array.dtype}, not {want_dtype}")
            self.variables[role] = var
        self.ds = ds
        self.time_unix = np.asarray(ds["time"].values, np.float64)
        self.time = self.time_unix + UNIX_TO_MJD_SECONDS
        self.frequency = np.asarray(ds["frequency"].values, np.float64)
        self.polarization = tuple(str(p) for p in ds["polarization"].values)
        names = [str(a) for a in node["antenna_xds"].ds["antenna_name"].values]
        self.antenna_names = names
        index = {a: i for i, a in enumerate(names)}
        n1 = [str(a) for a in ds["baseline_antenna1_name"].values]
        n2 = [str(a) for a in ds["baseline_antenna2_name"].values]
        try:
            self.antenna1 = np.asarray([index[a] for a in n1], np.int32)
            self.antenna2 = np.asarray([index[a] for a in n2], np.int32)
        except KeyError as exc:
            raise ValueError(
                f"{name}: baseline antenna {exc} not in antenna_xds"
            ) from exc
        self.field_name = self._per_time("field_name")
        self.scan_name = self._per_time("scan_name")

    def _per_time(self, coord):
        if coord not in self.ds.coords:
            return np.full(len(self.time), "", dtype=object)
        return np.asarray([str(v) for v in self.ds[coord].values], dtype=object)

    def _flag_as_bool(self, flag):
        """A uint8 `FLAG` as bool, refused unless every value is 0 or 1."""
        if flag.dtype == np.bool_:
            return flag
        bad = flag > 1
        if bad.any():
            values = np.unique(flag[bad])[:8].tolist()
            raise ValueError(
                f"{self.name}: {self.variables['flag']} is uint8 with values "
                f"{values} other than 0 and 1"
            )
        return flag != 0

    @property
    def nbaseline(self):
        return len(self.antenna1)

    def chunks(self, time_rows=None):
        """Row chunks of `time_rows` times each (all times by default)."""
        ntime = len(self.time)
        step = ntime if not time_rows else int(time_rows)
        for start in range(0, ntime, max(step, 1)):
            yield self.rows(start, min(start + step, ntime))

    def rows(self, start=0, stop=None):
        """The rows of times `start` to `stop` (exclusive), pads dropped; the
        dict also holds `PADS`, the number of pad cells dropped."""
        stop = len(self.time) if stop is None else stop
        part = self.ds.isel(time=slice(start, stop))
        values = {
            role: np.asarray(part[var].values) for role, var in self.variables.items()
        }
        values["flag"] = self._flag_as_bool(values["flag"])
        vis = values["correlated_data"]
        ntime, nbl, nchan, ncorr = vis.shape
        uvw = values["uvw"].reshape(ntime * nbl, 3)
        vis = vis.reshape(ntime * nbl, nchan, ncorr)
        # np.isnan of a complex value: either part NaN (the pads are nan+0j).
        pad = np.isnan(uvw).all(axis=1) & np.isnan(vis).reshape(ntime * nbl, -1).all(
            axis=1
        )
        keep = ~pad
        time = np.repeat(self.time[start:stop], nbl)
        out = {
            "ANTENNA1": np.tile(self.antenna1, ntime)[keep],
            "ANTENNA2": np.tile(self.antenna2, ntime)[keep],
            "TIME": time[keep],
            "FLAG_ROW": np.zeros(int(keep.sum()), bool),
            "DATA": vis[keep],
            "FLAG": values["flag"].reshape(ntime * nbl, nchan, ncorr)[keep],
            "WEIGHT_SPECTRUM": values["weight"].reshape(ntime * nbl, nchan, ncorr)[
                keep
            ],
            "UVW": uvw[keep],
            "FIELD_NAME": np.repeat(self.field_name[start:stop], nbl)[keep],
            "SCAN_NAME": np.repeat(self.scan_name[start:stop], nbl)[keep],
            "PADS": int(pad.sum()),
        }
        return out
