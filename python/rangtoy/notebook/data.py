"""Load the two small teaching datasets into the state the core wrappers take.

Two datasets, both real MeerKAT L-band data on four stations:

- the public SKA pointing fixture, scan 9 of `outer_scans.zip` (140 rows,
  4 antennas, 4096 channels; research/measurement-set-inspection.md), read
  through the core's Measurement Set reader (`core_ms`) with the frozen
  `flagging_workflow.prepare` conventions: Reynolds (1994) point model, the
  1024:3072 channel window, seed 7, the (2, 32) gain-grid reservation;
- the four-station LUNO PKS 1934-638 slice (row chunk 0, channel tiles 8-23),
  range-fetched with `core_fetch` and decoded by the core exactly as task K
  did (research/core-k-luno-campaign.md), or read from a local copy.

Every heavy step is a core wrapper call. Paths are always arguments; the
repository's ignored `outputs/` tree is only a fallback search location, and
downloads go to a cache directory the caller names, never into the package.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np

from .. import core_fetch, core_ms
from ..core_policy import protected_flags, split_holdout

FIXTURE_SHA256 = "d4dae56f7ad1bb4a49ab8c4a3846871d5b8ebb4b731ee958cb9f1baf3306144f"
FIXTURE_BYTES = 45_452_147
FIXTURE_URL = (
    "https://gitlab.com/ska-telescope/sdp/science-pipeline-workflows/"
    "ska-sdp-wflow-pointing-offset/-/raw/main/tests/data/outer_scans.zip"
)
FIXTURE_SCAN = "outer_scans/1672727931_sdp_l0_scan_9.ms"
FIXTURE_WINDOW = (1024, 3072)
SPLIT_SEED = 7
SPLIT_GRID = (2, 32)

LUNO_BUCKET = (
    "https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr"
)
LUNO_GROUP = "MAIN/MAIN_1"
LUNO_STATIONS = (0, 1, 2, 3)
LUNO_TILES = tuple(range(8, 24))
LUNO_CHANNELS = (1024, 3072)
# Bytes of task G's range fetch of the slice (core-g-20261029-01/result.json).
LUNO_EXPECTED_BYTES = 751_848_436
# The small objects `core_campaign.decode_extra` reads beyond the slice.
LUNO_EXTRA = (
    ("MAIN/MAIN_1/UVW", "0.0"),
    ("ANTENNA/ANTENNA_0/POSITION", "0.0"),
    ("ANTENNA/ANTENNA_0/NAME", "0"),
    ("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0"),
    ("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0"),
    ("FIELD/FIELD_0/PHASE_DIR", "0.0.0"),
    ("FIELD/FIELD_0/NAME", "0"),
    ("POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0"),
)
CORRELATIONS = ("XX", "XY", "YX", "YY")


@dataclass
class Dataset:
    """One loaded dataset.

    `state` is the dictionary `core_workflow.core_solve` and
    `core_campaign.tv_loop` take (data, model, weights, original flags and
    rows, times, frequencies, antenna1/2, names, eligible, train, validation,
    test, window). `extra` holds the geometry and metadata the flagger and
    imager need (uvw, antenna_position, chan_width, corr_type, phase_dir,
    field_name). `source` records where the bytes came from.
    """

    name: str
    state: dict
    extra: dict
    source: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.state["data"].shape

    @property
    def names(self):
        return [str(n) for n in self.state["names"]]

    def baselines(self, cross_only=True):
        """Sorted (p, q) pairs present in the rows."""
        p, q = self.state["antenna1"], self.state["antenna2"]
        pairs = sorted({(int(a), int(b)) for a, b in zip(p, q)})
        return [pq for pq in pairs if pq[0] != pq[1]] if cross_only else pairs

    def baseline_label(self, pair):
        return f"{self.names[pair[0]]}-{self.names[pair[1]]}"


# --- discovery ---------------------------------------------------------------


def _search_roots():
    """The checkout this package lives in, then the working directory and its
    parents (notebooks run from `notebooks/`)."""
    roots = []
    here = Path(__file__).resolve()
    if len(here.parents) > 3 and (here.parents[3] / "pyproject.toml").is_file():
        roots.append(here.parents[3])
    cwd = Path.cwd().resolve()
    roots.extend([cwd, *cwd.parents])
    seen, unique = set(), []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def find_fixture():
    """The fixture archive or extracted scan-9 MS, or None.

    Order: `RANG_FIXTURE` (a zip or an `.ms` directory), then
    `outputs/ska-pointing/outer_scans.zip` under the checkout or the working
    directory's parents.
    """
    configured = os.environ.get("RANG_FIXTURE")
    if configured:
        path = Path(configured)
        return path if path.exists() else None
    for root in _search_roots():
        candidate = root / "outputs" / "ska-pointing" / "outer_scans.zip"
        if candidate.is_file():
            return candidate
    return None


def find_luno_slice():
    """(slice_dir, extra_dir) of a local LUNO copy, or None.

    `slice_dir` is a `core_fetch.fetch_slice` output (result.json, objects,
    spans); `extra_dir` holds the extra objects at their store keys. Order:
    `RANG_LUNO_SLICE` and `RANG_LUNO_EXTRA`, then task G's fetch
    (`outputs/core-g-20261029-01`) with the solve inputs
    (`outputs/luno-solve-20261029-02/inputs`) under the checkout.
    """
    slice_env, extra_env = (
        os.environ.get("RANG_LUNO_SLICE"),
        os.environ.get("RANG_LUNO_EXTRA"),
    )
    if slice_env and extra_env:
        pair = Path(slice_env), Path(extra_env)
        return pair if _luno_complete(*pair) else None
    for root in _search_roots():
        pair = (
            root / "outputs" / "core-g-20261029-01",
            root / "outputs" / "luno-solve-20261029-02" / "inputs",
        )
        if _luno_complete(*pair):
            return pair
    return None


def _luno_complete(slice_dir, extra_dir):
    return (Path(slice_dir) / "result.json").is_file() and all(
        (Path(extra_dir) / key / chunk).is_file() for key, chunk in LUNO_EXTRA
    )


def default_cache_dir():
    """`RANG_NOTEBOOK_CACHE`, else `~/.cache/rang-notebook` (pathlib, any OS)."""
    configured = os.environ.get("RANG_NOTEBOOK_CACHE")
    return Path(configured) if configured else Path.home() / ".cache" / "rang-notebook"


# --- the fixture -------------------------------------------------------------


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download_fixture(cache_dir, progress=None):
    """Download `outer_scans.zip` (45 MB, public Git LFS object) into
    `cache_dir` and verify its SHA256. Returns the zip path. Nothing is
    downloaded when a verified copy is already there."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "outer_scans.zip"
    if target.is_file() and _sha256(target) == FIXTURE_SHA256:
        return target
    partial = cache_dir / "outer_scans.zip.partial"
    with (
        urllib.request.urlopen(FIXTURE_URL, timeout=120) as response,
        partial.open("wb") as stream,
    ):
        done = 0
        for block in iter(lambda: response.read(1 << 20), b""):
            stream.write(block)
            done += len(block)
            if progress is not None:
                progress(done, FIXTURE_BYTES)
    if _sha256(partial) != FIXTURE_SHA256:
        partial.unlink()
        raise ValueError("downloaded fixture does not match the pinned SHA256")
    partial.replace(target)
    return target


def _safe_members(zipped, prefix):
    members = []
    for info in zipped.infolist():
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
            raise ValueError(f"unsafe archive member {info.filename!r}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError(f"symbolic link in archive: {info.filename!r}")
        if info.filename.startswith(prefix):
            members.append(info)
    if not members:
        raise ValueError(f"{prefix} not found in the archive")
    return members


def extract_fixture(archive, cache_dir):
    """Checksum-pinned extraction of scan 9 only; returns the `.ms` path.

    The extraction is reused when `cache_dir/fixture-scan9` is complete.
    """
    cache_dir = Path(cache_dir)
    done = cache_dir / "fixture-scan9"
    ms = done / FIXTURE_SCAN
    if (done / "COMPLETE").is_file() and ms.is_dir():
        return ms
    if _sha256(archive) != FIXTURE_SHA256:
        raise ValueError(f"{archive} is not the pinned public fixture")
    partial = cache_dir / "fixture-scan9.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    with zipfile.ZipFile(archive) as zipped:
        for info in _safe_members(zipped, FIXTURE_SCAN + "/"):
            zipped.extract(info, partial)
    (partial / "COMPLETE").write_text(FIXTURE_SHA256 + "\n")
    if done.exists():
        shutil.rmtree(done)
    partial.replace(done)
    return ms


def reynolds_flux(frequencies_hz):
    """PKS 1934-638 Stokes I in Jy, Reynolds (1994), as `prepare` uses it."""
    log_nu = np.log10(np.asarray(frequencies_hz) / 1e6)
    return 10 ** (
        -30.7667 + 26.4908 * log_nu - 7.0977 * log_nu**2 + 0.605334 * log_nu**3
    )


def read_ms(ms):
    """The columns the teaching state needs, read through `core_ms`."""
    ms = Path(ms)
    with core_ms.open_table(ms) as table:
        names = table.colnames()
        columns = {
            c: table.getcol(c)
            for c in (
                "DATA",
                "FLAG",
                "FLAG_ROW",
                "TIME",
                "ANTENNA1",
                "ANTENNA2",
                "UVW",
                "SCAN_NUMBER",
                "FIELD_ID",
                "DATA_DESC_ID",
            )
        }
        if "WEIGHT_SPECTRUM" in names:
            columns["WEIGHT_SPECTRUM"] = table.getcol("WEIGHT_SPECTRUM")
        else:
            columns["WEIGHT_SPECTRUM"] = np.broadcast_to(
                table.getcol("WEIGHT")[:, None], columns["DATA"].shape
            ).copy()
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as spw:
        if spw.nrows != 1:
            raise ValueError("one spectral window required")
        columns["CHAN_FREQ"] = spw.getcol("CHAN_FREQ")[0]
        columns["CHAN_WIDTH"] = spw.getcol("CHAN_WIDTH")[0]
    with core_ms.open_table(ms / "ANTENNA") as antenna:
        columns["ANTENNA_NAME"] = [str(n) for n in antenna.getcol("NAME")]
        columns["ANTENNA_POSITION"] = antenna.getcol("POSITION")
    with core_ms.open_table(ms / "POLARIZATION") as pol:
        columns["CORR_TYPE"] = pol.getcol("CORR_TYPE")[0]
    with core_ms.open_table(ms / "FIELD") as fld:
        columns["PHASE_DIR"] = fld.getcol("PHASE_DIR")[0, 0]
        columns["FIELD_NAME"] = str(fld.getcol("NAME")[0])
    return columns


def fixture_state(columns, seed=SPLIT_SEED, window=FIXTURE_WINDOW, grid=SPLIT_GRID):
    """`flagging_workflow.prepare`'s state for the fixture, without casacore.

    Same model, window, eligibility, groups and seed as the frozen prepare,
    so the split counts can be checked against the archived run (73,720
    train, 9,115 validation, 9,169 test; results/gain-tv-flagging.json).
    """
    data = np.ascontiguousarray(columns["DATA"], np.complex64)
    flags = np.ascontiguousarray(columns["FLAG"], bool)
    rows = np.ascontiguousarray(columns["FLAG_ROW"], bool)
    weights = np.ascontiguousarray(columns["WEIGHT_SPECTRUM"], np.float32)
    times = np.ascontiguousarray(columns["TIME"], np.float64)
    p = np.ascontiguousarray(columns["ANTENNA1"], np.int32)
    q = np.ascontiguousarray(columns["ANTENNA2"], np.int32)
    frequencies = np.ascontiguousarray(columns["CHAN_FREQ"], np.float64)
    for key in ("SCAN_NUMBER", "FIELD_ID", "DATA_DESC_ID"):
        if len(np.unique(columns[key])) != 1:
            raise ValueError("one scan, field and data descriptor required")
    if tuple(int(c) for c in columns["CORR_TYPE"]) != (9, 10, 11, 12):
        raise ValueError("linear XX XY YX YY correlations required")
    flux = reynolds_flux(frequencies)
    model = np.zeros_like(data)
    model[..., 0] = model[..., 3] = flux[None, :]
    protected, _ = protected_flags(flags, rows, np.zeros_like(flags))
    in_window = np.zeros(len(frequencies), bool)
    in_window[window[0] : window[1]] = True
    eligible = (~protected.any(axis=-1)) & (p != q)[:, None] & in_window[None]
    eligible &= (
        np.isfinite(data).all(axis=-1)
        & np.isfinite(weights).all(axis=-1)
        & (weights > 0).all(axis=-1)
    )
    names = list(columns["ANTENNA_NAME"])
    time_bins = np.unique(times, return_inverse=True)[1] // grid[0]
    freq_bins = np.arange(len(frequencies)) // grid[1]
    groups = (time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]) * len(
        names
    ) ** 2 + (p * len(names) + q)[:, None]
    train, validation, test = split_holdout(eligible, seed, groups=groups)
    return {
        "original_flags": flags,
        "original_rows": rows,
        "data": data,
        "model": model,
        "weights": weights,
        "times": times,
        "frequencies": frequencies,
        "antenna1": p,
        "antenna2": q,
        "names": names,
        "eligible": eligible,
        "train": train,
        "validation": validation,
        "test": test,
        "window": in_window,
    }


def load_fixture(source=None, cache_dir=None, seed=SPLIT_SEED):
    """Scan 9 of the public fixture as a `Dataset`.

    `source` is the zip, an extracted scan-9 `.ms` directory, or None to use
    `find_fixture()`. A zip is extracted (scan 9 only) under `cache_dir`
    (default `default_cache_dir()`). Raises FileNotFoundError when no copy is
    found; `download_fixture(cache_dir)` fetches the public archive.
    """
    source = Path(source) if source is not None else find_fixture()
    if source is None or not source.exists():
        raise FileNotFoundError(
            "fixture not found: pass the path of outer_scans.zip, set RANG_FIXTURE, "
            "or call download_fixture(cache_dir)"
        )
    started = time.perf_counter()
    if source.is_dir():
        ms = source
    else:
        ms = extract_fixture(source, Path(cache_dir or default_cache_dir()))
    columns = read_ms(ms)
    state = fixture_state(columns, seed=seed)
    extra = {
        "uvw": np.ascontiguousarray(columns["UVW"], np.float64),
        "antenna_position": np.ascontiguousarray(
            columns["ANTENNA_POSITION"], np.float64
        ),
        "antenna_names": state["names"],
        "chan_freq": state["frequencies"],
        "chan_width": np.ascontiguousarray(columns["CHAN_WIDTH"], np.float64),
        "phase_dir": np.asarray(columns["PHASE_DIR"], np.float64),
        "field_name": columns["FIELD_NAME"],
        "corr_type": np.ascontiguousarray(columns["CORR_TYPE"], np.int32),
    }
    return Dataset(
        name="fixture scan 9 (J1939-6342)",
        state=state,
        extra=extra,
        source={
            "kind": "fixture",
            "path": str(source),
            "ms": str(ms),
            "archive_sha256": FIXTURE_SHA256,
            "model": "unpolarized phase-centre Reynolds (1994) point approximation",
            "seed": seed,
            "window": list(FIXTURE_WINDOW),
            "seconds": time.perf_counter() - started,
        },
    )


# --- the LUNO slice ----------------------------------------------------------


def _bytes_under(path):
    path = Path(path)
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def print_progress(done, expected, seconds):
    """Default fetch progress: one line, overwritten in place."""
    share = done / expected if expected else 0.0
    print(
        f"\rfetched {done / 1e6:7.1f} of ~{expected / 1e6:.0f} MB "
        f"({share:5.1%}) in {seconds:5.1f} s",
        end="",
        flush=True,
    )


def fetch_luno(cache_dir, progress=print_progress, workers=8, interval=1.0):
    """Range-fetch the four-station slice and its extra objects into
    `cache_dir/luno-1934-chunk0`; returns that directory. Reused when complete.

    `core_fetch.fetch_slice` has no progress hook, so a thread polls the
    bytes on disk and calls `progress(done, expected, seconds)`. About
    752 MB; 75 s on the development host.
    """
    cache_dir = Path(cache_dir)
    done_dir = cache_dir / "luno-1934-chunk0"
    if (done_dir / "COMPLETE").is_file():
        return done_dir
    partial = cache_dir / "luno-1934-chunk0.partial"
    if partial.exists():
        shutil.rmtree(partial)
    cache_dir.mkdir(parents=True, exist_ok=True)
    from ..core_campaign import fetch_extra

    stop = threading.Event()
    started = time.perf_counter()

    def poll():
        while not stop.wait(interval):
            if partial.exists() and progress is not None:
                progress(
                    _bytes_under(partial),
                    LUNO_EXPECTED_BYTES,
                    time.perf_counter() - started,
                )

    watcher = threading.Thread(target=poll, daemon=True)
    watcher.start()
    try:
        core_fetch.fetch_slice(
            LUNO_BUCKET,
            LUNO_GROUP,
            LUNO_STATIONS,
            LUNO_TILES,
            partial,
            workers=workers,
        )
        fetch_extra(LUNO_BUCKET, partial)
    finally:
        stop.set()
        watcher.join()
    if progress is not None:
        progress(
            _bytes_under(partial), LUNO_EXPECTED_BYTES, time.perf_counter() - started
        )
        print()
    (partial / "COMPLETE").write_text("fetched\n")
    if done_dir.exists():
        shutil.rmtree(done_dir)
    partial.replace(done_dir)
    return done_dir


def _luno_extra(objects_root, rows):
    """`core_campaign.decode_extra` for an objects root at store keys."""
    from ..core_campaign import decode_object

    lo, hi = LUNO_CHANNELS
    uvw = decode_object(objects_root, "MAIN/MAIN_1/UVW", "0.0")
    names = decode_object(objects_root, "ANTENNA/ANTENNA_0/NAME", "0")
    field_names = decode_object(objects_root, "FIELD/FIELD_0/NAME", "0")
    phase = decode_object(objects_root, "FIELD/FIELD_0/PHASE_DIR", "0.0.0")
    attrs_path = Path(objects_root) / LUNO_GROUP / ".zattrs"
    field_id = 0
    if attrs_path.is_file():
        field_id = int(json.loads(attrs_path.read_text())["FIELD_ID"])
    return {
        "field_id": field_id,
        "uvw": np.ascontiguousarray(uvw[np.asarray(rows)], np.float64),
        "antenna_position": np.ascontiguousarray(
            decode_object(objects_root, "ANTENNA/ANTENNA_0/POSITION", "0.0"),
            np.float64,
        ),
        "antenna_names": [str(n) for n in names],
        "chan_freq": np.ascontiguousarray(
            decode_object(
                objects_root, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0"
            )[0, lo:hi],
            np.float64,
        ),
        "chan_width": np.ascontiguousarray(
            decode_object(
                objects_root, "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0"
            )[0, lo:hi],
            np.float64,
        ),
        "phase_dir": np.asarray(phase[field_id, 0], np.float64),
        "field_name": str(field_names[field_id]),
        "corr_type": np.ascontiguousarray(
            decode_object(objects_root, "POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")[
                0
            ],
            np.int32,
        ),
    }


def load_luno(slice_dir=None, extra_dir=None, cache_dir=None, fetch=False, **kwargs):
    """The four-station LUNO PKS 1934-638 slice as a `Dataset`.

    With `slice_dir` and `extra_dir` (or a local copy found by
    `find_luno_slice()`), nothing is fetched. With `fetch=True`, the slice is
    range-fetched into `cache_dir` (see `fetch_luno`; extra keyword arguments
    go there). The state is `core_campaign.build_state`, task K's frozen
    split (seed 7, (2, 32) grid).
    """
    from ..core_campaign import build_state

    started = time.perf_counter()
    if slice_dir is None and not fetch:
        found = find_luno_slice()
        if found is None:
            raise FileNotFoundError(
                "no local LUNO slice: pass slice_dir and extra_dir, set "
                "RANG_LUNO_SLICE and RANG_LUNO_EXTRA, or use fetch=True with a cache_dir"
            )
        slice_dir, extra_dir = found
    if fetch:
        fetched = fetch_luno(Path(cache_dir or default_cache_dir()), **kwargs)
        slice_dir, extra_dir = fetched, fetched / "objects"
    if extra_dir is None:
        extra_dir = Path(slice_dir) / "objects"
    arrays, decode_stats = core_fetch.decode_slice(slice_dir)
    rows = json.loads((Path(slice_dir) / "result.json").read_text())["rows"]
    extra = _luno_extra(extra_dir, rows)
    state = build_state(arrays, extra)
    return Dataset(
        name="LUNO PKS 1934-638, four stations",
        state=state,
        extra=extra,
        source={
            "kind": "luno",
            "slice_dir": str(slice_dir),
            "extra_dir": str(extra_dir),
            "bucket": LUNO_BUCKET,
            "group": LUNO_GROUP,
            "stations": list(LUNO_STATIONS),
            "channels": list(LUNO_CHANNELS),
            "decode": decode_stats,
            "seconds": time.perf_counter() - started,
            "model": "MODEL_DATA as stored (origin unlogged; "
            "research/flagging-luno-support.md)",
        },
    )


# --- tables ------------------------------------------------------------------


def summary(ds):
    """A one-row-per-quantity overview a student should read first."""
    s = ds.state
    nrow, nchan, ncorr = s["data"].shape
    f = s["frequencies"]
    cross = s["antenna1"] != s["antenna2"]
    return {
        "dataset": ds.name,
        "rows": nrow,
        "channels": nchan,
        "correlations": ncorr,
        "antennas": ", ".join(ds.names),
        "baselines (cross)": len(ds.baselines()),
        "integrations": len(np.unique(s["times"])),
        "frequency range (MHz)": f"{f[0] / 1e6:.1f} - {f[-1] / 1e6:.1f}",
        "flagged cells (any correlation)": float(s["original_flags"].any(-1).mean()),
        "flagged rows": int(s["original_rows"].sum()),
        "cross-correlation rows": int(cross.sum()),
        "eligible cells": int(s["eligible"].sum()),
        "train cells": int(s["train"].sum()),
        "validation cells": int(s["validation"].sum()),
        "test cells": int(s["test"].sum()),
        "field": ds.extra.get("field_name"),
    }


def temporary_cache():
    """A throwaway cache directory (for tests and one-off runs)."""
    return Path(tempfile.mkdtemp(prefix="rang-notebook-"))
