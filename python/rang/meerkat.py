"""MeerKAT MVFv4 archives into the core's arrays (research/mk1-katdal.md).

Opens a MeerKAT visibility archive (an RDB URL, with its token if any, or a
local `.rdb` beside its `.npy` chunk store) through katdal, the SARAO reader,
and yields row chunks in the core's layout: the keys and dtypes of
`core_fetch.decode_slice` (`ANTENNA1`, `ANTENNA2`, `TIME`, `FLAG_ROW`,
`DATA`, `FLAG`, `WEIGHT_SPECTRUM` as `(row, channel, corr)`), plus `UVW`,
the native uint8 flag bitfield `FLAG_BITS`, `SCAN_NUMBER` and `FIELD_ID`.

The conventions are those of katdal's own `mvftoms.py`, so a loader chunk
equals the MS it would write, row for row once rows are matched by
`(TIME, ANTENNA1, ANTENNA2)`:

- rows are time-major, baselines in lexicographic `(ANTENNA1, ANTENNA2)`
  order of `dataset.ants` indices (crosses only unless `autos=True`);
- correlations `XX, XY, YX, YY` are katdal's `hh, hv, vh, vv`; a product
  missing from the archive is zero, weight zero and flagged;
- `WEIGHT_SPECTRUM` is katdal's `weights`: stored `weights × weights_channel`,
  divided by the two autocorrelation powers when the stored weights are
  unscaled (`need_weights_power_scale`);
- `FLAG_BITS` is katdal's `raw_flags` (bits in `FLAG_BITS_TABLE`), `FLAG` is
  `(FLAG_BITS & mask) != 0` for the selected flag names; with
  `upgrade_flags=False` the bits are the L0 ingest flags, otherwise katdal
  substitutes the `sdp_l1_flags` stream (katsdpcal);
- `TIME` is `katpoint.Timestamp(t).to_mjd() * 24 * 60 * 60` and `UVW` is the
  per-antenna `target.uvw` difference `ANTENNA1 − ANTENNA2`, as
  `katdal/ms_async.py` computes them; `FLAG_ROW` is false (MVF has none).

katdal, katsdptelstate and katpoint come from the optional `[meerkat]` extra
and are imported only when an archive is opened. `write_synthetic_mvf`
writes a small MVFv4 archive with katdal's own chunk store and telstate
writers, the fixture of the acceptance checks (no public MVF exists).
"""

import itertools
import json
import time
from pathlib import Path

import numpy as np

POLS = ("hh", "hv", "vh", "vv")
CORR_NAMES = ("XX", "XY", "YX", "YY")
CORR_TYPES = (9, 10, 11, 12)
# katdal/flags.py, bit by bit.
FLAG_BITS_TABLE = (
    ("reserved0", "reserved - bit 0"),
    ("static", "predefined static flag list"),
    ("cam", "flag based on live CAM information"),
    ("data_lost", "no data was received"),
    ("ingest_rfi", "RFI detected in ingest"),
    ("predicted_rfi", "RFI predicted from space based pollutants"),
    ("cal_rfi", "RFI detected in calibration"),
    ("postproc", "some correction/postprocessing step could not be applied"),
)
FLAG_NAMES = tuple(name for name, _ in FLAG_BITS_TABLE)
# What L3 calls native observatory flags (research/mk1-katdal.md): the
# telescope's own masks and ingest decisions, not calibration or later steps.
NATIVE_FLAGS = ("static", "cam", "data_lost", "ingest_rfi", "predicted_rfi")
TRACK_STATES = ("track", "scan")


def has_katdal():
    """True when the `[meerkat]` extra is installed."""
    try:
        import katdal  # noqa: F401
    except ImportError:
        return False
    return True


def flag_mask(names="all"):
    """The uint8 mask of flag `names` ('all', a name, or a sequence)."""
    if isinstance(names, str):
        names = FLAG_NAMES if names == "all" else [n for n in names.split(",") if n]
    mask = 0
    for name in names:
        if name not in FLAG_NAMES:
            raise ValueError(f"unknown flag {name!r}; one of {FLAG_NAMES}")
        mask |= 1 << FLAG_NAMES.index(name)
    return np.uint8(mask)


def baselines(nants, autos=False):
    """(ANTENNA1, ANTENNA2) in lexicographic order, ANTENNA1 < ANTENNA2 (or <=)."""
    a1, a2 = np.triu_indices(nants, 0 if autos else 1)
    return a1.astype(np.int32), a2.astype(np.int32)


def corrprod_index(corr_products, ant_names, a1, a2):
    """(baseline, corr) → index into katdal's corrprod axis, -1 where missing."""
    lookup = {(str(x), str(y)): n for n, (x, y) in enumerate(corr_products)}
    index = np.full((len(a1), len(POLS)), -1, np.int64)
    for b, (i, j) in enumerate(zip(a1, a2)):
        for p, pol in enumerate(POLS):
            index[b, p] = lookup.get((ant_names[i] + pol[0], ant_names[j] + pol[1]), -1)
    return index


def to_rows(array, cp_index, fill):
    """(time, channel, corrprod) → (time × baseline, channel, corr)."""
    ntime, nchan, _ = array.shape
    nbl = cp_index.shape[0]
    out = array[:, :, np.maximum(cp_index, 0)]  # (time, channel, baseline, corr)
    if np.any(cp_index < 0):
        out[:, :, cp_index < 0] = fill
    return np.ascontiguousarray(out.transpose(0, 2, 1, 3)).reshape(
        ntime * nbl, nchan, len(POLS)
    )


def public_source(source):
    """`source` without a URL query string or fragment, where an archive
    token lives; this is what metadata and receipts record."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(str(source))
    if parts.scheme in ("http", "https"):
        return urlunsplit(parts._replace(query="", fragment=""))
    return str(source)


def mjd_seconds(timestamps):
    """MS TIME exactly as katdal/ms_async.py converts UTC seconds."""
    import katpoint

    return np.asarray(
        [katpoint.Timestamp(t).to_mjd() * 24 * 60 * 60 for t in timestamps],
        dtype=np.float64,
    )


def antenna_uvw(target, ants, timestamps):
    """(time, antenna, 3) UVW of each antenna as ms_async.py computes it, one
    `target.uvw` call per dump (mvftoms writes one dump per call)."""
    reference = ants[0].array_reference_antenna()
    out = np.empty((len(timestamps), len(ants), 3))
    for n in range(len(timestamps)):
        uvw = np.asarray(target.uvw(ants, timestamps[n : n + 1], reference))
        out[n] = np.transpose(uvw, (1, 2, 0))[0]
    return out


class MvfLoader:
    """An open MVF dataset with a row-chunk view in the core's layout."""

    def __init__(self, dataset, source, upgrade_flags, open_seconds):
        self.dataset = dataset
        self.source = public_source(source)
        self.upgrade_flags = upgrade_flags
        self.open_seconds = open_seconds
        self.autos = False
        self.states = TRACK_STATES
        self.min_scan_dumps = 2
        self.mask = flag_mask("all")
        self.selection = {}
        self.select()

    # --- selection ------------------------------------------------------------

    def select(
        self,
        scans=None,
        targets=None,
        antennas=None,
        channels=None,
        autos=False,
        flags="all",
        states=TRACK_STATES,
        min_scan_dumps=2,
    ):
        """Select from the whole dataset (each call starts afresh).

        `scans` are katdal scan indices, `targets` names, `antennas` names,
        `channels` a slice or boolean mask; `flags` the flag names that make
        FLAG (FLAG_BITS keeps every bit). Only scans in `states` with at least
        `min_scan_dumps` dumps are read, as mvftoms writes them.
        """
        kwargs = {} if autos else {"corrprods": "cross"}
        if scans is not None:
            kwargs["scans"] = scans
        if targets is not None:
            kwargs["targets"] = targets
        if antennas is not None:
            kwargs["ants"] = antennas
        if channels is not None:
            kwargs["channels"] = channels
        self.dataset.select(reset="TFB", **kwargs)
        self.autos = autos
        self.states = tuple(states)
        self.min_scan_dumps = int(min_scan_dumps)
        self.mask = flag_mask(flags)
        self.selection = {
            "scans": scans,
            "targets": targets,
            "antennas": antennas,
            "channels": None if channels is None else _jsonable(channels),
            "autos": autos,
            "flags": flags if isinstance(flags, str) else list(flags),
            "states": list(self.states),
            "min_scan_dumps": self.min_scan_dumps,
        }
        return self

    # --- metadata -------------------------------------------------------------

    def metadata(self):
        """Antennas, frequencies, correlations, scans and provenance."""
        import katdal
        import katsdptelstate

        ds = self.dataset
        scans = []
        for index, state, target in ds.scans():
            scans.append(
                {
                    "index": int(index),
                    "state": str(state),
                    "target": target.name,
                    "tags": list(target.tags),
                    "dumps": int(ds.shape[0]),
                }
            )
        attrs = ds.source.metadata.attrs
        return {
            "source": self.source,
            "name": ds.name,
            "katdal": katdal.__version__,
            "katsdptelstate": katsdptelstate.__version__,
            "upgrade_flags": self.upgrade_flags,
            "need_weights_power_scale": bool(
                attrs.get("need_weights_power_scale", False)
            ),
            "antennas": [a.name for a in ds.ants],
            "positions_ecef": [list(map(float, a.position_ecef)) for a in ds.ants],
            "diameters": [float(a.diameter) for a in ds.ants],
            "channel_freqs": ds.channel_freqs.tolist(),
            "channel_width": float(ds.channel_width),
            "corr_names": list(CORR_NAMES),
            "corr_types": list(CORR_TYPES),
            "dump_period": float(ds.dump_period),
            "shape": [int(x) for x in ds.shape],
            "scans": scans,
            "targets": [t.description for t in ds.catalogue.targets],
            "flag_bits": [
                {"bit": b, "name": n, "description": d}
                for b, (n, d) in enumerate(FLAG_BITS_TABLE)
            ],
            "flag_mask": int(self.mask),
            "selection": self.selection,
        }

    # --- data -------------------------------------------------------------------

    def iter_chunks(self, dumps=None):
        """Yield row chunks (dicts of arrays) scan by scan.

        `dumps` per chunk defaults to the store's own dump chunking, so each
        chunk reads whole stored chunks; chunks never span scans.
        """
        from katdal.lazy_indexer import DaskLazyIndexer

        ds = self.dataset
        ants = list(ds.ants)
        names = [a.name for a in ants]
        a1, a2 = baselines(len(ants), self.autos)
        cp_index = corrprod_index(ds.corr_products, names, a1, a2)
        nbl = len(a1)
        field_names = []
        scan_number = 0
        for _, state, target in ds.scans():
            ntime = ds.shape[0]
            if state not in self.states or ntime < self.min_scan_dumps:
                continue
            scan_number += 1
            if target.name not in field_names:
                field_names.append(target.name)
            field_id = field_names.index(target.name)
            timestamps = ds.timestamps[:]
            if dumps is None:
                bounds = np.cumsum((0,) + tuple(ds.vis.dataset.chunks[0]))
            else:
                bounds = np.append(np.arange(0, ntime, int(dumps)), ntime)
            for start, stop in itertools.pairwise(bounds):
                started = time.perf_counter()
                shape = (int(stop - start),) + tuple(ds.shape[1:])
                vis = np.empty(shape, np.complex64)
                weights = np.empty(shape, np.float32)
                bits = np.empty(shape, np.uint8)
                DaskLazyIndexer.get(
                    [ds.vis, ds.weights, ds.raw_flags],
                    np.s_[start:stop],
                    out=[vis, weights, bits],
                )
                read_seconds = time.perf_counter() - started
                t = timestamps[start:stop]
                nt = len(t)
                uvw_ant = antenna_uvw(target, ants, t)
                flag_bits = to_rows(bits, cp_index, 0)
                if np.any(cp_index < 0):
                    # A missing product is flagged (mvftoms); no bit says why.
                    missing = np.broadcast_to(cp_index < 0, (nt, nbl, len(POLS)))
                    flags_missing = np.repeat(
                        missing.reshape(nt * nbl, 1, len(POLS)), shape[1], axis=1
                    )
                else:
                    flags_missing = None
                flag = (flag_bits & self.mask) != 0
                if flags_missing is not None:
                    flag |= flags_missing
                chunk = {
                    "ANTENNA1": np.tile(a1, nt),
                    "ANTENNA2": np.tile(a2, nt),
                    "TIME": np.repeat(mjd_seconds(t), nbl),
                    "FLAG_ROW": np.zeros(nt * nbl, bool),
                    "UVW": (uvw_ant[:, a1] - uvw_ant[:, a2]).reshape(nt * nbl, 3),
                    "DATA": to_rows(vis, cp_index, 0),
                    "FLAG": flag,
                    "WEIGHT_SPECTRUM": to_rows(weights, cp_index, 0),
                    "FLAG_BITS": flag_bits,
                    "SCAN_NUMBER": np.full(nt * nbl, scan_number, np.int32),
                    "FIELD_ID": np.full(nt * nbl, field_id, np.int32),
                    "_stats": {
                        "dumps": [int(start), int(stop)],
                        "rows": int(nt * nbl),
                        "read_seconds": read_seconds,
                        "total_seconds": time.perf_counter() - started,
                        "bytes_in": int(vis.nbytes + weights.nbytes + bits.nbytes),
                        "target": target.name,
                    },
                }
                yield chunk

    def read(self, dumps=None):
        """All selected rows as one chunk dict (concatenated `iter_chunks`)."""
        parts = list(self.iter_chunks(dumps))
        if not parts:
            raise ValueError("selection holds no track/scan dumps")
        out = {
            key: np.concatenate([p[key] for p in parts])
            for key in parts[0]
            if not key.startswith("_")
        }
        out["_stats"] = [p["_stats"] for p in parts]
        return out

    def save_chunks(self, out, dumps=None):
        """Write each chunk as `chunk-NNNNN/<KEY>.npy` and a `manifest.json`,
        the MS-free path for campaign drivers. Returns the manifest."""
        out = Path(out)
        if out.exists():
            raise FileExistsError(f"{out} exists; use a fresh output directory")
        out.mkdir(parents=True)
        manifest = {"metadata": self.metadata(), "chunks": []}
        for n, chunk in enumerate(self.iter_chunks(dumps)):
            folder = out / f"chunk-{n:05d}"
            folder.mkdir()
            for key, value in chunk.items():
                if not key.startswith("_"):
                    np.save(folder / f"{key}.npy", value)
            manifest["chunks"].append({"path": folder.name, **chunk["_stats"]})
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        return manifest


def load_saved_chunk(folder):
    """A chunk written by `MvfLoader.save_chunks`, as a dict of arrays."""
    return {p.stem: np.load(p) for p in sorted(Path(folder).glob("*.npy"))}


def open_mvf(source, *, ref_ant="", upgrade_flags=True, van_vleck="off", **kwargs):
    """Open an MVFv4 dataset (RDB URL or local `.rdb`) through katdal.

    `upgrade_flags=False` keeps the L0 ingest flag bits instead of katdal's
    default substitution of the `sdp_l1_flags` stream. Extra keyword
    arguments go to `katdal.open` (e.g. `chunk_store`, `token`).
    """
    try:
        import katdal
    except ImportError as error:
        raise ImportError(
            "rang.meerkat needs the [meerkat] extra: pip install 'rang-core[meerkat]'"
        ) from error
    started = time.perf_counter()
    dataset = katdal.open(
        str(source),
        ref_ant=ref_ant,
        upgrade_flags=upgrade_flags,
        van_vleck=van_vleck,
        **kwargs,
    )
    return MvfLoader(dataset, source, upgrade_flags, time.perf_counter() - started)


def _jsonable(value):
    if isinstance(value, slice):
        return [value.start, value.stop, value.step]
    return np.asarray(value).tolist()


# --- a synthetic MVFv4 archive (the acceptance fixture) ----------------------

# MeerKAT reference position (katpoint's array reference for MeerKAT).
MEERKAT_REFERENCE = "-30:42:39.8, 21:26:38.0, 1035.0"
TARGETS = (
    "J1939-6342 | PKS 1934-638, radec bpcal, 19:39:25.03, -63:42:45.6",
    "J1331+3030 | 3C 286, radec gaincal, 13:31:08.29, 30:30:33.0",
)


def write_synthetic_mvf(
    root,
    *,
    cbid="1700000000",
    n_ants=7,
    n_dumps=24,
    n_chans=64,
    dump_chunk=5,
    chan_chunk=16,
    seed=20261030,
    drop_chunk=True,
    zero_auto=True,
    l1_flags=True,
    shuffle=True,
    sync_time=1700000000.0,
    int_time=7.997,
):
    """Write a small MVFv4 archive under `root` with katdal's own writers.

    Layout as on the SARAO archive: `<root>/<cbid>/<cbid>_sdp_l0.rdb` and the
    chunk store `<root>/<cbid>-sdp-l0/<array>/<i>_<j>_<k>.npy`. The archive is
    adversarial on purpose: shuffled `bls_ordering`, partial edge chunks, two
    track scans on two targets around a slew, every flag bit used, an
    `sdp_l1_flags` stream that differs from L0, one deleted visibility chunk
    and one zero autocorrelation. Returns a dict with the paths, the stored
    arrays and the parameters.

    The telstate key layout and the chunk_info records are adapted from
    katdal 0.23's test helpers `_make_fake_stream` / `make_fake_data_source`
    (`katdal/test/test_datasources.py`) and `put_fake_dataset`
    (`test_vis_flags_weights.py`), BSD-3-Clause, National Research
    Foundation (SARAO); extended with the keys `VisibilityDataV4` and
    `mvftoms.py` need (antennas, sensors, targets, obs_params).
    """
    import dask.array as da
    import katpoint
    import katsdptelstate
    from katdal.chunkstore_npy import NpyFileChunkStore
    from katsdptelstate.rdb_writer import RDBWriter

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    names = [f"m{n:03d}" for n in range(n_ants)]
    # East, north, up offsets in metres, on the MeerKAT scale.
    enu = np.column_stack(
        [
            rng.uniform(-4000, 4000, n_ants),
            rng.uniform(-4000, 4000, n_ants),
            rng.uniform(-5, 5, n_ants),
        ]
    )
    descriptions = {
        name: f"{name}, {MEERKAT_REFERENCE}, 13.5, {e:.4f} {n:.4f} {u:.4f}, , 1.22"
        for name, (e, n, u) in zip(names, enu)
    }
    bls = [
        (names[i] + x, names[j] + y)
        for i in range(n_ants)
        for j in range(i, n_ants)
        for x in "hv"
        for y in "hv"
    ]
    order = rng.permutation(len(bls)) if shuffle else np.arange(len(bls))
    bls = [bls[k] for k in order]
    n_bls = len(bls)
    shape = (n_dumps, n_chans, n_bls)
    vis = (rng.normal(size=shape) + 1j * rng.normal(size=shape)).astype(np.complex64)
    autos = [k for k, (x, y) in enumerate(bls) if x[:-1] == y[:-1] and x[-1] == y[-1]]
    vis[:, :, autos] = (np.abs(vis[:, :, autos].real) + 1.0).astype(np.float32)
    if zero_auto:
        vis[3, 5, autos[0]] = 0
    weights = rng.integers(1, 256, shape, dtype=np.uint8)
    weights_channel = rng.uniform(0.5, 2.0, shape[:2]).astype(np.float32)
    flags = np.zeros(shape, np.uint8)
    for bit in range(8):
        flags |= (rng.random(shape) < 0.04).astype(np.uint8) << bit
    # The L1 stream: extra calibration RFI (bit 6), half the ingest RFI (bit 4) cleared.
    l1 = flags | ((rng.random(shape) < 0.1).astype(np.uint8) << 6)
    l1[rng.random(shape) < 0.5] &= np.uint8(0xFF ^ (1 << 4))
    chunks = {
        "correlator_data": (dump_chunk, chan_chunk, n_bls),
        "flags": (dump_chunk, chan_chunk, n_bls),
        "weights": (dump_chunk, chan_chunk, n_bls),
        "weights_channel": (dump_chunk, chan_chunk),
    }
    arrays = {
        "correlator_data": vis,
        "flags": flags,
        "weights": weights,
        "weights_channel": weights_channel,
    }
    store = NpyFileChunkStore(str(root))
    telstate = katsdptelstate.TelescopeState()

    def put(stream, data):
        prefix = f"{cbid}-{stream.replace('_', '-')}"
        info = {}
        for key, array in data.items():
            darray = da.from_array(array, chunks=chunks[key])
            store.create_array(store.join(prefix, key))
            da.compute(store.put_dask_array(store.join(prefix, key), darray))
            info[key] = {
                "prefix": prefix,
                "chunks": darray.chunks,
                "dtype": np.lib.format.dtype_to_descr(darray.dtype),
                "shape": darray.shape,
            }
        return prefix, info

    l0_prefix, l0_info = put("sdp_l0", arrays)
    first_timestamp = 0.5 * int_time + 13.0
    for stream, info, kind in (
        ("sdp_l0", l0_info, "sdp.vis"),
        *((("sdp_l1_flags", None, "sdp.flags"),) if l1_flags else ()),
    ):
        if info is None:
            _, info = put(stream, {"flags": l1})
        cs_view = telstate.view(telstate.join(cbid, stream))
        s_view = telstate.view(stream)
        cs_view["chunk_info"] = info
        cs_view["first_timestamp"] = first_timestamp
        s_view["sync_time"] = sync_time
        s_view["int_time"] = int_time
        s_view["bandwidth"] = 856e6
        s_view["center_freq"] = 1284e6
        s_view["n_chans"] = n_chans
        s_view["n_bls"] = n_bls
        s_view["bls_ordering"] = np.array(bls)
        s_view["stream_type"] = kind
        if kind == "sdp.vis":
            s_view["need_weights_power_scale"] = True
        else:
            s_view["src_streams"] = ["sdp_l0"]
    telstate["sdp_archived_streams"] = ["sdp_l0"] + (
        ["sdp_l1_flags"] if l1_flags else []
    )
    telstate["capture_block_id"] = cbid
    telstate["stream_name"] = "sdp_l0"
    telstate["sub_pool_resources"] = ",".join(["cbf_1", "sdp_1"] + names)
    telstate["sub_band"] = "l"
    telstate["sub_product"] = "c856M4k"
    telstate["obs_params"] = {
        "observer": "rang MK1 fixture",
        "description": "synthetic MVFv4 archive (research/mk1-katdal.md)",
        "experiment_id": "MK1-SYNTHETIC",
        "ants": ",".join(names),
    }
    for name in names:
        telstate[f"{name}_observer"] = descriptions[name]
    # Sensors: slew, track target 0, slew, track target 1 (dump boundaries).
    t0 = sync_time + first_timestamp
    edges = [0, 1, n_dumps // 2, n_dumps // 2 + 2]
    activity = ["slew", "track", "slew", "track"]
    target_at = [0, 0, 1, 1]
    labels = ["bandpass", "bandpass", "gain", "gain"]
    for edge, act, tgt, label in zip(edges, activity, target_at, labels):
        # A sensor event half a dump before the dump that it starts.
        ts = t0 + edge * int_time - 0.5 * int_time + 1e-3
        telstate.add("obs_activity", act, ts=ts)
        telstate.add("cbf_target", TARGETS[tgt], ts=ts)
        telstate.add("obs_label", label, ts=ts)
        for name in names:
            telstate.add(f"{name}_activity", act, ts=ts)
            telstate.add(f"{name}_target", TARGETS[tgt], ts=ts)
    dropped = None
    if drop_chunk:
        # The second dump chunk, third channel chunk: katdal sets data_lost.
        path = (
            root
            / l0_prefix
            / "correlator_data"
            / f"{dump_chunk:05d}_{2 * chan_chunk:05d}_00000.npy"
        )
        path.unlink()
        dropped = {
            "array": "correlator_data",
            "dumps": [dump_chunk, 2 * dump_chunk],
            "channels": [2 * chan_chunk, 3 * chan_chunk],
            "file": str(path.relative_to(root)),
        }
    rdb = root / cbid / f"{cbid}_sdp_l0.rdb"
    rdb.parent.mkdir(exist_ok=True)
    with RDBWriter(str(rdb)) as writer:
        writer.save(telstate)
    katpoint.Antenna(descriptions[names[0]])  # validates the descriptions
    return {
        "rdb": str(rdb),
        "root": str(root),
        "l0_prefix": l0_prefix,
        "arrays": arrays,
        "l1_flags": l1 if l1_flags else None,
        "bls_ordering": bls,
        "dropped": dropped,
        "zero_auto": [3, 5, autos[0]] if zero_auto else None,
        "params": {
            "cbid": cbid,
            "n_ants": n_ants,
            "n_dumps": n_dumps,
            "n_chans": n_chans,
            "dump_chunk": dump_chunk,
            "chan_chunk": chan_chunk,
            "seed": seed,
            "sync_time": sync_time,
            "int_time": int_time,
            "first_timestamp": first_timestamp,
            "scan_edges": edges,
            "activity": activity,
            "targets": list(TARGETS),
        },
    }


__all__ = [
    "CORR_NAMES",
    "CORR_TYPES",
    "FLAG_BITS_TABLE",
    "FLAG_NAMES",
    "NATIVE_FLAGS",
    "MvfLoader",
    "flag_mask",
    "has_katdal",
    "load_saved_chunk",
    "open_mvf",
    "public_source",
    "write_synthetic_mvf",
]
