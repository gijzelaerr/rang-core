# SPDX-License-Identifier: MIT
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

`flag(store, config)` runs the flag stage on a store and writes `FLAG` back
into it (research/msv4-flag-write.md): the stage's chunk tasks
(`core_tasks.plan_flag`, `core_tasks.run`, any executor) over each
partition's rows, then one writer that changes only the flag variable's
values. It keeps no flag versions: flag a copy of a store you want to keep,
or use `rang-core flag CONFIG STORE` (research/msv4-cli.md), which keeps a
run directory, flag versions and a journal (`rang.msv4_flags`).

The schema is read as is; no telescope is assumed. xarray, zarr 3 and
numcodecs come from the optional `[msv4]` extra and are imported only when a
store is opened.
"""

import hashlib
import re
import time as _time
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
CORR_CODES = {"RR": 5, "RL": 6, "LR": 7, "LL": 8, "XX": 9, "XY": 10, "YX": 11, "YY": 12}
# `flag.column` to the data group it reads (research/msv4-flag-write.md 3).
COLUMN_GROUPS = {"DATA": "base", "CORRECTED_DATA": "corrected", "MODEL_DATA": "model"}


def is_store(path):
    """True when `path` is a zarr directory (`zarr.json` or `.zgroup`) and
    not a casacore table (`table.dat`): the stores `rang-core` takes."""
    path = Path(path)
    if not path.is_dir() or (path / "table.dat").exists():
        return False
    return (path / "zarr.json").is_file() or (path / ".zgroup").is_file()


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
        if not has_msv4():
            raise ImportError(
                "rang.msv4 needs the extra: pip install 'rang-core[msv4]' (Python 3.11+)"
            )
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

    def cells(self):
        """(time index, baseline index) of every row `rows()` yields, in its
        order (pads dropped by the same rule): UVW first, VISIBILITY only at
        the times where some cell's UVW is all NaN."""
        if getattr(self, "_cells", None) is None:
            uvw = np.asarray(self.ds[self.variables["uvw"]].values)
            pad = np.isnan(uvw).all(axis=2)
            vis = self.ds[self.variables["correlated_data"]]
            for t in np.flatnonzero(pad.any(axis=1)):
                v = np.asarray(vis.isel(time=int(t)).values)
                pad[t] &= np.isnan(v).reshape(v.shape[0], -1).all(axis=1)
            ti, bi = np.nonzero(~pad)
            self._cells = (ti.astype(np.int64), bi.astype(np.int64))
        return self._cells

    def metadata(self):
        """The flag kernel's metadata from the store: antenna positions in
        `antenna_names` order, channel frequencies and widths, correlation
        codes. Refused (ValueError) when the store lacks one."""
        ant = self.node["antenna_xds"].ds
        if "ANTENNA_POSITION" not in ant:
            raise ValueError(f"{self.name}: antenna_xds has no ANTENNA_POSITION")
        pos = np.asarray(
            ant["ANTENNA_POSITION"].transpose("antenna_name", ...).values, np.float64
        )
        width = self.ds["frequency"].attrs.get("channel_width")
        if isinstance(width, dict):
            width = width.get("data")
        if width is None:
            raise ValueError(f"{self.name}: frequency has no channel_width")
        width = np.broadcast_to(
            np.asarray(width, np.float64), self.frequency.shape
        ).astype(np.float64)
        unknown = [p for p in self.polarization if p not in CORR_CODES]
        if unknown:
            raise ValueError(f"{self.name}: polarization {unknown} has no MSv2 code")
        corr = np.asarray([CORR_CODES[p] for p in self.polarization], np.int32)
        return {
            "antenna_position": pos,
            "chan_freq": np.asarray(self.frequency, np.float64),
            "chan_width": width,
            "corr_type": corr,
        }

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


# -- the flag stage on a store (research/msv4-flag-write.md) -----------------------


class RowSource:
    """A chunk task's reader of one partition: `getcol_rows(name, rows,
    chans)` for the rows `Partition.rows()` yields (indices in its order).
    `DATA`, `CORRECTED_DATA` and `MODEL_DATA` read the data group's
    correlated data, `FLAG` its flag (bool; uint8 under the M1 rule)."""

    def __init__(self, partition):
        self.partition = partition
        self.ti, self.bi = partition.cells()

    def getcol_rows(self, name, rows, chans=None):
        part = self.partition
        if name in COLUMN_GROUPS:
            var = part.variables["correlated_data"]
        elif name == "FLAG":
            var = part.variables["flag"]
        else:
            raise ValueError(f"{part.name}: the MSv4 row source has no column {name}")
        rows = np.asarray(rows, np.int64)
        ti, bi = self.ti[rows], self.bi[rows]
        t0, t1 = int(ti.min()), int(ti.max()) + 1
        block = np.asarray(part.ds[var].isel(time=slice(t0, t1)).values)
        if name == "FLAG":
            block = part._flag_as_bool(block)
        out = block[ti - t0, bi]
        if chans is not None:
            out = out[:, chans]
        return np.ascontiguousarray(out)


def row_source(store, partition, data_group="base"):
    """The `RowSource` of `partition` in the store at `store` (a worker's)."""
    return RowSource(open_processing_set(store).partition(partition, data_group))


def _strategy(config, config_path):
    from . import core_flag

    value = config["flag"]["strategy"]
    if value is None:
        raise ValueError("flag.strategy is required")
    path = Path(value).expanduser()
    if not path.is_absolute() and config_path is not None:
        path = Path(config_path).resolve().parent / path
    if not path.is_file():
        raise ValueError(f"flag.strategy: {path} not found")
    text = path.read_text(encoding="utf-8")
    core_flag.parse_strategy(text)  # refused here, not in a worker
    return path, text


# xradio 1.3.1 names a field `<MSv2 name>_<FIELD_ID>` (research/msv4-cli.md A3).
_FIELD_SUFFIX = re.compile(r"^(.+)_(0|[1-9][0-9]*)$")


def _field_source_nodes(node):
    return [
        child
        for child in node.children.values()
        if str(child.attrs.get("type", "")).startswith("field_and_source")
    ]


def field_map(parts):
    """{stored field name: (MSv2 FIELD name, FIELD id or None)} of a store's
    partitions (research/msv4-cli.md amendment A3). A `FIELD_ID` variable
    over a field-and-source `field_name` gives the id, and the name loses
    `_<id>` only when it ends so. Without one, on a store every partition of
    which xradio wrote, every name must be `<stem>_<id>` with one stem per id
    in the whole store; then the stem and id are the MSv2 ones. Otherwise
    (xarray-ms, a name or id that fails) the names stay and the ids are
    None."""
    names, declared, writers = set(), {}, set()
    for part in parts:
        names.update(str(f) for f in part.field_name)
        creator = part.node.attrs.get("creator") or {}
        writers.add(str(creator.get("software_name", "")))
        for fs in _field_source_nodes(part.node):
            ds = fs.ds
            if "field_name" not in ds.coords:
                continue
            stored = [str(v) for v in np.atleast_1d(ds["field_name"].values)]
            names.update(stored)
            if "FIELD_ID" in ds.data_vars and ds["FIELD_ID"].dims == ("field_name",):
                ids = np.atleast_1d(np.asarray(ds["FIELD_ID"].values)).tolist()
                for name, fid in zip(stored, ids):
                    declared[name] = int(fid)
    same = {n: (n, None) for n in names}
    if declared:
        out = dict(same)
        for name, fid in declared.items():
            suffix = f"_{fid}"
            stem = name.removesuffix(suffix)
            out[name] = (stem or name, fid)
        return out
    if writers != {"xradio"}:
        return same
    out, stems = {}, {}
    for name in names:
        match = _FIELD_SUFFIX.match(name)
        if match is None:
            return same
        stem, fid = match.group(1), int(match.group(2))
        if stems.setdefault(fid, stem) != stem:
            return same
        out[name] = (stem, fid)
    return out


def _selected_fields(tokens, fmap):
    """The stored field names `flag.fields` selects: a token is a field's
    MSv2 name or its stored name (A3); None for all."""
    tokens = [str(t) for t in (tokens or ["all"])]
    if "all" in tokens:
        return None
    out, missing, clash = set(), [], []
    for token in tokens:
        by_name = {s for s, (n, _) in fmap.items() if n == token}
        by_store = {token} if token in fmap else set()
        if by_store and by_name - by_store:
            clash.append(
                f"{token!r} is the stored name of {sorted(by_store)} and the "
                f"MSv2 name of {sorted(by_name - by_store)}"
            )
        elif by_name or by_store:
            out |= by_name | by_store
        else:
            missing.append(token)
    if clash:
        raise ValueError("flag.fields: ambiguous on this store: " + "; ".join(clash))
    if missing:
        known = sorted({n for n, _ in fmap.values()} | set(fmap))
        raise ValueError(
            f"flag.fields {missing}: an MSv4 store takes all or field names "
            f"({known}); roles and ids are not read here"
        )
    return out


def _groups(rows, field, scan, pindex):
    """{(field code, partition, scan code): row indices} and the names."""
    field_names = sorted({str(f) for f in field[rows]})
    scan_names = sorted({str(s) for s in scan[rows]})
    fcode = {f: i for i, f in enumerate(field_names)}
    scode = {s: i for i, s in enumerate(scan_names)}
    key = np.asarray(
        [[fcode[str(field[r])], pindex, scode[str(scan[r])]] for r in rows],
        np.int64,
    ).reshape(-1, 3)
    groups = {}
    if len(rows):
        uniq, inverse = np.unique(key, axis=0, return_inverse=True)
        inverse = np.asarray(inverse).reshape(-1)
        groups = {
            tuple(int(v) for v in k): rows[inverse == i] for i, k in enumerate(uniq)
        }
    return groups, field_names, scan_names


def flag(store, config, config_path=None, max_rows=None, on_write=None):
    """Run the flag stage on the processing set at `store` and write `FLAG`
    into it (research/msv4-flag-write.md). `config` is a resolved ra-ng
    configuration (`core_config.validate`) or the path of one. Each
    partition's groups (per field and scan) become `core_tasks.plan_flag`
    specs, mapped by `core_tasks.executor(config)`; the partials are written
    after the map, by this process only, into the flag variable's values.
    `max_rows` cuts a larger group into blocks of baselines.
    `on_write(partition)` is called before each partition's write (the
    command line's journal). Returns a summary."""
    from . import core_config

    if isinstance(config, (str, Path)):
        config_path = Path(config)
        config = core_config.validate_file(config, ["flag"])
    plan = prepare_flag(store, config, config_path)
    return run_flag(store, config, plan, max_rows=max_rows, on_write=on_write)


def prepare_flag(store, config, config_path=None):
    """What `flag` reads before it runs, checked: the column's data group,
    the strategy, the masks, the field and scan selection and the
    partitions. Raises ValueError for what a store cannot take (the
    command line refuses these before anything is written)."""
    from . import core_flag

    cfg = config["flag"]
    if cfg.get("flagger", "tricolour") != "tricolour":
        raise ValueError(f"flag.flagger {cfg['flagger']!r}: only tricolour on MSv4")
    learned = cfg.get("learned") or {}
    if learned.get("mode", "off") != "off":
        raise ValueError("flag.learned: learned modes are not run on MSv4")
    column = cfg["column"]
    if column not in COLUMN_GROUPS:
        raise ValueError(
            f"flag.column {column!r}: an MSv4 store takes {list(COLUMN_GROUPS)}"
        )
    data_group = COLUMN_GROUPS[column]
    strategy_path, text = _strategy(config, config_path)
    if cfg["static_masks"] == "tricolour":
        mask_files = core_flag.static_mask_files()
        masks = [core_flag.load_static_mask(p) for p in mask_files]
    else:
        mask_files, masks = [], []
    scans = {str(s) for s in (config["data"].get("scans") or [])}
    store = Path(store)
    ps = open_processing_set(store)
    if ps.refused:
        raise ValueError(f"{store}: partitions refused: {ps.refused}")
    if not ps.names:
        raise ValueError(f"{store}: no visibility partition")
    parts = ps.partitions(data_group)
    for part in parts:
        part.metadata()  # refused here when the store lacks what the kernel reads
    fmap = field_map(parts)
    fields = _selected_fields(cfg["fields"], fmap)
    return {
        "column": column,
        "data_group": data_group,
        "strategy_path": strategy_path,
        "text": text,
        "mask_files": mask_files,
        "masks": masks,
        "scans": scans,
        "fields": fields,
        "field_map": fmap,
        "parts": parts,
        "telescope": telescope(ps),
    }


def telescope(ps):
    """`overall_telescope_name` of the first partition's `antenna_xds`."""
    for name in ps.names:
        node = ps.tree[name]
        if "antenna_xds" in node.children:
            value = node["antenna_xds"].attrs.get("overall_telescope_name")
            if value:
                return str(value)
    return ""


def run_flag(store, config, plan, max_rows=None, on_write=None):
    """`flag` with the checked `plan` of `prepare_flag`."""
    import zarr

    from . import core_tasks

    cfg = config["flag"]
    column, data_group = plan["column"], plan["data_group"]
    text, masks = plan["text"], plan["masks"]
    scans, fields, parts = plan["scans"], plan["fields"], plan["parts"]
    fmap = plan.get("field_map") or field_map(parts)
    store = Path(store)
    summary = {
        "store": str(store),
        "strategy": str(plan["strategy_path"]),
        "strategy_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "static_masks": [p.name for p in plan["mask_files"]],
        "write": cfg["write"],
        "column": column,
        "data_group": data_group,
        "partitions": [],
    }
    t_start = _time.perf_counter()
    with core_tasks.executor(config) as ex:
        for pindex, part in enumerate(parts):
            source = RowSource(part)
            ti, bi = source.ti, source.bi
            meta = part.metadata()
            field = part.field_name[ti]
            scan = part.scan_name[ti]
            keep = np.ones(len(ti), bool)
            if fields is not None:
                keep &= np.isin(field.astype(str), sorted(fields))
            if scans:
                keep &= np.isin(scan.astype(str), sorted(scans))
            rows = np.flatnonzero(keep)
            groups, field_names, scan_names = _groups(rows, field, scan, pindex)
            info = {
                "rows": {
                    "ANTENNA1": part.antenna1[bi],
                    "ANTENNA2": part.antenna2[bi],
                    "TIME": part.time[ti],
                },
                **meta,
            }
            limit = len(ti) + 1 if max_rows is None else int(max_rows)
            specs, blocks = core_tasks.plan_flag(
                store, info, groups, limit, column, cfg["write"], text, masks
            )
            for spec in specs:
                spec.params["msv4"] = {"partition": part.name, "data_group": data_group}
            # No store write while tasks are in flight (a worker may be
            # reading the chunk): keep the partials, write after the map.
            new = {}
            totals = [[0, 0, 0.0] for _ in groups]
            for spec, result in zip(specs, ex.map(specs, source)):
                for r, f in zip(result["rows"], result["flag"]):
                    new[int(r)] = f
                total = totals[spec.key["group"]]
                total[0] += result["before"]
                total[1] += result["after"]
                total[2] += result["seconds"]
            if on_write is not None and new:
                on_write(part.name)  # the journal records FLAG before the put
            record = _write_flags(zarr, store, part, ti, bi, new)
            cells = int(len(part.frequency) * len(part.polarization))
            summary["partitions"].append(
                {
                    "name": part.name,
                    "rows": len(ti),
                    "rows_flagged": len(rows),
                    "selected_flagged_before": int(sum(t[0] for t in totals)),
                    "selected_flagged_after": int(sum(t[1] for t in totals)),
                    "blocks": blocks,
                    "groups": [
                        {
                            **_field_record(fmap, field_names[k[0]]),
                            "scan": scan_names[k[2]],
                            "rows": len(idx),
                            "flagged_before": b / (len(idx) * cells),
                            "flagged_after": a / (len(idx) * cells),
                            "core_seconds": sec,
                        }
                        for (k, idx), (b, a, sec) in zip(groups.items(), totals)
                    ],
                    **record,
                }
            )
        summary["executor"] = ex.describe()
    summary["seconds"] = _time.perf_counter() - t_start
    return summary


def _field_record(fmap, stored):
    """A group's `field` (MSv2 name), `field_id` and `store_field` (A3)."""
    name, fid = fmap.get(stored, (stored, None))
    return {"field": name, "field_id": fid, "store_field": stored}


def _write_flags(zarr, store, part, ti, bi, new):
    """Write the flags `new` ({row: (chan, corr) bool}) of `part` into its
    flag variable, one time chunk at a time; pads and rows not in `new`
    keep their stored values, and the stored dtype is kept."""
    var = part.variables["flag"]
    record = {"flag_variable": var, "time_writes": 0}
    rows = np.asarray(sorted(new), np.int64)
    if not len(rows):
        return record
    array = zarr.open_array(store=str(Path(store) / part.name / var), mode="r+")
    if tuple(array.shape[:2]) != (len(part.time), part.nbaseline):
        raise ValueError(f"{part.name}: {var} has shape {array.shape}")
    step = int(array.chunks[0]) or len(part.time)
    t_rows = ti[rows]
    for c0 in range(0, len(part.time), step):
        c1 = min(c0 + step, len(part.time))
        here = rows[(t_rows >= c0) & (t_rows < c1)]
        if not len(here):
            continue
        block = np.asarray(array[c0:c1])
        values = np.stack([new[int(r)] for r in here])
        block[ti[here] - c0, bi[here]] = values.astype(block.dtype)
        array[c0:c1] = block
        record["time_writes"] += 1
    digest = hashlib.sha256()
    for r in rows:
        digest.update(np.ascontiguousarray(new[int(r)]).tobytes())
    record["flag_dtype"] = str(array.dtype)
    record["flagged_cells"] = int(sum(int(new[int(r)].sum()) for r in rows))
    record["flag_sha256"] = digest.hexdigest()
    return record
