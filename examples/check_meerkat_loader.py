"""MK1 acceptance: the MVFv4 loader against raw chunks, katdal and mvftoms.

Protocol: research/mk1-katdal.md (frozen before the loader was written).
Writes a synthetic MVFv4 archive with katdal's own writers into `--out`,
then measures:

  (a) the loader against arrays recomputed from the raw `.npy` chunks and
      the RDB's telstate values, and against katdal's own arrays, for the
      local `.rdb` and the same archive over HTTP (a 127.0.0.1 server);
  (b) the loader against `mvftoms.py -f --quack 0`'s MS read by rang.core_ms,
      rows matched by (TIME, ANTENNA1, ANTENNA2);
  (d) the native flag bitfield with and without katdal's flag upgrade;
  cost per chunk on the fixture and, with `--large`, on an L-band-scale
  synthetic set (64 antennas, 4,096 channels).

Writes `<out>/result.json`; `--archive` also copies the compact result to
research/results/mk1-katdal.json. Needs the [meerkat] extra and, for (b),
python-casacore and setuptools<81 (katdal's ms_extra imports pkg_resources).
"""

import argparse
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms, meerkat, rusage

ROOT = Path(__file__).resolve().parents[1]
DATA_LOST = np.uint8(1 << 3)


def equal(a, b):
    """Bitwise equality (NaN-safe for floats), shapes included."""
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    if a.dtype.kind in "fc":
        return bool(np.array_equal(a.view(np.uint8), b.view(np.uint8)))
    return bool(np.array_equal(a, b))


def report(name, a, b):
    a, b = np.asarray(a), np.asarray(b)
    out = {"equal": equal(a, b), "shape": list(a.shape), "dtype": str(a.dtype)}
    if not out["equal"] and a.shape == b.shape and a.dtype.kind in "fciub":
        diff = a.astype(np.complex128) - b.astype(np.complex128)
        out["mismatches"] = int(np.count_nonzero(diff))
        out["max_abs_diff"] = float(np.max(np.abs(diff)))
    elif not out["equal"]:
        out["other_shape"], out["other_dtype"] = list(b.shape), str(b.dtype)
    print(f"  {name}: {'exact' if out['equal'] else 'DIFFERS'} {out}")
    return out


# --- (a)1: the archive recomputed without katdal's DataSet ------------------


def raw_store_arrays(root, telstate_rdb, l1=True):
    """Full arrays from the `.npy` chunks and the RDB, no katdal DataSet."""
    import katsdptelstate

    telstate = katsdptelstate.TelescopeState()
    telstate.load_from_file(telstate_rdb)
    cbid = telstate["capture_block_id"]
    stream = telstate["stream_name"]
    view = telstate.view(stream).view(telstate.join(cbid, stream))
    info = view["chunk_info"]
    out, lost = {}, None
    for key, meta in info.items():
        array = np.zeros(meta["shape"], np.dtype(meta["dtype"]))
        missing = np.zeros(meta["shape"][:2], bool)
        offsets = [np.cumsum((0,) + tuple(c)) for c in meta["chunks"]]
        for index in np.ndindex(*[len(c) for c in meta["chunks"]]):
            start = [int(offsets[d][i]) for d, i in enumerate(index)]
            stop = [int(offsets[d][i + 1]) for d, i in enumerate(index)]
            name = "_".join(f"{s:05d}" for s in start) + ".npy"
            path = Path(root) / meta["prefix"] / key / name
            region = tuple(slice(a, b) for a, b in zip(start, stop))
            if path.exists():
                array[region] = np.load(path)
            else:
                missing[region[:2]] = True
        out[key] = array
        lost = missing if lost is None else lost | missing
    flags_l0 = out["flags"].copy()
    flags_l0[lost] |= DATA_LOST
    flags_l1 = None
    if l1:
        l1_view = telstate.view("sdp_l1_flags").view(
            telstate.join(cbid, "sdp_l1_flags")
        )
        meta = l1_view["chunk_info"]["flags"]
        flags_l1 = np.zeros(meta["shape"], np.uint8)
        offsets = [np.cumsum((0,) + tuple(c)) for c in meta["chunks"]]
        for index in np.ndindex(*[len(c) for c in meta["chunks"]]):
            start = [int(offsets[d][i]) for d, i in enumerate(index)]
            stop = [int(offsets[d][i + 1]) for d, i in enumerate(index)]
            name = "_".join(f"{s:05d}" for s in start) + ".npy"
            region = tuple(slice(a, b) for a, b in zip(start, stop))
            flags_l1[region] = np.load(Path(root) / meta["prefix"] / "flags" / name)
        flags_l1[lost] |= DATA_LOST
    # Weights: stored uint8 × weights_channel, divided by the autocorrelation powers.
    bls = [tuple(map(str, p)) for p in view["bls_ordering"]]
    where = {p: k for k, p in enumerate(bls)}
    stored = out["weights"] * out["weights_channel"][..., np.newaxis]
    auto_i = np.array([where[(x, x)] for x, _ in bls])
    auto_j = np.array([where[(y, y)] for _, y in bls])
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        recip = np.reciprocal(out["correlator_data"].real)  # float32
        scale = recip[:, :, auto_i] * recip[:, :, auto_j]
    scale[~np.isfinite(scale)] = np.float32(2.0**-32)
    weights = scale * stored if view["need_weights_power_scale"] else stored
    n_dumps = info["correlator_data"]["shape"][0]
    timestamps = (
        view["sync_time"]
        + view["first_timestamp"]
        + np.arange(n_dumps) * view["int_time"]
    )
    return {
        "vis": out["correlator_data"],
        "flags_l0": flags_l0,
        "flags_l1": flags_l1,
        "weights": weights.astype(np.float32),
        "timestamps": timestamps,
        "bls": bls,
        "lost": lost,
    }


def expected_rows(raw, dumps, channels, ant_names, autos=False, bits="l1"):
    """Rows (time-major, lexicographic baselines) by name lookup, one by one."""
    where = {p: k for k, p in enumerate(raw["bls"])}
    pols = ("hh", "hv", "vh", "vv")
    pairs = [
        (i, j)
        for i in range(len(ant_names))
        for j in range(len(ant_names))
        if (i < j or (autos and i == j))
    ]
    index = np.array(
        [
            [where[(ant_names[i] + p[0], ant_names[j] + p[1])] for p in pols]
            for i, j in pairs
        ]
    )
    flags = raw["flags_l1"] if bits == "l1" else raw["flags_l0"]
    take = np.ix_(dumps, channels)

    def rows(array):
        sub = array[take[0], take[1]]  # (time, channel, corrprod)
        sub = sub[:, :, index]  # (time, channel, baseline, corr)
        return np.ascontiguousarray(sub.transpose(0, 2, 1, 3)).reshape(
            -1, len(channels), 4
        )

    return {
        "ANTENNA1": np.tile([i for i, _ in pairs], len(dumps)).astype(np.int32),
        "ANTENNA2": np.tile([j for _, j in pairs], len(dumps)).astype(np.int32),
        "DATA": rows(raw["vis"]),
        "FLAG_BITS": rows(flags),
        "WEIGHT_SPECTRUM": rows(raw["weights"]),
        "timestamps": raw["timestamps"][dumps],
    }


def check_raw(loader, raw, label, bits="l1", **select):
    loader.select(**select)
    ds = loader.dataset
    dumps = _track_dumps(loader)
    channels = np.asarray(ds.channels)
    names = [a.name for a in ds.ants]
    got = loader.read()
    want = expected_rows(raw, dumps, channels, names, select.get("autos", False), bits)
    print(
        f"(a)1 {label}: dumps {len(dumps)}, channels {len(channels)}, ants {len(names)}"
    )
    nbl = len(want["ANTENNA1"]) // max(len(dumps), 1)
    result = {
        "selection": loader.selection,
        "rows": len(got["TIME"]),
        "ANTENNA1": report("ANTENNA1", got["ANTENNA1"], want["ANTENNA1"]),
        "ANTENNA2": report("ANTENNA2", got["ANTENNA2"], want["ANTENNA2"]),
        "DATA": report("DATA", got["DATA"], want["DATA"]),
        "FLAG_BITS": report("FLAG_BITS", got["FLAG_BITS"], want["FLAG_BITS"]),
        "FLAG": report("FLAG", got["FLAG"], (want["FLAG_BITS"] & loader.mask) != 0),
        "WEIGHT_SPECTRUM": report(
            "WEIGHT_SPECTRUM", got["WEIGHT_SPECTRUM"], want["WEIGHT_SPECTRUM"]
        ),
        "TIME": report(
            "TIME",
            got["TIME"],
            np.repeat(meerkat.mjd_seconds(want["timestamps"]), nbl),
        ),
    }
    return result


def _track_dumps(loader):
    """Dumps the loader reads: katdal's scan partition (track/scan scans)."""
    ds = loader.dataset
    dumps = [
        ds.dumps.copy()
        for _, state, _ in ds.scans()
        if state in loader.states and ds.shape[0] >= loader.min_scan_dumps
    ]
    return np.concatenate(dumps)


# --- (a)2-4: katdal's own arrays ------------------------------------------------


def check_katdal(loader, label, **select):
    loader.select(**select)
    ds = loader.dataset
    got = loader.read()
    names = [a.name for a in ds.ants]
    a1, a2 = meerkat.baselines(len(names), select.get("autos", False))
    cp = meerkat.corrprod_index(ds.corr_products, names, a1, a2)
    vis, weights, raw_flags, flags, timestamps, u, v, w = [], [], [], [], [], [], [], []
    for _, state, _ in ds.scans():
        if state not in loader.states or ds.shape[0] < loader.min_scan_dumps:
            continue
        vis.append(ds.vis[:])
        weights.append(ds.weights[:])
        raw_flags.append(ds.raw_flags[:])
        flags.append(ds.flags[:])
        timestamps.append(ds.timestamps[:])
        u.append(ds.u[:])
        v.append(ds.v[:])
        w.append(ds.w[:])
    cat = np.concatenate
    print(f"(a)2 {label}")
    uvw = np.stack([cat(u), cat(v), cat(w)], axis=-1)  # (time, corrprod, 3)
    uvw_rows = uvw[:, cp[:, 0]].reshape(-1, 3)
    # The protocol expected katdal's u, v, w to carry the opposite sign; katdal
    # documents u1 − u2 for (ant1, ant2), the CASA sign mvftoms writes, so the
    # frozen 1e-6 m tolerance applies to the direct difference (deviation 1).
    delta = got["UVW"] - uvw_rows
    flipped = got["UVW"] + uvw_rows
    out = {
        "selection": loader.selection,
        "DATA": report("vis", got["DATA"], meerkat.to_rows(cat(vis), cp, 0)),
        "WEIGHT_SPECTRUM": report(
            "weights", got["WEIGHT_SPECTRUM"], meerkat.to_rows(cat(weights), cp, 0)
        ),
        "FLAG_BITS": report(
            "raw_flags", got["FLAG_BITS"], meerkat.to_rows(cat(raw_flags), cp, 0)
        ),
        "FLAG": report(
            "flags", got["FLAG"], meerkat.to_rows(cat(flags).view(np.uint8), cp, 0) != 0
        ),
        "TIME": report(
            "timestamps",
            got["TIME"],
            np.repeat(meerkat.mjd_seconds(cat(timestamps)), len(a1)),
        ),
        "UVW": {
            "max_abs_diff_m": float(np.max(np.abs(delta))),
            "max_abs_diff_after_sign_flip_m": float(np.max(np.abs(flipped))),
            "bitwise_equal": equal(got["UVW"], uvw_rows),
            "tolerance_m": 1e-6,
            "pass": bool(np.max(np.abs(delta)) <= 1e-6),
            "max_abs_uvw_m": float(np.max(np.abs(got["UVW"]))),
        },
        "antennas": {
            "names": names == [a.name for a in ds.ants],
            "positions": equal(
                np.array([a.position_ecef for a in ds.ants]),
                np.array(loader.metadata()["positions_ecef"]),
            ),
        },
        "channel_freqs": equal(
            np.asarray(loader.metadata()["channel_freqs"]), ds.channel_freqs
        ),
    }
    print(f"  UVW: {out['UVW']}")
    return out


# --- (b): the mvftoms MS --------------------------------------------------------


def run_mvftoms(rdb, ms, mvftoms):
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(mvftoms), "-f", "--quack", "0", "-o", str(ms), str(rdb)],
        check=False,
        capture_output=True,
        text=True,
    )
    seconds = time.perf_counter() - started
    (Path(ms).parent / "mvftoms.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"mvftoms failed: {proc.stderr[-2000:]}")
    return seconds


def check_ms(loader, ms):
    loader.select(autos=True)
    got = loader.read()
    with core_ms.open_table(ms) as table:
        cols = {
            name: table.getcol(name)
            for name in (
                "TIME",
                "ANTENNA1",
                "ANTENNA2",
                "DATA",
                "FLAG",
                "WEIGHT_SPECTRUM",
                "UVW",
                "FLAG_ROW",
                "WEIGHT",
                "SIGMA_SPECTRUM",
                "SCAN_NUMBER",
                "FIELD_ID",
            )
        }
        with table.subtable("ANTENNA") as ant:
            ant_names = list(ant.getcol("NAME"))
            ant_pos = ant.getcol("POSITION")
        with table.subtable("SPECTRAL_WINDOW") as spw:
            chan_freq = spw.getcol("CHAN_FREQ")
        with table.subtable("POLARIZATION") as pol:
            corr_type = pol.getcol("CORR_TYPE")
    keys = {
        (t, a, b): n
        for n, (t, a, b) in enumerate(
            zip(cols["TIME"], cols["ANTENNA1"], cols["ANTENNA2"])
        )
    }
    order = np.array(
        [
            keys.get((t, a, b), -1)
            for t, a, b in zip(got["TIME"], got["ANTENNA1"], got["ANTENNA2"])
        ]
    )
    print(
        f"(b) MS rows {len(cols['TIME'])}, loader rows {len(order)}, unmatched {np.sum(order < 0)}"
    )
    out = {
        "ms_rows": len(cols["TIME"]),
        "loader_rows": len(order),
        "unmatched_loader_rows": int(np.sum(order < 0)),
        "unmatched_ms_rows": int(len(cols["TIME"]) - len(set(order[order >= 0]))),
        "row_order_identical": bool(np.array_equal(order, np.arange(len(order)))),
    }
    if out["unmatched_loader_rows"]:
        return out
    for name in (
        "TIME",
        "ANTENNA1",
        "ANTENNA2",
        "DATA",
        "FLAG",
        "WEIGHT_SPECTRUM",
        "UVW",
    ):
        out[name] = report(name, got[name], cols[name][order])
    out["SCAN_NUMBER"] = report(
        "SCAN_NUMBER", got["SCAN_NUMBER"], cols["SCAN_NUMBER"][order]
    )
    out["FIELD_ID"] = report("FIELD_ID", got["FIELD_ID"], cols["FIELD_ID"][order])
    md = loader.metadata()
    out["ANTENNA.NAME"] = ant_names == md["antennas"]
    out["ANTENNA.POSITION"] = report(
        "ANTENNA.POSITION", ant_pos, np.asarray(md["positions_ecef"])
    )
    out["CHAN_FREQ"] = report(
        "CHAN_FREQ", chan_freq[0], np.asarray(md["channel_freqs"])
    )
    out["CORR_TYPE"] = report(
        "CORR_TYPE", corr_type[0], np.asarray(meerkat.CORR_TYPES, corr_type.dtype)
    )
    ws = cols["WEIGHT_SPECTRUM"]
    with np.errstate(divide="ignore"):
        out["recorded"] = {
            "FLAG_ROW_all_false": bool(not np.any(cols["FLAG_ROW"])),
            "WEIGHT_is_channel_mean": bool(
                np.allclose(cols["WEIGHT"], ws.mean(axis=1), rtol=1e-6)
            ),
            "SIGMA_SPECTRUM_is_w_pow_minus_half": bool(
                np.allclose(cols["SIGMA_SPECTRUM"], ws**-0.5, rtol=1e-6)
            ),
            "scans_written": sorted(int(s) for s in set(cols["SCAN_NUMBER"])),
        }
    print(f"  recorded {out['recorded']}")
    return out


# --- (d): the bitfield ----------------------------------------------------------


def check_bits(fixture, raw):
    out = {}
    for upgrade in (False, True):
        loader = meerkat.open_mvf(fixture["rdb"], upgrade_flags=upgrade)
        label = "upgrade_flags" if upgrade else "L0"
        res = check_raw(loader, raw, f"(d) {label}", bits="l1" if upgrade else "l0")
        per_bit = {}
        for bit, name in enumerate(meerkat.FLAG_NAMES):
            loader.select(flags=[name])
            got = loader.read()
            per_bit[name] = equal(
                got["FLAG"], ((got["FLAG_BITS"] >> bit) & 1).astype(bool)
            )
        loader.select(flags=list(meerkat.NATIVE_FLAGS))
        native = loader.read()
        out[label] = {
            "FLAG_BITS": res["FLAG_BITS"],
            "per_bit_select": per_bit,
            "native_flag_fraction": float(native["FLAG"].mean()),
            "bit_occupancy": {
                name: float(((native["FLAG_BITS"] >> b) & 1).mean())
                for b, name in enumerate(meerkat.FLAG_NAMES)
            },
        }
        print(f"(d) {label}: per-bit select {per_bit}")
    return out


# --- HTTP ---------------------------------------------------------------------------


@contextlib.contextmanager
def http_server(directory):
    """Serve `directory` on 127.0.0.1 as a minimal S3 bucket would: files by
    GET, and a bucket listing with `<Contents>` for a non-empty directory
    (katdal's S3ChunkStore lists the bucket after a missing chunk's 404 to
    tell a lost chunk from an inaccessible store). Counts requests and bytes."""
    import http.server
    import threading

    root = Path(directory)
    counters = {"requests": 0, "bytes": 0, "not_found": 0}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *args):
            pass

        def do_GET(self):
            counters["requests"] += 1
            path = root / self.path.split("?")[0].lstrip("/")
            if path.is_dir():
                keys = [p for p in path.rglob("*") if p.is_file()][:1]
                body = (
                    "<ListBucketResult>"
                    + "".join(
                        f"<Contents><Key>{k.relative_to(path)}</Key></Contents>"
                        for k in keys
                    )
                    + "</ListBucketResult>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if not path.is_file():
                counters["not_found"] += 1
            else:
                counters["bytes"] += path.stat().st_size
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", counters
    finally:
        server.shutdown()
        server.server_close()


# --- cost ------------------------------------------------------------------------------


def cost(loader, root, prefix, every_dump=False):
    """Wall, katdal read time and bytes per loader chunk; with every_dump,
    slews and one-dump scans are read too (the cost set has no long tracks)."""
    if every_dump:
        loader.select(states=("slew", "track", "scan", "stop"), min_scan_dumps=1)
    else:
        loader.select()
    stats = []
    started = time.perf_counter()
    for chunk in loader.iter_chunks():
        stats.append(chunk["_stats"])
    wall = time.perf_counter() - started
    # The same dumps read straight from the .npy files (no dask, no katdal).
    files = sorted((Path(root) / prefix).rglob("*.npy"))
    disk_bytes = sum(p.stat().st_size for p in files)
    t0 = time.perf_counter()
    for p in files:
        np.load(p)
    npy_seconds = time.perf_counter() - t0
    return {
        "chunks": len(stats),
        "rows": sum(s["rows"] for s in stats),
        "wall_seconds": wall,
        "katdal_read_seconds": sum(s["read_seconds"] for s in stats),
        "loader_total_seconds": sum(s["total_seconds"] for s in stats),
        "per_chunk_seconds_median": float(
            np.median([s["total_seconds"] for s in stats])
        ),
        "store_files": len(files),
        "store_bytes": disk_bytes,
        "npy_load_all_seconds": npy_seconds,
        "peak_rss_bytes": rusage.peak_rss_bytes(),
        "vm_hwm_bytes": _vm_hwm(),
    }


def _vm_hwm():
    """This process's peak resident set from /proc (Linux), else None."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--large",
        type=Path,
        default=None,
        help="scratch directory for the L-band-scale cost set (deleted after)",
    )
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--cost", nargs=3, metavar=("RDB", "ROOT", "PREFIX"))
    args = parser.parse_args()
    if args.cost:
        rdb, root, prefix = args.cost
        print(json.dumps(cost(meerkat.open_mvf(rdb), root, prefix, every_dump=True)))
        return 0
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; use a fresh output directory")
    args.out.mkdir(parents=True)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    t_all = time.perf_counter()
    import katdal
    import katpoint
    import katsdptelstate

    fixture = meerkat.write_synthetic_mvf(args.out / "archive")
    raw = raw_store_arrays(fixture["root"], fixture["rdb"])
    result = {
        "task": "MK1",
        "protocol": "research/mk1-katdal.md",
        "started_utc": started_utc,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "katdal": katdal.__version__,
            "katsdptelstate": katsdptelstate.__version__,
            "katpoint": katpoint.__version__,
            "platform": platform.platform(),
        },
        "fixture": {
            **fixture["params"],
            "dropped": fixture["dropped"],
            "zero_auto": fixture["zero_auto"],
            "n_bls": len(fixture["bls_ordering"]),
        },
    }
    loader = meerkat.open_mvf(fixture["rdb"])
    track = _track_dumps(loader)
    result["fixture"]["exercised"] = {
        "track_dumps": track.tolist(),
        # 2**-32 times a stored weight of at most 255 x 2: below 1e-6.
        "bad_weight_cells_in_tracks": int(np.sum(raw["weights"][track] < 1e-6)),
        "lost_cells_in_tracks": int(np.sum(raw["lost"][track])),
        "l0_l1_differing_cells_in_tracks": int(
            np.sum(raw["flags_l0"][track] != raw["flags_l1"][track])
        ),
        "bls_ordering_lexicographic": fixture["bls_ordering"]
        == sorted(fixture["bls_ordering"]),
    }
    print(f"fixture exercised: {result['fixture']['exercised']}")
    result["metadata"] = {
        k: v for k, v in loader.metadata().items() if k != "channel_freqs"
    }
    a = {"local": {}, "http": {}}
    restricted = {
        "scans": [3],
        "antennas": ["m001", "m003", "m004", "m006"],
        "channels": slice(10, 50),
    }
    a["local"]["raw_default"] = check_raw(loader, raw, "local default")
    a["local"]["raw_restricted"] = check_raw(
        loader, raw, "local restricted", **restricted
    )
    a["local"]["katdal_default"] = check_katdal(loader, "local default")
    a["local"]["katdal_restricted"] = check_katdal(
        loader, "local restricted", **restricted
    )
    with http_server(fixture["root"]) as (base, counters):
        url = (
            f"{base}/{fixture['params']['cbid']}/{fixture['params']['cbid']}_sdp_l0.rdb"
        )
        remote = meerkat.open_mvf(url)
        a["http"]["url"] = url
        a["http"]["raw_default"] = check_raw(remote, raw, "http default")
        a["http"]["katdal_restricted"] = check_katdal(
            remote, "http restricted", **restricted
        )
        a["http"]["server"] = dict(counters)
    result["a"] = a
    mvftoms = Path(sys.executable).parent / "mvftoms.py"
    ms = args.out / "fixture.ms"
    result["b"] = {
        "mvftoms_seconds": run_mvftoms(fixture["rdb"], ms, mvftoms),
        "arguments": ["-f", "--quack", "0"],
    }
    result["b"].update(check_ms(meerkat.open_mvf(fixture["rdb"]), ms))
    result["c"] = {
        "run": False,
        "reason": "no public MVFv4 archive reachable (token-gated "
        "SARAO archive; no MVF in the RATT bucket); see research/mk1-katdal.md",
    }
    result["d"] = check_bits(fixture, raw)
    result["cost"] = {
        "fixture": cost(
            meerkat.open_mvf(fixture["rdb"]), fixture["root"], fixture["l0_prefix"]
        )
    }
    if args.large is not None:
        if args.large.exists():
            raise SystemExit(f"{args.large} exists")
        t0 = time.perf_counter()
        # The loader then runs in a child process (peak from VmHWM, which execve
        # resets; ru_maxrss carries the forked parent's RSS across execve).
        big = meerkat.write_synthetic_mvf(
            args.large,
            n_ants=64,
            n_dumps=4,
            n_chans=4096,
            dump_chunk=1,
            chan_chunk=256,
            drop_chunk=False,
            l1_flags=False,
            cbid="1700000001",
        )
        write_seconds = time.perf_counter() - t0
        del big["arrays"]
        child = subprocess.run(
            [
                sys.executable,
                __file__,
                "--cost",
                big["rdb"],
                big["root"],
                big["l0_prefix"],
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result["cost"]["large"] = {
            "params": big["params"],
            "write_seconds": write_seconds,
            "note": "every dump read (slews included); loader in a child process",
            **json.loads(child.stdout.strip().splitlines()[-1]),
        }
        shutil.rmtree(args.large)
    result["seconds"] = time.perf_counter() - t_all
    checks = []
    for side in a.values():
        for part in side.values():
            if isinstance(part, dict):
                checks += [
                    v["equal"]
                    for v in part.values()
                    if isinstance(v, dict) and "equal" in v
                ]
                if "UVW" in part:
                    checks.append(part["UVW"]["pass"])
                    checks += [
                        part["antennas"]["names"],
                        part["antennas"]["positions"],
                        part["channel_freqs"],
                    ]
    result["pass_a"] = all(checks)
    b = result["b"]
    result["pass_b"] = (
        b["unmatched_loader_rows"] == 0
        and b["unmatched_ms_rows"] == 0
        and all(
            b[k]["equal"]
            for k in (
                "TIME",
                "ANTENNA1",
                "ANTENNA2",
                "DATA",
                "FLAG",
                "WEIGHT_SPECTRUM",
                "UVW",
                "CHAN_FREQ",
                "CORR_TYPE",
                "ANTENNA.POSITION",
            )
        )
        and b["ANTENNA.NAME"]
    )
    result["pass_d"] = all(
        v["FLAG_BITS"]["equal"] and all(v["per_bit_select"].values())
        for v in result["d"].values()
    )
    result["pass"] = result["pass_a"] and result["pass_b"] and result["pass_d"]
    print(f"pass (a) {result['pass_a']} (b) {result['pass_b']} (d) {result['pass_d']}")
    text = json.dumps(result, indent=1, default=str) + "\n"
    (args.out / "result.json").write_text(text)
    if args.archive:
        (ROOT / "research" / "results" / "mk1-katdal.json").write_text(text)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    sys.exit(main())
