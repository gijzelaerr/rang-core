"""The whole-array LUNO 1934-638 campaign on the core (research/luno-array-campaign.md).

Task L1 of research/big-plan.md: task K's frozen campaign
(`rangtoy.core_campaign`) on all stations of LUNO row chunk 0. Changes from
K only where the array's scale forces them, each bit-identical to K's code on
K's four-station slice (the precondition's replay checks this):

- inputs are the archived whole tiles on disk, hash-checked against their
  receipts, decoded straight into preallocated arrays; nothing is fetched;
- solves never keep complex128 residuals: the two base solves compute the
  whitened residual amplitude in row blocks, everything else keeps gains,
  TV and metrics only;
- the per-baseline robust scores of `flagging.residual_features` are
  computed on each baseline's rows instead of the whole array;
- gain application and the Stokes I reader run in row blocks;
- the dirty image is gridded in channel groups whose unnormalised images
  are summed, and the image geometry and boxes come from the array's
  resolution and the measured PSF.

Big plan task P5 (research/p5-memory.md) keeps one copy of the cube and no
per-cell temporaries, each change bit-identical except the gain correction
(complex64 rounding):

- tiles decode straight into the final arrays (`core_fetch.read_rows_into`);
- eligibility and the seed-7 split run in row blocks (`split_holdout_lean`);
- solve flags are built in row blocks into one cube;
- the base solves' outlier scores come from the fused pass (`scores=True`)
  over groups of whole baselines and are kept sparse (only training cells
  with `outliers >= 2` can be proposed), with the guidance median; the
  policy masks are evaluated on that set (`sparse_policy_mask`);
- additions are stored as sorted cell indices;
- gain correction and the Stokes I reader run in Rust into reused buffers
  (`correct_stokes_i`), with the final-flag rule folded in.

Original FLAG and FLAG_ROW are never modified.
"""

import ctypes
import itertools
import json
import math
import platform
import resource
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import (
    core,
    core_campaign,
    core_fetch,
    core_flag,
    core_grid,
    core_weights,
    core_zarr,
)
from .core_campaign import (
    array_sha256,
    call,
    file_sha256,
    git_status,
    hypothesis,
    receipt_lines,
    rss_mb,
    snapshot,
    tricolour_checks,
    write_json,
)
from .core_workflow import gain_grid
from .flagging import (
    assert_preserved,
    fixed_support_tv,
    gain_tv,
    polar_gauge,
    protected_flags,
)

ROOT = core_campaign.ROOT
GROUP = core_campaign.GROUP
TILES = core_campaign.TILES
CHANNELS = core_campaign.CHANNELS
CHUNK_ROWS = 50_000
SUPPORT = core_campaign.SUPPORT
SOLVE_INPUTS = core_campaign.SOLVE_INPUTS
ROOTS = (SUPPORT, SOLVE_INPUTS)
K_RUN = ROOT / "outputs/core-k-20261030-01"
K_ARCHIVE = ROOT / "research/results/core-k-luno-campaign.json"
ARRAY_IMAGE = {
    "width": 1024,
    "height": 1024,
    "scale_arcsec": 1.5,
    "w_layers": 64,
    "kernel_size": 7,
    "oversampling": 1023,
    "padding": 1.2,
}
ARRAY_CHANNEL_GROUPS = 4
ROW_BLOCK = 2048
# Rows per baseline group of the feature pass (whole baselines per group).
FEATURE_ROWS = 2048
# "fused": scores from the fused pass; "numpy": L1's row-block amplitude
# and per-baseline estimator (the pre-registered fallback of P5).
SCORES = "fused"
GROUP_TOLERANCE = 1e-4
MEMORY_BUDGET_MB = 20_000
MIN_AVAILABLE_GIB = 20
ARCHIVED_INPUTS = (
    "outputs/luno-support-20261029-01",
    "outputs/luno-solve-20261029-02",
    "outputs/core-k-20261030-01",
    "outputs/core-section6-20261029-02",
    "outputs/caracal-strategy-inputs-8f7bb363",
)
EXTRA_KEYS = (
    "MAIN/MAIN_1/.zattrs",
    "MAIN/MAIN_1/UVW/.zarray",
    "MAIN/MAIN_1/UVW/0.0",
    "ANTENNA/ANTENNA_0/POSITION/.zarray",
    "ANTENNA/ANTENNA_0/POSITION/0.0",
    "ANTENNA/ANTENNA_0/NAME/.zarray",
    "ANTENNA/ANTENNA_0/NAME/0",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/.zarray",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ/0.0",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH/.zarray",
    "SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH/0.0",
    "FIELD/FIELD_0/PHASE_DIR/.zarray",
    "FIELD/FIELD_0/PHASE_DIR/0.0.0",
    "FIELD/FIELD_0/NAME/.zarray",
    "FIELD/FIELD_0/NAME/0",
    "POLARIZATION/POLARIZATION_0/CORR_TYPE/.zarray",
    "POLARIZATION/POLARIZATION_0/CORR_TYPE/0.0",
)
CODE_FILES = (*core_campaign.CODE_FILES, "python/rangtoy/core_campaign_array.py")


# --- cost bookkeeping --------------------------------------------------------


def cpu_seconds():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def mem_available_gib():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2**20
    except OSError:
        pass
    return None


class Stages:
    """Wall, CPU (cores busy) and the RSS high-water mark per stage."""

    def __init__(self):
        self.records = {}

    def start(self):
        return time.perf_counter(), cpu_seconds()

    def stop(self, name, mark):
        wall = time.perf_counter() - mark[0]
        cpu = cpu_seconds() - mark[1]
        self.records[name] = {
            "seconds": wall,
            "cpu_seconds": cpu,
            "cores_busy": cpu / wall if wall > 0 else None,
            "max_rss_mb": rss_mb(),
        }
        return self.records[name]


# --- local inputs ------------------------------------------------------------


def resolve(key, roots=ROOTS):
    """The archived object `key`, from whichever root holds it."""
    for root in roots:
        if (Path(root) / key).exists():
            return Path(root) / key
    raise FileNotFoundError(key)


def archived_receipts(roots=ROOTS):
    return receipt_lines(*(Path(r) / "receipt.txt" for r in roots))


def verify_object(key, receipts, roots=ROOTS):
    """Size and SHA256 of a local object against its archived receipt line."""
    path = resolve(key, roots)
    size = path.stat().st_size
    digest = file_sha256(path)
    expected = receipts.get(key)
    return {
        "key": key,
        "root": str(path.parent.relative_to(ROOT))
        if path.is_relative_to(ROOT)
        else str(path.parent),
        "bytes": size,
        "sha256": digest,
        "receipt": list(expected) if expected else None,
        "ok": expected is not None and expected == (size, digest),
    }


def tile_keys(columns=core_fetch.TILE_COLUMNS, tiles=TILES):
    return [f"{GROUP}/{name}/0.{tile}.0" for name in columns for tile in tiles]


def input_keys():
    keys = []
    for name, _ in core_fetch.ROW_COLUMNS:
        keys += [f"{GROUP}/{name}/.zarray", f"{GROUP}/{name}/0"]
    for name in core_fetch.TILE_COLUMNS:
        keys.append(f"{GROUP}/{name}/.zarray")
    return keys + tile_keys() + list(EXTRA_KEYS)


def verify_inputs(roots=ROOTS):
    """Criterion 1: every object the campaign reads equals its receipt line."""
    receipts = archived_receipts(roots)
    started = time.perf_counter()
    records = [verify_object(key, receipts, roots) for key in input_keys()]
    headers = {}
    for name in core_fetch.TILE_COLUMNS:
        meta = core_zarr.array_meta(resolve(f"{GROUP}/{name}", roots))
        whole = int(np.prod(meta["chunks"])) * np.dtype(meta["dtype"]).itemsize
        for tile in TILES:
            with open(resolve(f"{GROUP}/{name}/0.{tile}.0", roots), "rb") as stream:
                nbytes = core_zarr.header_fields(stream.read(core_fetch.HEADER))[0]
            headers[f"{name}/0.{tile}.0"] = [int(nbytes), whole]
    return {
        "objects": records,
        "all_match_receipts": all(r["ok"] for r in records),
        "bytes_hashed": sum(r["bytes"] for r in records),
        "whole_tile_headers": all(a == b for a, b in headers.values()),
        "tile_nbytes": headers,
        "fetched_bytes": 0,
        "fetched_requests": 0,
        "seconds": time.perf_counter() - started,
    }


def decode_row_columns(roots=ROOTS):
    arrays = {}
    for name, dtype in core_fetch.ROW_COLUMNS:
        payload = resolve(f"{GROUP}/{name}/0", roots).read_bytes()
        values = np.frombuffer(core.blosc_decode(payload), dtype)
        arrays[name] = np.ascontiguousarray(values[:CHUNK_ROWS])
    return arrays


def decode_inputs(stations=None, roots=ROOTS):
    """The kept rows of every column, tiles decoded into preallocated arrays.

    `stations=None` keeps all stations. Returns (arrays, rows, statistics).
    """
    started = time.perf_counter()
    row_arrays = decode_row_columns(roots)
    nant_total = int(max(row_arrays["ANTENNA1"].max(), row_arrays["ANTENNA2"].max()))
    stations = list(range(nant_total + 1)) if stations is None else list(stations)
    rows = core_fetch.kept_rows(row_arrays, stations)
    arrays = {k: np.ascontiguousarray(v[rows]) for k, v in row_arrays.items()}
    stats = {"blocks_decoded": 0, "blocks_total": 0, "bytes_read": 0}
    lo, hi = CHANNELS
    for name in core_fetch.TILE_COLUMNS:
        meta = core_zarr.array_meta(resolve(f"{GROUP}/{name}", roots))
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        dtype = np.dtype(meta["dtype"])
        row_bytes = nchan * ncorr * dtype.itemsize
        out = np.empty((len(rows), hi - lo, ncorr), dtype)
        for tile in TILES:
            # P5: each tile decodes straight into its channel range of `out`.
            first = tile * nchan - lo
            tile_stats = core_fetch.read_rows_into(
                resolve(f"{GROUP}/{name}/0.{tile}.0", roots),
                row_bytes,
                rows,
                out,
                first * ncorr * dtype.itemsize,
            )
            for k in stats:
                stats[k] += tile_stats[k]
        arrays[name] = out
    stats["seconds"] = time.perf_counter() - started
    return arrays, rows, stats


def decode_extra(rows, roots=ROOTS, channels=CHANNELS):
    """K's `decode_extra` with each object resolved across the archived roots."""

    def obj(key, chunk):
        return core_campaign.decode_object(
            resolve(key, roots).parent, key.split("/")[-1], chunk
        )

    attrs = json.loads(resolve(f"{GROUP}/.zattrs", roots).read_text())
    field = int(attrs["FIELD_ID"])
    lo, hi = channels
    uvw = obj(f"{GROUP}/UVW", "0.0")
    return {
        "field_id": field,
        "scan_number": int(attrs["SCAN_NUMBER"]),
        "uvw": np.ascontiguousarray(uvw[np.asarray(rows)], np.float64),
        "antenna_position": np.ascontiguousarray(
            obj("ANTENNA/ANTENNA_0/POSITION", "0.0"), np.float64
        ),
        "antenna_names": [str(n) for n in obj("ANTENNA/ANTENNA_0/NAME", "0")],
        "chan_freq": np.ascontiguousarray(
            obj("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_FREQ", "0.0")[0, lo:hi],
            np.float64,
        ),
        "chan_width": np.ascontiguousarray(
            obj("SPECTRAL_WINDOW/SPECTRAL_WINDOW_0/CHAN_WIDTH", "0.0")[0, lo:hi],
            np.float64,
        ),
        "phase_dir": np.asarray(
            obj("FIELD/FIELD_0/PHASE_DIR", "0.0.0")[field, 0], np.float64
        ),
        "field_name": str(obj("FIELD/FIELD_0/NAME", "0")[field]),
        "corr_type": np.ascontiguousarray(
            obj("POLARIZATION/POLARIZATION_0/CORR_TYPE", "0.0")[0], np.int32
        ),
    }


# --- state, solves, features -------------------------------------------------


def row_blocks(nrow, block=ROW_BLOCK):
    for start in range(0, nrow, block):
        yield slice(start, min(start + block, nrow))


def eligible_cells(flags, rows, data, weights, model, p, q, block=ROW_BLOCK):
    """K's eligibility (no original flag in any correlation, FLAG_ROW false,
    cross-correlation, finite data, model and weights, positive weights) in
    row blocks: the booleans of `~protected_flags(...)[0].any(-1) & ...`."""
    eligible = np.empty(flags.shape[:2], bool)
    for s in row_blocks(len(flags), block):
        e = ~flags[s].any(axis=-1)
        e &= ~rows[s][:, None]
        e &= (p[s] != q[s])[:, None]
        e &= np.isfinite(data[s]).all(axis=-1)
        e &= np.isfinite(weights[s]).all(axis=-1)
        e &= (weights[s] > 0).all(axis=-1)
        e &= np.isfinite(model[s]).all(axis=-1)
        eligible[s] = e
    return eligible


def split_holdout_lean(
    eligible,
    seed,
    groups,
    validation_fraction=0.1,
    test_fraction=0.1,
    minimum_train=2,
    block=ROW_BLOCK,
):
    """`flagging.split_holdout(eligible, seed, groups=G)` without its
    full-size temporaries; `groups(s)` returns the group labels of row block
    `s`. The seed's draws are taken in row blocks (the same stream in the
    same order), only the eligible cells' draws and groups are kept, and the
    `minimum_train` cells reserved per group (largest draw first, ties by
    cell order) come from one stable lexsort instead of a loop over groups.
    Bit-identical by construction; tests compare it with the original."""
    if (
        min(validation_fraction, test_fraction) < 0
        or not 0 <= validation_fraction + test_fraction < 1
    ):
        raise ValueError("holdout fractions must leave training samples")
    if minimum_train < 1:
        raise ValueError("holdout groups must match samples and retain training data")
    rng = np.random.default_rng(seed)
    nrow, nchan = eligible.shape
    validation = np.empty_like(eligible)
    test = np.empty_like(eligible)
    n = int(np.count_nonzero(eligible))
    draws = np.empty(n)
    labels = np.empty(n, np.int64)
    at = 0
    for s in row_blocks(nrow, block):
        random = rng.random((s.stop - s.start, nchan))
        e = eligible[s]
        validation[s] = e & (random < validation_fraction)
        test[s] = (
            e
            & (random >= validation_fraction)
            & (random < validation_fraction + test_fraction)
        )
        k = int(np.count_nonzero(e))
        draws[at : at + k] = random[e]
        g = np.asarray(groups(s))
        if g.shape != e.shape:
            raise ValueError(
                "holdout groups must match samples and retain training data"
            )
        labels[at : at + k] = g[e]
        at += k
        del random, g
    order = np.lexsort((-draws, labels))
    del draws
    labels = labels[order]
    start = np.ones(n, bool)
    start[1:] = labels[1:] != labels[:-1]
    del labels
    first = np.flatnonzero(start)
    rank = np.arange(n) - first[np.cumsum(start) - 1]
    del start, first
    reserved = order[rank < minimum_train]
    del order, rank
    cells = np.flatnonzero(eligible)[reserved]
    validation.reshape(-1)[cells] = False
    test.reshape(-1)[cells] = False
    return eligible & ~(validation | test), validation, test


def build_state(
    arrays, extra, nant, seed=core_campaign.SPLIT_SEED, grid=core_campaign.GRID
):
    """K's `build_state` with the station count as a parameter (K: 4)."""
    data = np.ascontiguousarray(arrays["DATA"], np.complex64)
    model = np.ascontiguousarray(arrays["MODEL_DATA"], np.complex64)
    weights = np.ascontiguousarray(arrays["WEIGHT_SPECTRUM"], np.float32)
    flags = np.ascontiguousarray(arrays["FLAG"], bool)
    rows = np.ascontiguousarray(arrays["FLAG_ROW"], bool)
    p = np.ascontiguousarray(arrays["ANTENNA1"], np.int32)
    q = np.ascontiguousarray(arrays["ANTENNA2"], np.int32)
    times = np.ascontiguousarray(arrays["TIME"], np.float64)
    names = list(extra["antenna_names"][:nant])
    eligible = eligible_cells(flags, rows, data, weights, model, p, q)
    time_bins = np.unique(times, return_inverse=True)[1] // grid[0]
    freq_bins = np.arange(data.shape[1]) // grid[1]

    def groups(s):
        return (
            time_bins[s, None] * (freq_bins.max() + 1) + freq_bins[None]
        ) * nant**2 + (p[s] * nant + q[s])[:, None]

    train, validation, test = split_holdout_lean(eligible, seed, groups)
    return {
        "original_flags": flags,
        "original_rows": rows,
        "data": data,
        "model": model,
        "weights": weights,
        "times": times,
        "frequencies": extra["chan_freq"],
        "antenna1": p,
        "antenna2": q,
        "names": names,
        "eligible": eligible,
        "train": train,
        "validation": validation,
        "test": test,
        "window": np.ones(data.shape[1], bool),
    }


def residual_amplitude(
    state, gains, valid, labels, time_map, freq_map, block=ROW_BLOCK
):
    """Whitened residual amplitude per sample, `|r sqrt(w)|` over the four
    correlations, from the fused pass in row blocks (K: one call, then
    `residuals * sqrt(weights)` on the whole array)."""
    nrow, nchan = state["data"].shape[:2]
    amplitude = np.empty((nrow, nchan))
    for start in range(0, nrow, block):
        s = slice(start, min(start + block, nrow))
        fused = core.fused_pass(
            state["data"][s],
            state["weights"][s],
            state["antenna1"][s],
            state["antenna2"][s],
            time_map[s],
            freq_map,
            gains,
            valid,
            labels[s],
            model=state["model"][s],
            residuals=True,
            scores=False,
            normals=False,
        )
        whitened = fused.residuals * np.sqrt(state["weights"][s])
        amplitude[s] = np.sqrt(np.sum(np.abs(whitened) ** 2, axis=-1))
    return amplitude


def baseline_scores(amplitude, eligible, antenna1, antenna2):
    """`flagging.residual_features` from the amplitude, one baseline's rows at a
    time. Same estimator, same values: each baseline's cells are the same
    multiset in the same order."""
    amplitude = np.asarray(amplitude)
    eligible = np.asarray(eligible, bool)
    antenna1, antenna2 = np.asarray(antenna1), np.asarray(antenna2)
    z = np.zeros_like(amplitude, dtype=float)
    order = np.lexsort((antenna2, antenna1))
    pairs = np.stack([antenna1[order], antenna2[order]], axis=1)
    cut = np.flatnonzero(np.any(np.diff(pairs, axis=0) != 0, axis=1)) + 1
    for group in np.split(order, cut):
        rows = np.sort(group)
        amp = amplitude[rows]
        mask = eligible[rows] & np.isfinite(amp)
        if not mask.any():
            continue
        log_amplitude = np.log(np.maximum(amp, 1e-30))
        median = np.median(log_amplitude[mask])
        deviation = max(1.4826 * np.median(np.abs(log_amplitude[mask] - median)), 0.05)
        block = z[rows]
        block[mask] = np.maximum((log_amplitude[mask] - median) / deviation, 0)
        z[rows] = block
    return z


def additions_dense(state, indices):
    """A stored solve's additions (sorted cell indices) as a `(row, chan)` mask."""
    mask = np.zeros(state["train"].shape, bool)
    mask.reshape(-1)[np.asarray(indices, np.int64)] = True
    return mask


def solve_flags_lean(state, added, block=ROW_BLOCK):
    """`core_workflow.solve_flags(state, added)` (holdout cells and additions
    flagged on top of the protected originals) in row blocks into one cube."""
    original, rows, train = (
        state["original_flags"],
        state["original_rows"],
        state["train"],
    )
    added = np.asarray(added, bool)
    flags = np.empty(original.shape, bool)
    flag_rows = np.empty(rows.shape, bool)
    for s in row_blocks(len(rows), block):
        f = flags[s]
        np.logical_or(original[s], rows[s][:, None, None], out=f)
        np.logical_or(f, (~train[s] | added[s])[..., None], out=f)
        flag_rows[s] = rows[s] | f.all(axis=(1, 2))
    return flags, flag_rows


def guidance_values(state, maps, time_map, freq_map, rows, chans):
    """K's TV guidance `max(map[t, f, p], map[t, f, q])` at the given cells."""
    t, f = time_map[rows], freq_map[chans]
    return np.maximum(
        maps[t, f, state["antenna1"][rows]], maps[t, f, state["antenna2"][rows]]
    )


def guidance_scale(state, maps, time_map, freq_map, block=ROW_BLOCK):
    """`policy_mask`'s scale: the median of the positive finite guidance over
    the training cells, gathered in row blocks (same values, same order)."""
    parts = []
    p, q, train = state["antenna1"], state["antenna2"], state["train"]
    for s in row_blocks(len(p), block):
        t, f = time_map[s][:, None], freq_map[None]
        g = np.maximum(maps[t, f, p[s][:, None]], maps[t, f, q[s][:, None]])
        parts.append(g[train[s] & np.isfinite(g) & (g > 0)])
    positive = np.concatenate(parts) if parts else np.zeros(0)
    return np.median(positive) if len(positive) else 1.0


def baseline_groups(antenna1, antenna2, nant, rows_per_group=FEATURE_ROWS):
    """Rows of whole baselines, grouped in baseline order up to
    `rows_per_group` rows each (a baseline larger than that is its own group)."""
    baseline = np.asarray(antenna1, np.int64) * nant + np.asarray(antenna2, np.int64)
    values, counts = np.unique(baseline, return_counts=True)
    groups, current, size = [], [], 0
    for value, count in zip(values.tolist(), counts.tolist()):
        if current and size + count > rows_per_group:
            groups.append(current)
            current, size = [], 0
        current.append(value)
        size += count
    if current:
        groups.append(current)
    return [np.flatnonzero(np.isin(baseline, g)) for g in groups]


def fused_candidates(
    state, gains, valid, time_map, freq_map, rows_per_group=FEATURE_ROWS
):
    """Training cells with fused-pass score `>= 2`: sorted cell indices and
    their scores. The fused pass runs on groups of whole baselines; a
    baseline's robust scores depend only on its own training cells in cell
    order, so they equal those of one call on every row."""
    nrow, nchan = state["train"].shape
    nant = gains.shape[2]
    found, values = [], []
    for rows in baseline_groups(
        state["antenna1"], state["antenna2"], nant, rows_per_group
    ):
        if len(rows) == nrow:

            def take(name):
                return state[name]
        else:

            def take(name, rows=rows):
                return np.ascontiguousarray(state[name][rows])

        fused = core.fused_pass(
            take("data"),
            take("weights"),
            take("antenna1"),
            take("antenna2"),
            time_map[rows],
            freq_map,
            gains,
            valid,
            core.split_labels(train=take("train")),
            model=take("model"),
            residuals=False,
            scores=True,
            normals=False,
        )
        r, c = np.nonzero(fused.scores >= 2)
        found.append(rows[r] * nchan + c)
        values.append(fused.scores[r, c])
        del fused
    cells = np.concatenate(found) if found else np.zeros(0, np.int64)
    scores = np.concatenate(values) if values else np.zeros(0)
    order = np.argsort(cells, kind="stable")
    return cells[order], scores[order]


def solve_features(state, gains, valid, time_map, freq_map, maps, scores=None):
    """The policy loop's inputs from a base solve, kept sparse: the training
    cells that can ever be proposed (`outliers >= 2`), their outlier scores
    and TV guidance, the guidance median over all training cells and the
    training count. `scores="numpy"` takes L1's row-block amplitude path."""
    scores = SCORES if scores is None else scores
    train = state["train"]
    nchan = train.shape[1]
    if scores == "numpy":
        labels = core.split_labels(
            train=state["train"], validation=state["validation"], test=state["test"]
        )
        amplitude = residual_amplitude(state, gains, valid, labels, time_map, freq_map)
        z = baseline_scores(amplitude, train, state["antenna1"], state["antenna2"])
        del amplitude, labels
        cells = np.flatnonzero(train & (z >= 2))
        outliers = z.reshape(-1)[cells]
        del z
    elif scores == "fused":
        cells, outliers = fused_candidates(state, gains, valid, time_map, freq_map)
    else:
        raise ValueError(f"unknown scores {scores!r}")
    rows, chans = np.divmod(cells, nchan)
    return {
        "scores": scores,
        "cells": cells,
        "outliers": outliers,
        "guidance": guidance_values(state, maps, time_map, freq_map, rows, chans),
        "guidance_scale": guidance_scale(state, maps, time_map, freq_map),
        "eligible_count": int(np.count_nonzero(train)),
    }


def sparse_policy_mask(features, shape, *, threshold, tv_weight, max_fraction):
    """`flagging.policy_mask(outliers, guidance, train, ...)` on the sparse
    features: every cell it can propose is in `features["cells"]`, and the
    same elementwise arithmetic and the same stable top-k cut are applied
    there, so the mask is identical."""
    if not (threshold > 0 and tv_weight >= 0 and 0 <= max_fraction < 1):
        raise ValueError("invalid policy parameters")
    outliers, guidance = features["outliers"], features["guidance"]
    scale = features["guidance_scale"]
    relative = np.clip(np.nan_to_num(guidance / max(scale, 1e-30), nan=0), 0, 5)
    score = outliers * (1 + tv_weight * relative)
    proposed = np.isfinite(score) & (outliers >= 2) & (score > threshold)
    limit = int(np.floor(max_fraction * features["eligible_count"]))
    cells = features["cells"][proposed]
    if len(cells) > limit:
        order = np.argsort(-score[proposed], kind="stable")
        cells = np.sort(cells[order[:limit]])
    mask = np.zeros(shape, bool)
    mask.reshape(-1)[cells] = True
    return mask


def solve_arm(state, added, label, scale=None, features=False):
    """`core_workflow.core_solve` plus K's `solve_arm` summaries, without
    keeping residuals. With `features`, also the sparse outlier scores and
    TV guidance that the policy loop needs from its base solve. The
    additions are stored as sorted cell indices."""
    added = np.asarray(added, bool)
    flags, rows = solve_flags_lean(state, added)
    time_map, freq_map, gain_times, gain_freqs = gain_grid(state, *core_campaign.GRID)
    nant = len(state["names"])
    started = time.perf_counter()
    solution = core.solve_complex(
        state["data"],
        state["weights"],
        flags,
        rows,
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
        ntime_bins=len(gain_times),
        nfreq_bins=len(gain_freqs),
        nant=nant,
        model=state["model"],
        max_iterations=core_campaign.ITERATIONS,
    )
    del flags
    gains = solution.gains
    valid = (solution.flags == 0) & np.isfinite(gains).all(axis=(-1, -2))
    labels = core.split_labels(
        train=state["train"], validation=state["validation"], test=state["test"]
    )
    fused = core.fused_pass(
        state["data"],
        state["weights"],
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
        gains,
        valid,
        labels,
        model=state["model"],
        residuals=False,
        scores=False,
        normals=False,
    )
    elapsed = time.perf_counter() - started
    if scale is None:
        scale = float(np.median(np.linalg.norm(gains[valid], axis=(-1, -2))))
    del labels
    raw_tv = gain_tv(gains, valid, gain_times, gain_freqs, scale=scale)
    aligned, tv_valid = polar_gauge(gains, valid)
    tv = gain_tv(aligned, tv_valid, gain_times, gain_freqs, scale=scale)
    metrics = {
        "trial": label,
        "seconds": elapsed,
        "tv": tv["total"],
        "raw_tv": raw_tv["total"],
        "time_tv": tv["time"],
        "frequency_tv": tv["frequency"],
        "scale": scale,
        "valid_gain_fraction": float(np.mean(valid)),
        "losses": fused.losses(),
        "invalid_predictions": fused.invalid_predictions(),
        "added_count": int(np.sum(added)),
        "added_fraction": float(np.sum(added) / np.sum(state["train"])),
        "solver": {
            "iterations": solution.iterations,
            "converged_fraction": solution.converged_fraction,
        },
    }
    diag = np.abs(gains[valid][:, [0, 1], [0, 1]])
    off = np.abs(gains[valid][:, [0, 1], [1, 0]])
    metrics["median_diagonal_amplitude"] = float(np.median(diag)) if diag.size else None
    metrics["median_offdiagonal_amplitude"] = (
        float(np.median(off)) if off.size else None
    )
    metrics["gauge_lost_valid_fraction"] = (
        float(np.count_nonzero(valid & ~tv_valid) / np.count_nonzero(valid))
        if valid.any()
        else None
    )
    metrics["station_valid_bins"] = [int(n) for n in valid.sum(axis=(0, 1))]
    solve = {
        "label": label,
        "added": np.flatnonzero(added),
        "metrics": metrics,
        "tv": {"edges": tv["edges"], "total": tv["total"]},
        "diagnostics": {"gains": gains, "gain_valid": valid},
    }
    if features:
        mark = time.perf_counter()
        solve["features"] = solve_features(
            state, gains, valid, time_map, freq_map, tv["map"]
        )
        metrics["feature_seconds"] = time.perf_counter() - mark
    return solve


def strip(solve):
    """A stored solve: everything but the policy features."""
    return {k: v for k, v in solve.items() if k != "features"}


def tv_loop(state, base, scale, prefix):
    """K's `tv_loop` (one round of the frozen policy) on `solve_arm` solves.

    `base` must carry `features` (a `features=True` solve)."""
    cfg = core_campaign
    base_added = additions_dense(state, base["added"])
    denominator = max(base["metrics"]["tv"], 1e-30)
    validation0 = base["metrics"]["losses"]["validation"]
    if (
        validation0 is None
        or fixed_support_tv(base["tv"]["edges"], base["tv"]["edges"]) is None
    ):
        raise RuntimeError(f"{prefix}: base solve has no validation loss or TV support")
    validation0 = max(validation0, 1e-30)
    best_objective = base["metrics"]["tv"] / denominator + cfg.VALIDATION_WEIGHT
    best = {"solve": strip(base), "policy": None, "objective": best_objective}
    trials = [
        {
            "trial": base["label"],
            "policy": None,
            "objective": best_objective,
            "accepted": True,
            "added_count": int(base_added.sum()),
        }
    ]
    seen = {sha256(base_added.tobytes()).hexdigest()}
    unguided = None
    ntrain = np.count_nonzero(state["train"])
    for tv_weight in cfg.TV_WEIGHTS:
        for threshold in cfg.THRESHOLDS:
            mask = sparse_policy_mask(
                base["features"],
                base_added.shape,
                threshold=threshold,
                tv_weight=tv_weight,
                max_fraction=cfg.MAX_FRACTION,
            )
            added = base_added | mask
            policy = {"threshold": float(threshold), "tv_weight": float(tv_weight)}
            fingerprint = sha256(added.tobytes()).hexdigest()
            label = f"{prefix}-w{tv_weight:g}-z{threshold:g}"
            if fingerprint in seen:
                trials.append(
                    {
                        "trial": label,
                        "policy": policy,
                        "duplicate_mask": fingerprint,
                        "mask_count": int(mask.sum()),
                    }
                )
                continue
            seen.add(fingerprint)
            solve = solve_arm(state, added, label, scale=scale)
            tv_score = fixed_support_tv(solve["tv"]["edges"], base["tv"]["edges"])
            val = solve["metrics"]["losses"]["validation"]
            admissible = (
                tv_score is not None
                and val is not None
                and val <= (1 + cfg.VALIDATION_TOLERANCE) * validation0
            )
            objective = (
                tv_score / denominator
                + cfg.FLAG_PENALTY * (mask.sum() / ntrain)
                + cfg.VALIDATION_WEIGHT * val / validation0
                if admissible
                else None
            )
            accepted = bool(admissible and objective < best_objective)
            trials.append(
                {
                    "trial": label,
                    "policy": policy,
                    "mask_count": int(mask.sum()),
                    "added_count": int(added.sum()),
                    "fixed_support_tv_vs_base": tv_score,
                    "losses": solve["metrics"]["losses"],
                    "invalid_predictions": solve["metrics"]["invalid_predictions"],
                    "converged_fraction": solve["metrics"]["solver"][
                        "converged_fraction"
                    ],
                    "objective": objective,
                    "accepted": accepted,
                    "rejection": None
                    if admissible
                    else "gain support loss or validation degradation",
                    "mask_sha256": fingerprint,
                    "solve_seconds": solve["metrics"]["seconds"],
                }
            )
            if (
                tv_weight == 0
                and admissible
                and (unguided is None or objective < unguided["objective"])
            ):
                unguided = {"solve": solve, "policy": policy, "objective": objective}
            if accepted:
                best_objective = objective
                best = {"solve": solve, "policy": policy, "objective": objective}
    return trials, best, unguided


def tricolour_arm(state, extra, strategy_path):
    """K's `tricolour_arm` without the intensity output (flags unaffected)."""
    text = Path(strategy_path).read_text()
    strategies = core_flag.parse_strategy(text)
    started = time.perf_counter()
    result = core_flag.flag_rows(
        state["data"],
        state["original_flags"],
        state["antenna1"],
        state["antenna2"],
        state["times"],
        extra["antenna_position"],
        state["frequencies"],
        extra["chan_width"],
        extra["corr_type"],
        strategies,
        want_intensity=False,
    )
    wall = time.perf_counter() - started
    window = result["flags"].any(axis=-1)
    additions = state["train"] & window
    summary = {
        "strategy": Path(strategy_path).name,
        "strategy_sha256": sha256(text.encode()).hexdigest(),
        "steps": len(strategies),
        "core_seconds": result["seconds"],
        "wall_seconds": wall,
        "window_flag_fraction": float(result["flags"].mean()),
        "newly_flagged_cells": int(
            np.count_nonzero(window & ~state["original_flags"].any(-1))
        ),
        "additions_on_train": int(np.count_nonzero(additions)),
        "checks": tricolour_checks(result, state["original_flags"], strategies),
    }
    return additions, summary


# --- imaging -----------------------------------------------------------------


def correct_stokes_i(state, gains, valid, added, sample=None, weight=None):
    """Gain-corrected Stokes I sample (complex64) and reader weight (float32),
    `(row, chan)`, from the core's `correct_stokes_i` (P5): per cell
    `G_p^{-1} V G_q^{-H}` with inverses from `np.linalg.inv` (those of
    `core_campaign.apply_gains`), rounded to complex64, then K's reader on
    the final flags (original | FLAG_ROW | addition | invalid gain). `added`
    is a `(row, chan)` mask or None; `sample` and `weight` are optional
    buffers to write into."""
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    nrow, nchan = state["data"].shape[:2]
    gains = np.ascontiguousarray(gains, np.complex128)
    valid = np.ascontiguousarray(valid, bool)
    inverse = np.zeros(gains.shape, np.complex128)
    if valid.any():
        inverse[valid] = np.linalg.inv(gains[valid])
    if sample is None:
        sample = np.empty((nrow, nchan), np.complex64)
    if weight is None:
        weight = np.empty((nrow, nchan), np.float32)
    if (
        sample.shape != (nrow, nchan)
        or sample.dtype != np.complex64
        or weight.shape != (nrow, nchan)
        or weight.dtype != np.float32
        or not (sample.flags.c_contiguous and weight.flags.c_contiguous)
    ):
        raise ValueError("sample and weight must be C-contiguous (row, chan) buffers")
    nt, nf, na = gains.shape[:3]
    arrays = {
        "data": np.require(state["data"], np.complex64, ["C", "A"]).view(np.float32),
        "weights": np.require(state["weights"], np.float32, ["C", "A"]),
        "flags": np.require(state["original_flags"], bool, ["C", "A"]).view(np.uint8),
        "flag_row": np.require(state["original_rows"], bool, ["C", "A"]).view(np.uint8),
        "added": None
        if added is None
        else np.require(added, bool, ["C", "A"]).view(np.uint8),
        "antenna1": np.ascontiguousarray(state["antenna1"], np.uint32),
        "antenna2": np.ascontiguousarray(state["antenna2"], np.uint32),
        "time_bin": np.ascontiguousarray(time_map, np.uint32),
        "freq_bin": np.ascontiguousarray(freq_map, np.uint32),
        "inverse": inverse.view(np.float64),
        "valid": valid.view(np.uint8),
    }
    if arrays["added"] is not None and arrays["added"].shape != (nrow, nchan):
        raise ValueError("added must be (row, chan)")
    ext = core_fetch.p5_extension()
    if ext is not None:
        status = ext.correct_stokes_i(
            nrow,
            nchan,
            nt,
            nf,
            na,
            *arrays.values(),
            sample.view(np.float32),
            weight,
        )
    else:
        inputs = core_fetch.CorrectInputs(
            nrow,
            nchan,
            nt,
            nf,
            na,
            *(None if a is None else a.ctypes.data for a in arrays.values()),
        )
        status = core_fetch.p5_library().rang_core_correct_stokes_i(
            ctypes.byref(inputs), sample.ctypes.data, weight.ctypes.data
        )
    if status:
        raise RuntimeError(f"rang_core_correct_stokes_i failed with status {status}")
    return sample, weight


def corrected_stokes(state, solve, sample=None, weight=None):
    """The image inputs of one arm: `correct_stokes_i` on its gains and
    additions, into the optional reused buffers."""
    added = additions_dense(state, solve["added"]) if len(solve["added"]) else None
    return correct_stokes_i(
        state,
        solve["diagnostics"]["gains"],
        solve["diagnostics"]["gain_valid"],
        added,
        sample,
        weight,
    )


def corrected_stokes_reference(state, gains, valid, added, block=ROW_BLOCK):
    """L1's corrected-data Stokes I reader inputs in row blocks
    (`core_campaign.apply_gains` and `core_grid.stokes_i_reader` on the final
    flags): the reference that `correct_stokes_i` is tested against."""
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    nrow, nchan = state["data"].shape[:2]
    sample = np.empty((nrow, nchan), np.complex64)
    weight = np.empty((nrow, nchan), np.float32)
    if added is None:
        added = np.zeros((nrow, nchan), bool)
    added = np.broadcast_to(added[..., None], state["original_flags"].shape)
    final, final_rows = protected_flags(
        state["original_flags"], state["original_rows"], added
    )
    for start in range(0, nrow, block):
        s = slice(start, min(start + block, nrow))
        corrected, ok = core_campaign.apply_gains(
            state["data"][s],
            gains,
            valid,
            state["antenna1"][s],
            state["antenna2"][s],
            time_map[s],
            freq_map,
        )
        sample[s], weight[s] = core_grid.stokes_i_reader(
            corrected,
            state["weights"][s],
            final[s] | ~ok[..., None],
            flag_rows=final_rows[s],
        )
    return sample, weight, final, final_rows


def grouped_invert(uvw, frequencies, sample, weight, imaging, image, groups):
    """`core_grid.invert` over `groups` contiguous channel groups, summed.

    One group is the plain call. Otherwise each group's unnormalised images
    `R_k = dirty_k W_k / N_k` are summed and renormalised by the summed PSF
    centre, which is the single call up to the per-group w-layer placement."""
    if groups == 1:
        out = core_grid.invert(uvw, frequencies, sample, weight, imaging, **image)
        out["groups"] = [dict(out["stats"])]
        return out
    nchan = len(frequencies)
    edges = np.linspace(0, nchan, groups + 1).astype(int)
    h, w = image["height"], image["width"]
    raw = np.zeros((h, w))
    raw_psf = np.zeros((h, w))
    records = []
    for lo, hi in itertools.pairwise(edges):
        if not np.any((weight[:, lo:hi] * imaging[:, lo:hi]) != 0):
            records.append({"channels": [int(lo), int(hi)], "skipped": True})
            continue
        part = core_grid.invert(
            uvw,
            frequencies[lo:hi],
            sample[:, lo:hi],
            weight[:, lo:hi],
            imaging[:, lo:hi],
            **image,
        )
        st = part["stats"]
        factor = st["image_weight"] / st["psf_normalization"]
        raw += part["dirty"] * factor
        raw_psf += part["psf"] * factor
        records.append({"channels": [int(lo), int(hi)], "skipped": False, **st})
    centre = raw_psf[h // 2, w // 2]
    used = [r for r in records if not r["skipped"]]
    image_weight = sum(r["image_weight"] for r in used)
    stats = {
        "visibility_weight_sum": sum(r["visibility_weight_sum"] for r in used),
        "gridded_count": sum(r["gridded_count"] for r in used),
        "image_weight": image_weight,
        "psf_normalization": image_weight / centre,
        "n_w_layers": image["w_layers"],
        "max_gridded_weight": max(r["max_gridded_weight"] for r in used),
        "min_w": min(r["min_w"] for r in used),
        "max_w": max(r["max_w"] for r in used),
    }
    return {
        "dirty": raw / centre,
        "psf": raw_psf / centre,
        "stats": stats,
        "groups": records,
    }


def psf_fwhm(psf):
    """Main-lobe FWHM in pixels from half-power crossings through the centre
    along the row, the column and both diagonals (diagonals scaled by sqrt 2)."""
    psf = np.asarray(psf, np.float64)
    h, w = psf.shape
    cy, cx = h // 2, w // 2
    psf = psf / psf[cy, cx]
    widths = {}
    for name, (dy, dx) in {
        "x": (0, 1),
        "y": (1, 0),
        "diagonal": (1, 1),
        "antidiagonal": (1, -1),
    }.items():
        step = math.hypot(dy, dx)
        total = 0.0
        for sign in (1, -1):
            k, previous = 0, 1.0
            while True:
                k += 1
                y, x = cy + sign * k * dy, cx + sign * k * dx
                if not (0 <= y < h and 0 <= x < w):
                    total = math.nan
                    break
                value = psf[y, x]
                if value < 0.5:
                    total += step * ((k - 1) + (previous - 0.5) / (previous - value))
                    break
                previous = value
        widths[name] = total
    finite = [v for v in widths.values() if np.isfinite(v)]
    return {"fwhm_pixels": widths, "fwhm_max_pixels": max(finite) if finite else None}


def boxes_from_psf(psf, width):
    fwhm = psf_fwhm(psf)
    f = fwhm["fwhm_max_pixels"]
    return {
        **fwhm,
        "main_lobe_half_width": math.ceil(1.5 * f),
        "far_half_width": int(min(width // 4, max(32, math.ceil(20 * f)))),
    }


def robust_sigma(values):
    values = np.asarray(values, np.float64)
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def array_image_metrics(dirty, psf, boxes, model_flux=None):
    """K's image metrics with the boxes measured on the `original` PSF."""
    dirty = np.asarray(dirty, np.float64)
    psf = np.asarray(psf, np.float64)
    h, w = dirty.shape
    cy, cx = h // 2, w // 2
    r = boxes["main_lobe_half_width"]
    box = dirty[cy - r : cy + r + 1, cx - r : cx + r + 1]
    iy, ix = np.unravel_index(np.argmax(box), box.shape)
    py, px = cy - r + iy, cx - r + ix
    peak = float(dirty[py, px])
    centre = psf[cy, cx]
    psfn = psf / centre if centre else psf
    inner = np.zeros_like(dirty, bool)
    inner[cy - r : cy + r + 1, cx - r : cx + r + 1] = True
    far = np.ones_like(dirty, bool)
    o = boxes["far_half_width"]
    far[cy - o : cy + o + 1, cx - o : cx + o + 1] = False
    shifted = np.roll(np.roll(psfn, py - cy, axis=0), px - cx, axis=1)
    residual = dirty - peak * shifted
    out = {
        "peak_jy_per_beam": peak,
        "peak_pixel": [int(py), int(px)],
        "psf_centre": float(centre),
        "psf_fwhm": psf_fwhm(psf),
        "psf_max_sidelobe": float(np.abs(psfn[~inner]).max()),
        "psf_max_far": float(np.abs(psfn[far]).max()),
        "offsource_rms": float(np.sqrt(np.mean(dirty[far] ** 2))),
        "offsource_robust_sigma": robust_sigma(dirty[far]),
        "residual_rms": float(np.sqrt(np.mean(residual**2))),
        "residual_rms_offsource": float(np.sqrt(np.mean(residual[far] ** 2))),
        "residual_robust_sigma_offsource": robust_sigma(residual[far]),
        "residual_max_abs": float(np.abs(residual).max()),
        "boxes": {k: boxes[k] for k in ("main_lobe_half_width", "far_half_width")},
    }
    if model_flux:
        out["model_stokes_i_jy"] = float(model_flux)
        out["flux_recovery"] = peak / float(model_flux)
    return out


def final_flags_summary(state, added, block=ROW_BLOCK):
    """An arm's final flags `protected_flags(FLAG, FLAG_ROW, added)` checked
    and summarised in row blocks (no full cube): `assert_preserved` on each
    block (both are row-local), the final flag fraction (exact count over
    cells, as `final.mean()`), FLAG_ROW unchanged, superset of the input."""
    original, rows = state["original_flags"], state["original_rows"]
    count = 0
    unchanged = True
    superset = True
    for s in row_blocks(len(rows), block):
        final, final_rows = protected_flags(
            original[s],
            rows[s],
            np.broadcast_to(added[s][..., None], original[s].shape),
        )
        assert_preserved(original[s], rows[s], final, final_rows)
        count += int(np.count_nonzero(final))
        unchanged &= bool(np.array_equal(final_rows, rows[s]))
        superset &= not np.any(original[s] & ~final)
    return {
        "final_flag_fraction": float(np.float64(count) / np.float64(original.size)),
        "flag_row_unchanged": bool(unchanged),
        "superset_of_original": bool(superset),
    }


def model_stokes_mean(model, weight, block=ROW_BLOCK):
    """`mean(Re(XX + YY) / 2)` of MODEL_DATA over imaged samples (`weight >
    0`), as `image_arm` computed it on the whole array: the selected float32
    values are gathered in row blocks into one vector (same values, same
    order), then averaged. Returns (mean or None, imaged count)."""
    count = int(np.count_nonzero(weight > 0))
    values = np.empty(count, np.float32)
    at = 0
    for s in row_blocks(len(weight), block):
        imaged = weight[s] > 0
        part = (np.real(model[s][..., 0] + model[s][..., 3]) * 0.5)[imaged]
        values[at : at + len(part)] = part
        at += len(part)
    return (float(values.mean()) if count else None), count


def image_arm(
    state, extra, solve, out_dir, label, image, groups, boxes=None, buffers=None
):
    """Corrected-data Stokes I dirty image of one arm. With `boxes=None` K's
    frozen metrics (9 x 9 and 64 x 64 boxes) are used, else the array's.
    `buffers` (sample, weight) are reused across arms when given."""
    started = time.perf_counter()
    sample, weight = corrected_stokes(state, solve, *(buffers or (None, None)))
    padded = core_weights.padded_size(image["width"], image["padding"])
    padded_h = core_weights.padded_size(image["height"], image["padding"])
    imaging = core_weights.imaging_weights(
        extra["uvw"],
        core_weights.wsclean_wavelengths(state["frequencies"]),
        weight,
        np.ones(len(weight), bool),
        mode="briggs",
        robust=core_campaign.ROBUST,
        width=padded,
        height=padded_h,
        pixel_scale=core_weights.pixel_scale_radians(image["scale_arcsec"]),
        return_grid=False,
    )
    weighted = time.perf_counter()
    products = grouped_invert(
        extra["uvw"],
        state["frequencies"],
        sample,
        weight,
        imaging["weights"],
        image,
        groups,
    )
    gridded = time.perf_counter()
    model_flux, imaged_cells = model_stokes_mean(state["model"], weight)
    del sample, weight, imaging["weights"]
    if boxes is None:
        metrics = core_campaign.image_metrics(
            products["dirty"], products["psf"], model_flux
        )
    else:
        if boxes == "measure":
            boxes = boxes_from_psf(products["psf"], image["width"])
        metrics = array_image_metrics(
            products["dirty"], products["psf"], boxes, model_flux
        )
        metrics["boxes_used"] = boxes
    metrics["imaged_cells"] = imaged_cells
    metrics["imaging_weight_sums"] = imaging["sums"]
    metrics["gridder"] = products["stats"]
    metrics["gridder_groups"] = products["groups"]
    header = core_grid.wcs_header(
        extra["phase_dir"],
        image["width"],
        image["height"],
        image["scale_arcsec"],
        state["frequencies"],
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = {
        "WSCVWSUM": products["stats"]["visibility_weight_sum"],
        "WSCIMGWG": products["stats"]["image_weight"],
        "WSCNORMF": products["stats"]["psf_normalization"],
        "WSCNVIS": products["stats"]["gridded_count"],
        "WSCNWLAY": products["stats"]["n_w_layers"],
        "WSCDATAC": "CORRECTED_DATA",
        "WSCWEIGH": f"Briggs'({core_campaign.ROBUST})",
        "RANGARM": label,
    }
    core_grid.write_fits(
        out_dir / f"{label}-dirty.fits", products["dirty"], header, keys
    )
    core_grid.write_fits(out_dir / f"{label}-psf.fits", products["psf"], header, keys)
    metrics["seconds"] = {
        "correct_and_weights": weighted - started,
        "grid": gridded - weighted,
        "total": time.perf_counter() - started,
    }
    metrics["dirty_sha256"] = array_sha256(products["dirty"])
    metrics["psf_sha256"] = array_sha256(products["psf"])
    return metrics, products


def valid_prediction(state, gain_valid, time_map, freq_map):
    """Samples whose two station gains are valid (the fused pass predicts them)."""
    p, q = state["antenna1"], state["antenna2"]
    t, f = time_map[:, None], freq_map[None]
    return gain_valid[t, f, p[:, None]] & gain_valid[t, f, q[:, None]]


def restricted_losses(state, solve, masks):
    """Fused-pass losses of `solve`'s gains on the given sample masks."""
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    fused = core.fused_pass(
        state["data"],
        state["weights"],
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
        solve["diagnostics"]["gains"],
        solve["diagnostics"]["gain_valid"],
        core.split_labels(**masks),
        model=state["model"],
        residuals=False,
        scores=False,
        normals=False,
    )
    losses = fused.losses()
    return {
        name: {
            "loss": losses[name],
            "cells": fused.split_stats[name]["cells"],
            "invalid": fused.split_stats[name]["invalid"],
        }
        for name in masks
    }


AMENDMENT_PAIRS = (
    ("tv-policy", "tricolour-firstpass"),
    ("tv-policy", "original"),
    ("tricolour-firstpass+tv", "tricolour-firstpass"),
    ("tricolour-firstpass+tv-a1", "tricolour-firstpass"),
)


def matched_calls(state, solves, arms):
    """Amendment 1: every arm's losses on its validly predicted samples, and
    each pair's call on the held-out samples both arms predict."""
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    ok = {
        label: valid_prediction(
            state, solve["diagnostics"]["gain_valid"], time_map, freq_map
        )
        for label, solve in solves.items()
        if solve is not None
    }
    per_arm = {
        label: restricted_losses(
            state,
            solves[label],
            {
                "train": state["train"] & mask,
                "validation": state["validation"] & mask,
                "test": state["test"] & mask,
            },
        )
        for label, mask in ok.items()
    }
    pairs = []
    for candidate, reference in AMENDMENT_PAIRS:
        if candidate not in ok or reference not in ok:
            pairs.append(
                {
                    "candidate": candidate,
                    "reference": reference,
                    "mse_test": {"ratio": None, "call": "undecidable"},
                    "residual_rms": {"ratio": None, "call": "undecidable"},
                    "mse_validation": {"ratio": None, "call": "undecidable"},
                }
            )
            continue
        both = ok[candidate] & ok[reference]
        masks = {"validation": state["validation"] & both, "test": state["test"] & both}
        lc = restricted_losses(state, solves[candidate], masks)
        lr = restricted_losses(state, solves[reference], masks)
        pairs.append(
            {
                "candidate": candidate,
                "reference": reference,
                "matched_test_cells": lc["test"]["cells"],
                "dropped_test_cells": int(np.count_nonzero(state["test"] & ~both)),
                "matched_validation_cells": lc["validation"]["cells"],
                "losses": {"candidate": lc, "reference": lr},
                "mse_test": call(lc["test"]["loss"], lr["test"]["loss"]),
                "mse_validation": call(
                    lc["validation"]["loss"], lr["validation"]["loss"]
                ),
                "residual_rms": call(
                    (arms.get(candidate) or {}).get("image", {}).get("residual_rms"),
                    (arms.get(reference) or {}).get("image", {}).get("residual_rms"),
                ),
            }
        )
    return {"arm_losses_valid_only": per_arm, "pairs": pairs}


def available_hypothesis(arms, candidate, reference):
    """K's `hypothesis`, undecidable when an arm is unavailable."""
    if arms.get(candidate) is None or arms.get(reference) is None:
        undecidable = {"ratio": None, "call": "undecidable"}
        return {
            "candidate": candidate,
            "reference": reference,
            "mse_test": undecidable,
            "residual_rms": undecidable,
            "mse_validation": undecidable,
            "additions": None,
        }
    return hypothesis(arms, candidate, reference)


# --- the campaign ------------------------------------------------------------


def run(
    run_dir,
    stations=None,
    image=None,
    groups=ARRAY_CHANNEL_GROUPS,
    k_metrics=False,
    group_check=False,
    precondition_dir=None,
    label="frozen",
):
    """The frozen L1 campaign. `stations=None` is the whole array; the
    precondition's replay passes K's stations, image settings, one group and
    `k_metrics=True`."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} exists; use a fresh run directory")
    run_dir.mkdir(parents=True)
    image = dict(ARRAY_IMAGE if image is None else image)
    core.library()
    available = mem_available_gib()
    before = {name: snapshot(ROOT / name) for name in ARCHIVED_INPUTS}
    status_before = git_status()
    wall = time.perf_counter()
    cpu0 = cpu_seconds()
    stages = Stages()

    # 1. Input integrity (nothing is fetched).
    mark = stages.start()
    integrity = verify_inputs()
    stages.stop("input_integrity", mark)
    if not (integrity["all_match_receipts"] and integrity["whole_tile_headers"]):
        write_json(run_dir / "integrity.json", integrity)
        raise RuntimeError("local inputs differ from the archived receipts")
    # 2. Decode.
    mark = stages.start()
    arrays, rows, decode_stats = decode_inputs(stations)
    extra = decode_extra(rows)
    stages.stop("decode", mark)
    nant = len(extra["antenna_names"]) if stations is None else max(stations) + 1
    # 3. State and split.
    mark = stages.start()
    state = build_state(arrays, extra, nant)
    del arrays
    stages.stop("split", mark)
    split_counts = {
        k: int(np.count_nonzero(state[k]))
        for k in ("eligible", "train", "validation", "test")
    }
    del state["eligible"]  # P5: not used after the split counts
    baselines = sorted(set(zip(state["antenna1"].tolist(), state["antenna2"].tolist())))
    stations_present = sorted(
        set(state["antenna1"].tolist()) | set(state["antenna2"].tolist())
    )
    solves, candidates, tricolour = {}, {}, {}
    # 4. Arms.
    mark = stages.start()
    zero = np.zeros_like(state["train"])
    original = solve_arm(state, zero, "original", features=True)
    scale0 = original["metrics"]["scale"]
    stages.stop("solve_original", mark)
    solves["original"] = strip(original)
    for arm_label, strategy in core_campaign.STRATEGIES.items():
        mark = stages.start()
        additions, summary = tricolour_arm(
            state, extra, core_campaign.STRATEGY_DIR / strategy
        )
        stages.stop(f"flag_{arm_label}", mark)
        mark = stages.start()
        firstpass = arm_label == "tricolour-firstpass"
        solve = solve_arm(state, additions, arm_label, scale=scale0, features=firstpass)
        stages.stop(f"solve_{arm_label}", mark)
        tricolour[arm_label] = summary
        solves[arm_label] = strip(solve)
        if firstpass:
            firstpass_base = solve
    unavailable = {}
    mark = stages.start()
    try:
        trials, best, unguided = tv_loop(state, original, scale0, "tv")
    except RuntimeError as error:  # no validation loss or TV support on the base
        trials, best, unguided = [{"error": str(error)}], None, None
        unavailable["tv-policy"] = str(error)
    stages.stop("tv_loop", mark)
    del original
    candidates["tv-policy"] = trials
    solves["tv-policy"] = (
        {**strip(best["solve"]), "label": "tv-policy", "policy": best["policy"]}
        if best is not None
        else None
    )
    solves["tv-unguided-best"] = (
        {
            **strip(unguided["solve"]),
            "label": "tv-unguided-best",
            "policy": unguided["policy"],
        }
        if unguided is not None
        else None
    )
    mark = stages.start()
    try:
        trials2, best2, _ = tv_loop(state, firstpass_base, scale0, "firstpass-tv")
    except RuntimeError as error:
        trials2, best2 = [{"error": str(error)}], None
        unavailable["tricolour-firstpass+tv"] = str(error)
    stages.stop("tv_loop_firstpass", mark)
    del firstpass_base
    candidates["tricolour-firstpass+tv"] = trials2
    solves["tricolour-firstpass+tv"] = (
        {
            **strip(best2["solve"]),
            "label": "tricolour-firstpass+tv",
            "policy": best2["policy"],
        }
        if best2 is not None
        else None
    )
    # Amendment 1: the first-pass loop on the validation samples its base
    # predicts; a candidate that loses any of them is inadmissible.
    mark = stages.start()
    amendment_loop = None
    if solves.get("tricolour-firstpass") is not None:
        time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
        fp = solves["tricolour-firstpass"]
        ok_fp = valid_prediction(
            state, fp["diagnostics"]["gain_valid"], time_map, freq_map
        )
        state_m = {**state, "validation": state["validation"] & ok_fp}
        base_m = solve_arm(
            state_m,
            additions_dense(state, fp["added"]),
            "tricolour-firstpass",
            scale=scale0,
            features=True,
        )
        amendment_loop = {
            "validation_samples": int(np.count_nonzero(state_m["validation"])),
            "dropped_validation_samples": int(
                np.count_nonzero(state["validation"] & ~ok_fp)
            ),
            "base_gains_equal_firstpass": bool(
                np.array_equal(
                    base_m["diagnostics"]["gains"], fp["diagnostics"]["gains"]
                )
            ),
            "base_losses": base_m["metrics"]["losses"],
        }
        del ok_fp
        try:
            trials3, best3, _ = tv_loop(state_m, base_m, scale0, "firstpass-tv-a1")
        except RuntimeError as error:
            trials3, best3 = [{"error": str(error)}], None
            unavailable["tricolour-firstpass+tv-a1"] = str(error)
        del base_m, state_m
        candidates["tricolour-firstpass+tv-a1"] = trials3
        solves["tricolour-firstpass+tv-a1"] = (
            {
                **strip(best3["solve"]),
                "label": "tricolour-firstpass+tv-a1",
                "policy": best3["policy"],
            }
            if best3 is not None
            else None
        )
    stages.stop("tv_loop_firstpass_a1", mark)
    # 5. Images; the boxes come from the `original` PSF (array mode).
    base_edges = solves["original"]["tv"]["edges"]
    boxes = None
    group_comparison = None
    arms = {}
    nrow, nchan = state["train"].shape
    buffers = (
        np.empty((nrow, nchan), np.complex64),
        np.empty((nrow, nchan), np.float32),
    )
    for arm_label, solve in solves.items():
        if solve is None:
            arms[arm_label] = None
            continue
        mark = stages.start()
        metrics, products = image_arm(
            state,
            extra,
            solve,
            run_dir / "images",
            arm_label,
            image,
            groups,
            boxes=None if k_metrics else (boxes if boxes is not None else "measure"),
            buffers=buffers,
        )
        if not k_metrics and boxes is None:
            boxes = metrics["boxes_used"]
        stages.stop(f"image_{arm_label}", mark)
        if group_check and arm_label == "original":
            mark = stages.start()
            sample, weight = corrected_stokes(state, solve)
            imaging = core_weights.imaging_weights(
                extra["uvw"],
                core_weights.wsclean_wavelengths(state["frequencies"]),
                weight,
                np.ones(len(weight), bool),
                mode="briggs",
                robust=core_campaign.ROBUST,
                width=core_weights.padded_size(image["width"], image["padding"]),
                height=core_weights.padded_size(image["height"], image["padding"]),
                pixel_scale=core_weights.pixel_scale_radians(image["scale_arcsec"]),
                return_grid=False,
            )
            other = grouped_invert(
                extra["uvw"],
                state["frequencies"],
                sample,
                weight,
                imaging["weights"],
                image,
                1 if groups != 1 else ARRAY_CHANNEL_GROUPS,
            )
            peak = float(np.abs(products["dirty"]).max())
            group_comparison = {
                "groups": [groups, 1 if groups != 1 else ARRAY_CHANNEL_GROUPS],
                "dirty_linf_over_peak": float(
                    np.abs(other["dirty"] - products["dirty"]).max() / peak
                ),
                "psf_linf": float(np.abs(other["psf"] - products["psf"]).max()),
                "tolerance": GROUP_TOLERANCE,
            }
            group_comparison["pass"] = bool(
                group_comparison["dirty_linf_over_peak"] <= GROUP_TOLERANCE
                and group_comparison["psf_linf"] <= GROUP_TOLERANCE
            )
            del sample, weight, imaging, other
            stages.stop("group_check", mark)
        del products
        added = additions_dense(state, solve["added"])
        final = final_flags_summary(state, added)
        arms[arm_label] = {
            "label": arm_label,
            "source": solve["label"],
            "policy": solve.get("policy"),
            "metrics": solve["metrics"],
            "fixed_support_tv_vs_original": fixed_support_tv(
                solve["tv"]["edges"], base_edges
            ),
            "additions": int(added.sum()),
            "additions_fraction_of_train": float(added.sum() / split_counts["train"]),
            "final_flag_fraction": final["final_flag_fraction"],
            "original_flag_fraction": float(state["original_flags"].mean()),
            "flag_row_unchanged": final["flag_row_unchanged"],
            "superset_of_original": final["superset_of_original"],
            "holdout_cells_added": int(np.count_nonzero(added & ~state["train"])),
            "additions_sha256": array_sha256(added),
            "gains_sha256": array_sha256(solve["diagnostics"]["gains"]),
            "image": metrics,
        }
        (run_dir / "flags").mkdir(exist_ok=True)
        (run_dir / "gains").mkdir(exist_ok=True)
        np.savez_compressed(run_dir / "flags" / f"{arm_label}.npz", additions=added)
        np.savez_compressed(
            run_dir / "gains" / f"{arm_label}.npz",
            gains=solve["diagnostics"]["gains"],
            gain_valid=solve["diagnostics"]["gain_valid"],
        )
    del buffers
    # Amendment 1: matched-sample calls.
    mark = stages.start()
    amendment = matched_calls(state, solves, arms)
    amendment["firstpass_loop"] = amendment_loop
    stages.stop("amendment_1_calls", mark)
    # 6. Hypotheses and the cost clause.
    hypotheses = [
        available_hypothesis(arms, "tv-policy", "tricolour-firstpass"),
        available_hypothesis(arms, "tv-policy", "original"),
        available_hypothesis(arms, "tricolour-firstpass+tv", "tricolour-firstpass"),
    ]
    rec = stages.records
    tv_chain = rec["solve_original"]["seconds"] + rec["tv_loop"]["seconds"]
    port = rec["flag_tricolour-firstpass"]["seconds"]
    cost = {
        "tv_chain_seconds": tv_chain,
        "tricolour_firstpass_seconds": port,
        "ratio": tv_chain / port,
        "limit_ratio": 3.0,
        "comparable": tv_chain <= 3.0 * port,
    }
    total = time.perf_counter() - wall
    after = {name: snapshot(ROOT / name) for name in ARCHIVED_INPUTS}
    lo, hi = CHANNELS
    result = {
        "protocol": "research/luno-array-campaign.md",
        "label": label,
        "caveats": "WEIGHT_SPECTRUM is a QuartiCal product; 1934-638 MODEL_DATA origin unlogged",
        "cells": {
            "group": GROUP,
            "row_chunk": 0,
            "field_id": extra["field_id"],
            "field_name": extra["field_name"],
            "scan_number": extra["scan_number"],
            "stations_requested": "all" if stations is None else list(stations),
            "nant": nant,
            "stations_with_rows": stations_present,
            "stations_without_rows": [
                extra["antenna_names"][i]
                for i in range(nant)
                if i not in stations_present
            ],
            "baselines": len(baselines),
            "integrations": len(np.unique(state["times"])),
            "channels": [lo, hi],
            "rows": len(rows),
            "rows_sha256": array_sha256(np.asarray(rows, np.int64)),
            "shape": list(state["data"].shape),
            "frequency_range_mhz": [
                float(state["frequencies"][0] / 1e6),
                float(state["frequencies"][-1] / 1e6),
            ],
        },
        "integrity": {k: v for k, v in integrity.items() if k != "objects"},
        "decode": decode_stats,
        "split": {"seed": core_campaign.SPLIT_SEED, "counts": split_counts},
        "tricolour": tricolour,
        "arms": arms,
        "unavailable": unavailable,
        "boxes": boxes,
        "group_comparison": group_comparison,
        "amendment_1": amendment,
        "hypotheses": hypotheses,
        "cost_clause": cost,
        "stages": rec,
        "wall_seconds": total,
        "cores_busy": (cpu_seconds() - cpu0) / total,
        "max_rss_mb": rss_mb(),
        "memory": {
            "available_gib_at_start": available,
            "required_gib_at_start": MIN_AVAILABLE_GIB,
            "budget_mb": MEMORY_BUDGET_MB,
            "within_budget": rss_mb() <= MEMORY_BUDGET_MB,
        },
        "settings": {
            "grid": core_campaign.GRID,
            "iterations": core_campaign.ITERATIONS,
            "thresholds": core_campaign.THRESHOLDS,
            "tv_weights": core_campaign.TV_WEIGHTS,
            "max_fraction": core_campaign.MAX_FRACTION,
            "flag_penalty": core_campaign.FLAG_PENALTY,
            "validation_weight": core_campaign.VALIDATION_WEIGHT,
            "validation_tolerance": core_campaign.VALIDATION_TOLERANCE,
            "image": image,
            "channel_groups": groups,
            "k_metrics": k_metrics,
            "robust": core_campaign.ROBUST,
            "decision_band": [core_campaign.BETTER, core_campaign.WORSE],
            "row_block": ROW_BLOCK,
        },
    }
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "candidates.json", candidates)
    write_json(run_dir / "integrity.json", integrity)
    receipt = {
        "inputs": "integrity.json",
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES},
        "library": str(core.library_path()),
        "library_sha256": file_sha256(core.library_path()),
        "backend": core.backend_name(),
        "strategies": {
            k: file_sha256(core_campaign.STRATEGY_DIR / v)
            for k, v in core_campaign.STRATEGIES.items()
        },
        "static_masks": {p.name: file_sha256(p) for p in core_flag.static_mask_files()},
        "settings": result["settings"],
        "seed": core_campaign.SPLIT_SEED,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "precondition_dir": str(precondition_dir) if precondition_dir else None,
    }
    write_json(run_dir / "receipt.json", receipt)
    audit = {
        "inputs": list(ARCHIVED_INPUTS),
        "input_files_checked": sum(len(v) for v in before.values()),
        "inputs_unchanged": before == after,
        "changed": [
            f"{name}/{k}"
            for name in ARCHIVED_INPUTS
            for k in set(before[name]) | set(after[name])
            if before[name].get(k) != after[name].get(k)
        ][:20],
        "git_status_unchanged": status_before == git_status(),
        "run_dir_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.iterdir()),
    }
    write_json(run_dir / "side-effects.json", audit)
    return result


# --- precondition ------------------------------------------------------------


def _load(path):
    return json.loads(Path(path).read_text())


def compare_replay(replay, k_result, k_candidates):
    """Exact equality of the four-station replay with K's frozen run -01."""
    out = {}
    out["shape"] = replay["cells"]["shape"] == k_result["cells"]["shape"]
    out["split_counts"] = replay["split"]["counts"] == k_result["split"]["counts"]
    arm_keys = (
        "additions_sha256",
        "gains_sha256",
        "fixed_support_tv_vs_original",
        "final_flag_fraction",
        "additions",
    )
    arms = {}
    for label, k_arm in k_result["arms"].items():
        arm = replay["arms"].get(label)
        if k_arm is None or arm is None:
            arms[label] = k_arm is None and arm is None
            continue
        same = {key: arm[key] == k_arm[key] for key in arm_keys}
        same["losses"] = arm["metrics"]["losses"] == k_arm["metrics"]["losses"]
        same["tv"] = arm["metrics"]["tv"] == k_arm["metrics"]["tv"]
        for key in ("dirty_sha256", "psf_sha256", "residual_rms", "peak_jy_per_beam"):
            same[f"image_{key}"] = arm["image"][key] == k_arm["image"][key]
        arms[label] = same
    out["arms"] = arms
    cand = {}
    for loop, k_trials in k_candidates.items():
        trials = {t["trial"]: t for t in replay.get("_candidates", {}).get(loop, [])}
        for k_trial in k_trials:
            mine = trials.get(k_trial["trial"], {})
            cand[k_trial["trial"]] = all(
                mine.get(key) == k_trial.get(key)
                for key in (
                    "mask_sha256",
                    "mask_count",
                    "objective",
                    "accepted",
                    "duplicate_mask",
                )
            )
    out["candidates"] = cand
    out["tricolour_newly_flagged"] = {
        k: replay["tricolour"][k]["newly_flagged_cells"] == v["newly_flagged_cells"]
        and replay["tricolour"][k]["additions_on_train"] == v["additions_on_train"]
        for k, v in k_result["tricolour"].items()
    }
    out["hypotheses"] = [
        (h["mse_test"], h["residual_rms"]) == (k["mse_test"], k["residual_rms"])
        for h, k in zip(replay["hypotheses"], k_result["hypotheses"])
    ]

    def flat(value):
        if isinstance(value, dict):
            return all(flat(v) for v in value.values())
        if isinstance(value, list):
            return all(flat(v) for v in value)
        return bool(value)

    out["all_equal"] = flat(out)
    return out


def precondition(out_dir):
    """The three gated parts of the protocol's precondition."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    stages = Stages()
    # 1. K's precondition, unedited, and the archive's numbers.
    mark = stages.start()
    k_pre = core_campaign.precondition(out_dir / "k-precondition")
    stages.stop("k_precondition", mark)
    archive = _load(K_ARCHIVE)
    sec6 = k_pre["section6"]
    arch6 = archive["section6_reference"]
    part1 = {
        "k_checks_all_passed": k_pre["all_passed"],
        "chi2_equals_archive": k_pre["checks"]["chi2"]
        == archive["precondition"]["chi2"],
        "max_product_difference_equals_archive": k_pre["checks"][
            "max_baseline_product_difference"
        ]
        == archive["precondition"]["max_baseline_product_difference"],
        "section6_equal_archive": {
            k: sec6[k] == arch6[k]
            for k in (
                "gains_sha256",
                "gain_flags_sha256",
                "chi2_train_mean_per_cell",
                "converged_fraction",
                "flagged_gain_fraction",
                "survey",
                "policy_mask_counts",
                "policy_mask_sha256",
            )
        },
    }
    part1["pass"] = bool(
        part1["k_checks_all_passed"]
        and part1["chi2_equals_archive"]
        and all(part1["section6_equal_archive"].values())
    )
    # 2-3. Four-station replay of K's run -01, and the gridder-group check.
    k_result_path = K_RUN / "result.json"
    k_hash_ok = file_sha256(k_result_path) == archive["result_sha256"]
    mark = stages.start()
    replay = run(
        out_dir / "replay",
        stations=core_campaign.STATIONS,
        image=core_campaign.IMAGE,
        groups=1,
        k_metrics=True,
        group_check=True,
        label="precondition replay of K run -01",
    )
    stages.stop("replay", mark)
    replay["_candidates"] = _load(out_dir / "replay" / "candidates.json")
    part2 = compare_replay(
        replay, _load(k_result_path), _load(K_RUN / "candidates.json")
    )
    part2["k_result_hash_matches_archive"] = k_hash_ok
    part2["pass"] = bool(part2["all_equal"] and k_hash_ok)
    part3 = replay["group_comparison"]
    passed = {
        "k_precondition": part1["pass"],
        "replay": part2["pass"],
        "groups": part3["pass"],
    }
    result = {
        "protocol": "research/luno-array-campaign.md",
        "stage": "precondition",
        "passed": passed,
        "all_passed": all(passed.values()),
        "k_precondition": part1,
        "replay": part2,
        "groups": part3,
        "replay_stages": replay["stages"],
        "stages": stages.records,
        "seconds": time.perf_counter() - started,
        "max_rss_mb": rss_mb(),
    }
    write_json(out_dir / "result.json", result)
    return result


# --- the checker -------------------------------------------------------------


def check(run_dir, precondition_dir, check_dir):
    """Criteria 1-7 of the protocol for one array run."""
    run_dir, precondition_dir, check_dir = (
        Path(run_dir),
        Path(precondition_dir),
        Path(check_dir),
    )
    check_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    result = _load(run_dir / "result.json")
    pre = _load(precondition_dir / "result.json")
    integrity = _load(run_dir / "integrity.json")
    criteria = {}
    # 1. Input integrity, re-hashed independently of the run.
    receipts = archived_receipts()
    rehashed = [verify_object(r["key"], receipts) for r in integrity["objects"]]
    same_as_run = all(
        a["sha256"] == b["sha256"] and a["bytes"] == b["bytes"]
        for a, b in zip(rehashed, integrity["objects"])
    )
    keys_complete = sorted(r["key"] for r in integrity["objects"]) == sorted(
        input_keys()
    )
    criteria["1_input_integrity"] = {
        "pass": all(r["ok"] for r in rehashed)
        and same_as_run
        and keys_complete
        and integrity["whole_tile_headers"]
        and integrity["fetched_bytes"] == 0,
        "objects": len(rehashed),
        "bytes_hashed": sum(r["bytes"] for r in rehashed),
        "mismatches": [r["key"] for r in rehashed if not r["ok"]][:10],
        "rehash_equals_run": same_as_run,
        "keys_complete": keys_complete,
        "whole_tile_headers": integrity["whole_tile_headers"],
        "fetched_bytes": integrity["fetched_bytes"],
    }
    # 2. Flags preserved and no side effects.
    audit = _load(run_dir / "side-effects.json")
    arms = {k: v for k, v in result["arms"].items() if v is not None}
    flag_ok = {
        label: arm["superset_of_original"]
        and arm["flag_row_unchanged"]
        and arm["holdout_cells_added"] == 0
        for label, arm in arms.items()
    }
    added_files = {}
    for label in arms:
        with np.load(run_dir / "flags" / f"{label}.npz") as stored:
            added_files[label] = (
                array_sha256(stored["additions"]) == arms[label]["additions_sha256"]
            )
    criteria["2_flags_preserved"] = {
        "pass": all(flag_ok.values())
        and all(added_files.values())
        and audit["inputs_unchanged"]
        and audit["git_status_unchanged"],
        "arms": flag_ok,
        "stored_additions_match": added_files,
        "inputs_unchanged": audit["inputs_unchanged"],
        "input_files_checked": audit["input_files_checked"],
        "git_status_unchanged": audit["git_status_unchanged"],
    }
    # 3. Precondition.
    criteria["3_precondition"] = {
        "pass": bool(pre["all_passed"]),
        "passed": pre["passed"],
    }
    # 4. Every arm solves.
    solved = {}
    for label, arm in arms.items():
        m = arm["metrics"]
        with np.load(run_dir / "gains" / f"{label}.npz") as stored:
            finite = bool(np.isfinite(stored["gains"][stored["gain_valid"]]).all())
        solved[label] = (
            m["solver"]["converged_fraction"] >= 0.9
            and finite
            and m["losses"]["validation"] is not None
            and m["losses"]["test"] is not None
            and all(v == 0 for v in m["invalid_predictions"].values())
        )
    criteria["4_arms_solve"] = {
        "pass": all(solved.values()),
        "arms": solved,
        "converged": {
            k: v["metrics"]["solver"]["converged_fraction"] for k, v in arms.items()
        },
        "unavailable": [k for k, v in result["arms"].items() if v is None],
    }
    # 5. Tricolour arms well formed.
    criteria["5_tricolour_well_formed"] = {
        "pass": all(t["checks"]["pass"] for t in result["tricolour"].values()),
        "checks": {
            k: {c: v for c, v in t["checks"].items() if c != "stage_fractions"}
            for k, t in result["tricolour"].items()
        },
    }

    # 6. Hypotheses (pass means decidable), recomputed from the arm numbers.
    def arm_value(label, *path):
        value = arms.get(label)
        for key in path:
            if value is None:
                return None
            value = value[key]
        return value

    recomputed = [
        {
            "mse_test": call(
                arm_value(h["candidate"], "metrics", "losses", "test"),
                arm_value(h["reference"], "metrics", "losses", "test"),
            ),
            "residual_rms": call(
                arm_value(h["candidate"], "image", "residual_rms"),
                arm_value(h["reference"], "image", "residual_rms"),
            ),
        }
        for h in result["hypotheses"]
    ]
    criteria["6_hypotheses"] = {
        "pass": all(
            h["mse_test"]["call"] != "undecidable" for h in result["hypotheses"]
        )
        and all(
            r["mse_test"] == h["mse_test"] and r["residual_rms"] == h["residual_rms"]
            for r, h in zip(recomputed, result["hypotheses"])
        ),
        "calls": result["hypotheses"],
        "headline": {
            "pair": "tv-policy vs tricolour-firstpass",
            "mse_test": result["hypotheses"][0]["mse_test"],
            "residual_rms": result["hypotheses"][0]["residual_rms"],
            "cost_comparable": result["cost_clause"]["comparable"],
            "cost_ratio": result["cost_clause"]["ratio"],
            "tv_policy_selected": arm_value("tv-policy", "policy"),
            "unavailable": result.get("unavailable"),
        },
    }
    # 7. Outputs.
    files = {
        p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()
    }
    required = {
        "result.json",
        "receipt.json",
        "side-effects.json",
        "candidates.json",
        "integrity.json",
    }
    required |= {f"flags/{k}.npz" for k in arms} | {f"gains/{k}.npz" for k in arms}
    required |= {f"images/{k}-dirty.fits" for k in arms} | {
        f"images/{k}-psf.fits" for k in arms
    }
    missing = sorted(required - files)
    criteria["7_outputs"] = {
        "pass": not missing and (run_dir / "environment.json").exists(),
        "missing": missing,
        "environment_json": (run_dir / "environment.json").exists(),
    }
    summary = {
        "protocol": "research/luno-array-campaign.md",
        "run": str(run_dir),
        "precondition": str(precondition_dir),
        "all_pass": all(c["pass"] for c in criteria.values()),
        "criteria": criteria,
        "memory": result["memory"],
        "check_seconds": time.perf_counter() - started,
    }
    write_json(check_dir / "result.json", summary)
    return summary


__all__ = [
    "array_image_metrics",
    "baseline_scores",
    "boxes_from_psf",
    "build_state",
    "check",
    "compare_replay",
    "corrected_stokes",
    "decode_extra",
    "decode_inputs",
    "grouped_invert",
    "precondition",
    "psf_fwhm",
    "residual_amplitude",
    "run",
    "solve_arm",
    "tricolour_arm",
    "tv_loop",
    "verify_inputs",
]
