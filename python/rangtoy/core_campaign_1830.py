"""The LUNO PKS 1830-211 campaign on the core (research/luno-1830-campaign.md).

Task L2 of research/big-plan.md: the whole-array campaign of task L1
(`rangtoy.core_campaign_array`) on the gain calibrator PKS 1830-211
(`MAIN/MAIN_2`, scan 3, the whole 80 s scan), under two model arms:

- `stored`: MODEL_DATA as stored, with its ~1e-3 cross-hand terms;
- `scalar`: an unpolarised point source at the FIELD phase direction with a
  power-law spectrum fitted to the short-baseline Stokes I data, predicted by
  the core predictor (`core.predict_components`).

The campaign functions of L1 and K are imported unedited. What L1 hardcodes
for 1934-638 (the zarr group, the input roots, the model column, four
gridder groups) is parameterised here by wrapping: integrity, decode and
`run()` take the group, the roots and the model arm. The DATA and UVW of
MAIN_2 are fetched whole from the RATT bucket; everything else is archived.

Original FLAG and FLAG_ROW are never modified.
"""

import json
import math
import platform
import time
from pathlib import Path

import numpy as np

from . import core, core_campaign, core_fetch, core_flag, core_zarr
from . import core_campaign_array as array
from .core_campaign import (
    array_sha256,
    call,
    file_sha256,
    git_status,
    rss_mb,
    snapshot,
    write_json,
)
from .core_campaign_array import (
    Stages,
    archived_receipts,
    available_hypothesis,
    compare_replay,
    cpu_seconds,
    image_arm,
    matched_calls,
    mem_available_gib,
    resolve,
    solve_arm,
    strip,
    tricolour_arm,
    tv_loop,
    valid_prediction,
    verify_object,
)
from .core_workflow import gain_grid
from .flagging import assert_preserved, fixed_support_tv, protected_flags

ROOT = core_campaign.ROOT
BUCKET = core_campaign.BUCKET
GROUP = "MAIN/MAIN_2"
K_GROUP = core_campaign.GROUP
TILES = core_campaign.TILES
CHANNELS = core_campaign.CHANNELS
SUPPORT = core_campaign.SUPPORT
SOLVE_INPUTS = core_campaign.SOLVE_INPUTS
MODEL_ARMS = ("stored", "scalar")
# The 19 fetched objects and their sizes from the pre-protocol probe
# (outputs/l2-1830-20261030-00-probe/probe.json), frozen in the protocol.
EXPECTED_SIZES = {
    "MAIN/MAIN_2/DATA/.zarray": 369,
    "MAIN/MAIN_2/DATA/0.8.0": 54898275,
    "MAIN/MAIN_2/DATA/0.9.0": 54330026,
    "MAIN/MAIN_2/DATA/0.10.0": 54755838,
    "MAIN/MAIN_2/DATA/0.11.0": 55919146,
    "MAIN/MAIN_2/DATA/0.12.0": 56014546,
    "MAIN/MAIN_2/DATA/0.13.0": 56087141,
    "MAIN/MAIN_2/DATA/0.14.0": 55161638,
    "MAIN/MAIN_2/DATA/0.15.0": 56522829,
    "MAIN/MAIN_2/DATA/0.16.0": 55062009,
    "MAIN/MAIN_2/DATA/0.17.0": 54041500,
    "MAIN/MAIN_2/DATA/0.18.0": 54061693,
    "MAIN/MAIN_2/DATA/0.19.0": 54049152,
    "MAIN/MAIN_2/DATA/0.20.0": 54008186,
    "MAIN/MAIN_2/DATA/0.21.0": 54002248,
    "MAIN/MAIN_2/DATA/0.22.0": 53985119,
    "MAIN/MAIN_2/DATA/0.23.0": 53994504,
    "MAIN/MAIN_2/UVW/.zarray": 342,
    "MAIN/MAIN_2/UVW/0.0": 305897,
}
FETCH_KEYS = tuple(EXPECTED_SIZES)
NU0 = 1.284e9
SHORT_BASELINE_M = 200.0
MIN_TILE_SAMPLES = 1000
MIN_FIT_TILES = 6
PREDICT_TOLERANCE = 1e-12
IMAGE_TOLERANCE = 1e-9
CHANNEL_GROUPS = 1
MIN_AVAILABLE_GIB = 12
MEMORY_BUDGET_MB = 10_000
SURVEY_STATIONS = (0, 1, 2, 3)
SURVEY_CUTOFF = 1e-10
LENGTH_BANDS = ((0, 200), (200, 1000), (1000, 3000), (3000, 9000))
SUPPORT_ARCHIVE = ROOT / "research/results/meerkat-luno-support.json"
ARCHIVED_SURVEY_GROUP2 = {
    "train_cells": 47409,
    "bins_with_train": 160,
    "fully_identified": 0,
    "underidentified": 15,
    "over_rank": 145,
    "no_train": 160,
    "status": {"over_rank status6": 145, "underidentified status6": 15},
}
CODE_FILES = (*array.CODE_FILES, "python/rangtoy/core_campaign_1830.py")


# --- fetch -------------------------------------------------------------------


def fetch(out, bucket=BUCKET, keys=FETCH_KEYS):
    """Whole GETs of the MAIN_2 DATA and UVW objects into `out/objects`.

    Writes `receipt-extra.json` (K's per-request records), `objects/receipt.txt`
    (`bytes sha256 key`, the archived receipt format, so the fetch directory
    is one more resolver root) and `result.json`."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists; use a fresh output directory")
    out.mkdir(parents=True)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary = core_campaign.fetch_extra(bucket, out, keys)
    records = json.loads((out / "receipt-extra.json").read_text())
    lines = []
    objects = []
    for record in records:
        path = out / "objects" / record["key"]
        on_disk = file_sha256(path)
        lines.append(f"{record['bytes']} {record['sha256']} {record['key']}")
        objects.append(
            {
                "key": record["key"],
                "status": record["status"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
                "seconds": record["seconds"],
                "attempts": len(record["attempts"]),
                "expected_bytes": EXPECTED_SIZES.get(record["key"]),
                "file_sha256_matches": on_disk == record["sha256"],
                "etag": record["headers"].get("ETag"),
                "last_modified": record["headers"].get("Last-Modified"),
            }
        )
    (out / "objects" / "receipt.txt").write_text("\n".join(lines) + "\n")
    result = {
        "protocol": "research/luno-1830-campaign.md",
        "base_url": bucket,
        "started_utc": started_utc,
        **summary,
        "objects": objects,
        "keys_complete": sorted(r["key"] for r in records) == sorted(keys),
        "all_status_200": all(o["status"] == 200 for o in objects),
        "sizes_match_probe": all(o["bytes"] == o["expected_bytes"] for o in objects),
        "hashes_match_files": all(o["file_sha256_matches"] for o in objects),
        "expected_bytes": sum(EXPECTED_SIZES[k] for k in keys),
    }
    write_json(out / "result.json", result)
    return result


def roots_for(group, fetch_dir=None):
    """Resolver roots: the fetch (if any), the support slice, the solve inputs."""
    if group == K_GROUP:
        return array.ROOTS
    if fetch_dir is None:
        return (SUPPORT, SOLVE_INPUTS)
    return (Path(fetch_dir) / "objects", SUPPORT, SOLVE_INPUTS)


# --- integrity and decode (L1's, parameterised by group and roots) -----------


def extra_keys(group):
    return [k.replace(K_GROUP, group) for k in array.EXTRA_KEYS]


def tile_keys(group, columns=core_fetch.TILE_COLUMNS, tiles=TILES):
    return [f"{group}/{name}/0.{tile}.0" for name in columns for tile in tiles]


def input_keys(group, columns=core_fetch.TILE_COLUMNS):
    keys = []
    for name, _ in core_fetch.ROW_COLUMNS:
        keys += [f"{group}/{name}/.zarray", f"{group}/{name}/0"]
    for name in columns:
        keys.append(f"{group}/{name}/.zarray")
    return keys + tile_keys(group, columns) + extra_keys(group)


def verify_inputs(group, roots, fetched=None, columns=core_fetch.TILE_COLUMNS):
    """Criterion 1: every object read equals its receipt line, whole tiles."""
    receipts = archived_receipts(roots)
    started = time.perf_counter()
    records = [
        verify_object(key, receipts, roots) for key in input_keys(group, columns)
    ]
    headers = {}
    for name in columns:
        meta = core_zarr.array_meta(resolve(f"{group}/{name}", roots))
        whole = int(np.prod(meta["chunks"])) * np.dtype(meta["dtype"]).itemsize
        for tile in TILES:
            with open(resolve(f"{group}/{name}/0.{tile}.0", roots), "rb") as stream:
                nbytes = core_zarr.header_fields(stream.read(core_fetch.HEADER))[0]
            headers[f"{name}/0.{tile}.0"] = [int(nbytes), whole]
    return {
        "group": group,
        "roots": [str(r) for r in roots],
        "objects": records,
        "all_match_receipts": all(r["ok"] for r in records),
        "bytes_hashed": sum(r["bytes"] for r in records),
        "whole_tile_headers": all(a == b for a, b in headers.values()),
        "tile_nbytes": headers,
        "fetched_bytes": 0 if fetched is None else fetched["bytes"],
        "fetched_requests": 0 if fetched is None else fetched["requests"],
        "fetched_seconds": 0.0 if fetched is None else fetched["seconds"],
        "seconds": time.perf_counter() - started,
    }


def decode_row_columns(group, roots):
    arrays = {}
    for name, dtype in core_fetch.ROW_COLUMNS:
        payload = resolve(f"{group}/{name}/0", roots).read_bytes()
        arrays[name] = np.ascontiguousarray(
            np.frombuffer(core.blosc_decode(payload), dtype)
        )
    return arrays


def decode_inputs(group, roots, stations=None, columns=core_fetch.TILE_COLUMNS):
    """L1's `decode_inputs` for `group`: kept rows, tiles into preallocated arrays."""
    started = time.perf_counter()
    row_arrays = decode_row_columns(group, roots)
    nant_total = int(max(row_arrays["ANTENNA1"].max(), row_arrays["ANTENNA2"].max()))
    stations = list(range(nant_total + 1)) if stations is None else list(stations)
    rows = core_fetch.kept_rows(row_arrays, stations)
    arrays = {k: np.ascontiguousarray(v[rows]) for k, v in row_arrays.items()}
    stats = {"blocks_decoded": 0, "blocks_total": 0, "bytes_read": 0}
    lo, hi = CHANNELS
    for name in columns:
        meta = core_zarr.array_meta(resolve(f"{group}/{name}", roots))
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        dtype = np.dtype(meta["dtype"])
        row_bytes = nchan * ncorr * dtype.itemsize
        out = np.empty((len(rows), hi - lo, ncorr), dtype)
        for tile in TILES:
            raw, tile_stats = core_zarr.read_rows(
                resolve(f"{group}/{name}/0.{tile}.0", roots), row_bytes, rows
            )
            first = tile * nchan - lo
            out[:, first : first + nchan] = np.frombuffer(raw, dtype).reshape(
                len(rows), nchan, ncorr
            )
            del raw
            for k in stats:
                stats[k] += tile_stats[k]
        arrays[name] = out
    stats["seconds"] = time.perf_counter() - started
    return arrays, rows, stats


def decode_extra(group, rows, roots, channels=CHANNELS):
    """L1's `decode_extra` for `group`."""

    def obj(key, chunk):
        return core_campaign.decode_object(
            resolve(key, roots).parent, key.split("/")[-1], chunk
        )

    attrs = json.loads(resolve(f"{group}/.zattrs", roots).read_text())
    field = int(attrs["FIELD_ID"])
    lo, hi = channels
    uvw = obj(f"{group}/UVW", "0.0")
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


# --- the model arms ----------------------------------------------------------


def eligibility(arrays):
    """`build_state`'s eligible samples (L1), without building the state."""
    flags = np.asarray(arrays["FLAG"], bool)
    rows = np.asarray(arrays["FLAG_ROW"], bool)
    protected, _ = protected_flags(flags, rows, np.zeros_like(flags))
    eligible = ~protected.any(axis=-1)
    del protected
    p, q = arrays["ANTENNA1"], arrays["ANTENNA2"]
    eligible &= (p != q)[:, None]
    eligible &= np.isfinite(arrays["DATA"]).all(axis=-1)
    eligible &= np.isfinite(arrays["WEIGHT_SPECTRUM"]).all(axis=-1)
    eligible &= (arrays["WEIGHT_SPECTRUM"] > 0).all(axis=-1)
    eligible &= np.isfinite(arrays["MODEL_DATA"]).all(axis=-1)
    return eligible


def fit_power_law(data, eligible, uvw, frequencies, tile_width=128):
    """The frozen flux rule: per-tile median |0.5 (XX + YY)| on eligible samples
    of rows shorter than SHORT_BASELINE_M, and a least-squares line in log-log
    about NU0. Returns I0 (Jy at NU0), alpha and the per-tile record."""
    short = np.hypot(uvw[:, 0], uvw[:, 1]) < SHORT_BASELINE_M
    data_short = data[short]
    ok_short = eligible[short]
    tiles = []
    for t, lo in enumerate(range(0, data.shape[1], tile_width)):
        hi = lo + tile_width
        ok = ok_short[:, lo:hi]
        count = int(ok.sum())
        stokes = 0.5 * (data_short[:, lo:hi, 0] + data_short[:, lo:hi, 3])
        median = float(np.median(np.abs(stokes[ok]))) if count else None
        tiles.append(
            {
                "tile": int(TILES[0] + t),
                "frequency_hz": float(np.mean(frequencies[lo:hi])),
                "samples": count,
                "median_abs_stokes_i": median,
                "used": count >= MIN_TILE_SAMPLES,
            }
        )
    used = [t for t in tiles if t["used"]]
    if len(used) < 2:
        raise RuntimeError("fewer than two tiles with short-baseline support")
    x = np.log(np.array([t["frequency_hz"] for t in used]) / NU0)
    y = np.log(np.array([t["median_abs_stokes_i"] for t in used]))
    alpha, intercept = np.polyfit(x, y, 1)
    fitted = intercept + alpha * x
    return {
        "i0_jy": float(np.exp(intercept)),
        "alpha": float(alpha),
        "nu0_hz": NU0,
        "short_baseline_m": SHORT_BASELINE_M,
        "short_rows": int(short.sum()),
        "min_tile_samples": MIN_TILE_SAMPLES,
        "tiles_used": len(used),
        "log_rms_residual": float(np.sqrt(np.mean((y - fitted) ** 2))),
        "tiles": tiles,
    }


def predict_scalar(uvw, frequencies, i0, alpha):
    """The core predictor's point source at the phase centre, as XX = YY = S."""
    started = time.perf_counter()
    vis = core.predict_components(
        uvw,
        frequencies,
        np.zeros((1, 2)),
        np.zeros(1, np.uint8),
        np.array([i0]),
        np.array([[alpha]]),
        np.ones(1, bool),
        np.array([NU0]),
        np.zeros((1, 3)),
    )
    seconds = time.perf_counter() - started
    expected = i0 * (frequencies / NU0) ** alpha
    relative = float(np.max(np.abs(vis - expected[None, :])) / np.max(expected))
    check = {
        "max_relative_deviation_from_power_law": relative,
        "max_abs_imaginary": float(np.max(np.abs(vis.imag))),
        "tolerance": PREDICT_TOLERANCE,
        "seconds": seconds,
    }
    check["pass"] = bool(relative <= PREDICT_TOLERANCE)
    model = np.zeros((*vis.shape, 4), np.complex64)
    model[..., 0] = vis
    model[..., 3] = vis
    del vis
    return model, check


def model_diagnostic(model, uvw, eligible):
    """Model Stokes I by baseline length on eligible samples."""
    length = np.hypot(uvw[:, 0], uvw[:, 1])
    stokes = 0.5 * (model[..., 0] + model[..., 3])
    out = {}
    for lo, hi in LENGTH_BANDS:
        sel = (length >= lo) & (length < hi)
        values = stokes[sel][eligible[sel]]
        if values.size:
            out[f"{lo}-{hi} m"] = {
                "rows": int(sel.sum()),
                "samples": int(values.size),
                "median_abs_I": float(np.median(np.abs(values))),
                "mean_re_I": float(np.mean(values.real)),
            }
    xx = np.abs(model[..., 0][eligible])
    out["median_abs_xy_over_xx"] = float(
        np.median(np.abs(model[..., 1][eligible]) / np.maximum(xx, 1e-30))
    )
    out["median_abs_yx_over_xx"] = float(
        np.median(np.abs(model[..., 2][eligible]) / np.maximum(xx, 1e-30))
    )
    return out


def apply_model_arm(arrays, extra, model_arm, fit=None):
    """Replace MODEL_DATA for the scalar arm; returns the model record.

    The fit uses the stored arm's eligibility, so both arms fit and split the
    same samples. With `fit` given (the survey's four-station rows) the
    whole-array fit is reused."""
    if model_arm not in MODEL_ARMS:
        raise ValueError(f"unknown model arm {model_arm}")
    started = time.perf_counter()
    eligible = eligibility(arrays)
    record = {
        "arm": model_arm,
        "stored_diagnostic": model_diagnostic(
            arrays["MODEL_DATA"], extra["uvw"], eligible
        ),
    }
    if model_arm == "scalar":
        if fit is None:
            fit = fit_power_law(
                arrays["DATA"], eligible, extra["uvw"], extra["chan_freq"]
            )
        model, check = predict_scalar(
            extra["uvw"], extra["chan_freq"], fit["i0_jy"], fit["alpha"]
        )
        record["fit"] = fit
        record["predictor_check"] = check
        record["stored_short_median_abs_I_per_tile"] = _short_tile_medians(
            arrays["MODEL_DATA"], eligible, extra["uvw"]
        )
        arrays["MODEL_DATA"] = model
        record["diagnostic"] = model_diagnostic(model, extra["uvw"], eligible)
    else:
        record["diagnostic"] = record["stored_diagnostic"]
    record["seconds"] = time.perf_counter() - started
    return record


def _short_tile_medians(model, eligible, uvw, tile_width=128):
    short = np.hypot(uvw[:, 0], uvw[:, 1]) < SHORT_BASELINE_M
    out = {}
    for t, lo in enumerate(range(0, model.shape[1], tile_width)):
        m = model[short, lo : lo + tile_width]
        ok = eligible[short, lo : lo + tile_width]
        i = np.abs(0.5 * (m[..., 0] + m[..., 3]))[ok]
        out[str(TILES[0] + t)] = float(np.median(i)) if i.size else None
    return out


# --- the four-station identifiability survey ---------------------------------


def survey(arrays, gains=None, gain_valid=None, grid=core_campaign.GRID):
    """The support survey (flagging-luno-support.md) on four-station rows.

    TRAIN cells as the support survey: no correlation flagged, all four
    weights positive, the model finite (rows have FLAG_ROW false). `gains`
    (ntime, nfreq, >=4, 2, 2) with `gain_valid` gives the solved-gain point;
    None gives identity. Native status from anchored_response(H, 0, 0, 0)."""
    from .flagging_influence import anchored_response, training_normals

    p_all, q_all = arrays["ANTENNA1"], arrays["ANTENNA2"]
    if np.any(p_all >= 4) or np.any(q_all >= 4):
        raise ValueError("the native survey normals are four-station")
    flag, weight, model = (
        arrays["FLAG"],
        arrays["WEIGHT_SPECTRUM"],
        arrays["MODEL_DATA"],
    )
    integration = np.searchsorted(np.unique(arrays["TIME"]), arrays["TIME"])
    ntime = int(integration.max()) // grid[0] + 1
    nfreq = flag.shape[1] // grid[1]
    nbins = ntime * nfreq
    train = ~flag.any(-1) & (weight > 0).all(-1) & np.isfinite(model).all(-1)
    rows, channels = np.nonzero(train)
    bins = (integration[rows] // grid[0]) * nfreq + channels // grid[1]
    p, q = p_all[rows], q_all[rows]
    if gains is None:
        flat = np.ascontiguousarray(
            np.broadcast_to(np.eye(2), (nbins, 4, 2, 2)).astype(np.complex128)
        )
        flagged = np.zeros((nbins, 4), bool)
        point = "identity"
    else:
        g = np.asarray(gains)[:, :, :4]
        if g.shape[:2] != (ntime, nfreq):
            raise ValueError(f"gain grid {g.shape} does not match the survey")
        flat = np.ascontiguousarray(g.reshape(nbins, 4, 2, 2).astype(np.complex128))
        flagged = ~np.asarray(gain_valid)[:, :, :4].reshape(nbins, 4)
        point = "solved"
    h, _, counts = training_normals(
        np.where(np.isfinite(flat), flat, 0),
        model[rows, channels].astype(np.complex128).reshape(-1, 2, 2),
        np.zeros((len(rows), 2, 2), np.complex128),
        weight[rows, channels].astype(np.float64),
        p,
        q,
        bins,
    )
    out = {
        "point": point,
        "bins": nbins,
        "train_cells": int(train.sum()),
        "bins_with_train": 0,
        "fully_identified": 0,
        "underidentified": 0,
        "over_rank": 0,
        "no_train": 0,
        "no_solved_gain": 0,
        "cells": {"fully_identified": 0, "underidentified": 0, "over_rank": 0},
        "status": {},
        "failures": [],
    }
    order = np.argsort(bins, kind="stable")
    sorted_bins = bins[order]
    zero = np.zeros(32)
    for k in range(nbins):
        if not counts[k]:
            out["no_train"] += 1
            continue
        out["bins_with_train"] += 1
        lo, hi = np.searchsorted(sorted_bins, [k, k + 1])
        sel = order[lo:hi]
        active = np.zeros(4, bool)
        active[p[sel]] = True
        active[q[sel]] = True
        if flagged[k, active].any():
            out["no_solved_gain"] += 1
            out["failures"].append({"bin": int(k), "label": "no_solved_gain"})
            continue
        eig = np.linalg.eigvalsh(h[k])
        rank = int(np.sum(eig > SURVEY_CUTOFF * eig[-1])) if eig[-1] > 0 else 0
        required = 8 * int(active.sum()) - 4
        label = (
            "fully_identified"
            if rank == required
            else ("underidentified" if rank < required else "over_rank")
        )
        out[label] += 1
        out["cells"][label] += int(counts[k])
        status = anchored_response(h[k], zero, 0 * h[k], zero, flat[k], active)[
            "native_status"
        ]
        key = f"{label} status{status}"
        out["status"][key] = out["status"].get(key, 0) + 1
        if label != "fully_identified":
            edges = sorted({(int(x), int(y)) for x, y in zip(p[sel], q[sel])})
            out["failures"].append(
                {
                    "bin": int(k),
                    "label": label,
                    "status": int(status),
                    "cells": int(counts[k]),
                    "active": np.flatnonzero(active).tolist(),
                    "edges": edges,
                    "rank": rank,
                    "required": required,
                }
            )
    return out


def survey_matches_archive(result):
    keys = ("train_cells", "bins_with_train", "fully_identified", "underidentified")
    keys += ("over_rank", "no_train", "status")
    return {k: result[k] == ARCHIVED_SURVEY_GROUP2[k] for k in keys}


def survey_arm(group, roots, model_arm, fit, solve=None):
    """Four-station survey of `group` under the model arm, at identity and at
    the arm's solved gains (stations 0-3 of the whole-array solve)."""
    started = time.perf_counter()
    columns = ("MODEL_DATA", "FLAG", "WEIGHT_SPECTRUM")
    arrays, rows, _ = decode_inputs(group, roots, SURVEY_STATIONS, columns)
    if model_arm == "scalar":
        extra = decode_extra(group, rows, roots)
        model, _ = predict_scalar(
            extra["uvw"], extra["chan_freq"], fit["i0_jy"], fit["alpha"]
        )
        arrays["MODEL_DATA"] = model
    out = {
        "stations": list(SURVEY_STATIONS),
        "rows": len(rows),
        "model_arm": model_arm,
        "identity": survey(arrays),
    }
    if solve is not None:
        out["solved"] = survey(
            arrays, solve["diagnostics"]["gains"], solve["diagnostics"]["gain_valid"]
        )
    out["seconds"] = time.perf_counter() - started
    return out


# --- the campaign ------------------------------------------------------------


def derived_row_flags(original_flags, original_rows, added):
    """The derived row flag and the two clauses of criterion 2."""
    final, final_rows = protected_flags(
        original_flags,
        original_rows,
        np.broadcast_to(np.asarray(added)[..., None], original_flags.shape),
    )
    expected = original_rows | final.all(axis=(1, 2))
    return (
        final,
        final_rows,
        {
            "derived_rows": int(final_rows.sum()),
            "input_flag_rows": int(original_rows.sum()),
            "equals_flag_row_or_all_flagged": bool(
                np.array_equal(final_rows, expected)
            ),
            "equals_input_flag_row": bool(np.array_equal(final_rows, original_rows)),
        },
    )


def run(
    run_dir,
    model_arm,
    fetch_dir=None,
    group=GROUP,
    stations=None,
    image=None,
    groups=CHANNEL_GROUPS,
    k_metrics=False,
    precondition_dir=None,
    label="frozen",
    with_survey=True,
):
    """The frozen L2 campaign for one model arm (L1's `run` with the group,
    roots and model as parameters). The precondition's replay passes K's
    group, stations and image settings with `k_metrics=True`."""
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise FileExistsError(f"{run_dir} exists; use a fresh run directory")
    run_dir.mkdir(parents=True)
    image = dict(array.ARRAY_IMAGE if image is None else image)
    roots = roots_for(group, fetch_dir)
    fetched = None
    if fetch_dir is not None and group != K_GROUP:
        fetched = json.loads((Path(fetch_dir) / "result.json").read_text())
    watched = list(array.ARCHIVED_INPUTS)
    if fetch_dir is not None:
        path = Path(fetch_dir)
        watched.append(str(path.relative_to(ROOT) if path.is_absolute() else path))
    core.library()
    available = mem_available_gib()
    before = {name: snapshot(ROOT / name) for name in watched}
    status_before = git_status()
    wall = time.perf_counter()
    cpu0 = cpu_seconds()
    stages = Stages()

    # 1. Input integrity.
    mark = stages.start()
    integrity = verify_inputs(group, roots, fetched)
    stages.stop("input_integrity", mark)
    if not (integrity["all_match_receipts"] and integrity["whole_tile_headers"]):
        write_json(run_dir / "integrity.json", integrity)
        raise RuntimeError("inputs differ from their receipts")
    # 2. Decode.
    mark = stages.start()
    arrays, rows, decode_stats = decode_inputs(group, roots, stations)
    extra = decode_extra(group, rows, roots)
    stages.stop("decode", mark)
    nant = len(extra["antenna_names"]) if stations is None else max(stations) + 1
    # 3. Model arm.
    mark = stages.start()
    model_record = apply_model_arm(arrays, extra, model_arm)
    stages.stop("model", mark)
    # 4. State and split.
    mark = stages.start()
    state = array.build_state(arrays, extra, nant)
    del arrays
    stages.stop("split", mark)
    split_counts = {
        k: int(np.count_nonzero(state[k]))
        for k in ("eligible", "train", "validation", "test")
    }
    split_sha256 = {
        k: array_sha256(state[k]) for k in ("eligible", "train", "validation", "test")
    }
    baselines = sorted(set(zip(state["antenna1"].tolist(), state["antenna2"].tolist())))
    stations_present = sorted(
        set(state["antenna1"].tolist()) | set(state["antenna2"].tolist())
    )
    solves, candidates, tricolour, unavailable = {}, {}, {}, {}
    # 5. Arms.
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
        summary["additions_sha256"] = array_sha256(additions)
        mark = stages.start()
        firstpass = arm_label == "tricolour-firstpass"
        solve = solve_arm(state, additions, arm_label, scale=scale0, features=firstpass)
        stages.stop(f"solve_{arm_label}", mark)
        tricolour[arm_label] = summary
        solves[arm_label] = strip(solve)
        if firstpass:
            firstpass_base = solve
    mark = stages.start()
    try:
        trials, best, unguided = tv_loop(state, original, scale0, "tv")
    except RuntimeError as error:
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
    # Amendment 1 of L1, adopted from the start.
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
            state_m, fp["added"], "tricolour-firstpass", scale=scale0, features=True
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
    # 6. Images; boxes from the `original` PSF.
    base_edges = solves["original"]["tv"]["edges"]
    boxes = None
    arms = {}
    model_i = 0.5 * (state["model"][..., 0] + state["model"][..., 3])
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
        )
        del products
        if not k_metrics and boxes is None:
            boxes = metrics["boxes_used"]
        added = solve["added"]
        final, final_rows, row_clause = derived_row_flags(
            state["original_flags"], state["original_rows"], added
        )
        assert_preserved(
            state["original_flags"], state["original_rows"], final, final_rows
        )
        # Denominator set: samples unflagged in the arm's final flags with
        # positive weights (image_arm's own set also drops invalid gains).
        imaged = ~final.any(-1) & (state["weights"] > 0).all(-1)
        abs_flux = float(np.mean(np.abs(model_i[imaged]))) if imaged.any() else None
        re_flux = float(np.mean(model_i[imaged].real)) if imaged.any() else None
        metrics["flux_recovery_denominators"] = {
            "set": "final-unflagged samples with positive weights",
            "mean_re_model_i": re_flux,
            "mean_abs_model_i": abs_flux,
            "recovery_re": metrics["peak_jy_per_beam"] / re_flux if re_flux else None,
            "recovery_abs": metrics["peak_jy_per_beam"] / abs_flux
            if abs_flux
            else None,
        }
        stages.stop(f"image_{arm_label}", mark)
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
            "final_flag_fraction": float(final.mean()),
            "original_flag_fraction": float(state["original_flags"].mean()),
            "flag_row_unchanged": row_clause["equals_input_flag_row"],
            "row_flag_clause": row_clause,
            "superset_of_original": bool(not np.any(state["original_flags"] & ~final)),
            "holdout_cells_added": int(np.count_nonzero(added & ~state["train"])),
            "additions_sha256": array_sha256(added),
            "gains_sha256": array_sha256(solve["diagnostics"]["gains"]),
            "image": metrics,
        }
        del final, final_rows
        (run_dir / "flags").mkdir(exist_ok=True)
        (run_dir / "gains").mkdir(exist_ok=True)
        np.savez_compressed(run_dir / "flags" / f"{arm_label}.npz", additions=added)
        np.savez_compressed(
            run_dir / "gains" / f"{arm_label}.npz",
            gains=solve["diagnostics"]["gains"],
            gain_valid=solve["diagnostics"]["gain_valid"],
        )
    del model_i
    mark = stages.start()
    amendment = matched_calls(state, solves, arms)
    amendment["firstpass_loop"] = amendment_loop
    stages.stop("amendment_1_calls", mark)
    hypotheses = [
        available_hypothesis(arms, "tv-policy", "tricolour-firstpass"),
        available_hypothesis(arms, "tv-policy", "original"),
        available_hypothesis(arms, "tricolour-firstpass+tv", "tricolour-firstpass"),
    ]
    # 7. The four-station survey under this model.
    survey_result = None
    if with_survey:
        mark = stages.start()
        survey_result = survey_arm(
            group, roots, model_arm, model_record.get("fit"), solves["original"]
        )
        stages.stop("survey", mark)
        write_json(run_dir / "survey.json", survey_result)
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
    after = {name: snapshot(ROOT / name) for name in watched}
    lo, hi = CHANNELS
    result = {
        "protocol": "research/luno-1830-campaign.md",
        "label": label,
        "model_arm": model_arm,
        "caveats": (
            "WEIGHT_SPECTRUM is a QuartiCal product; MODEL_DATA origin unlogged; "
            "the scalar arm's flux is a gain-amplitude gauge, not a flux scale"
        ),
        "cells": {
            "group": group,
            "row_chunk": 0,
            "field_id": extra["field_id"],
            "field_name": extra["field_name"],
            "scan_number": extra["scan_number"],
            "stations_requested": "all" if stations is None else list(stations),
            "nant": nant,
            "stations_with_rows": stations_present,
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
        "model": model_record,
        "split": {
            "seed": core_campaign.SPLIT_SEED,
            "counts": split_counts,
            "sha256": split_sha256,
        },
        "tricolour": tricolour,
        "arms": arms,
        "unavailable": unavailable,
        "boxes": boxes,
        "amendment_1": amendment,
        "hypotheses": hypotheses,
        "survey": None
        if survey_result is None
        else {
            k: {kk: vv for kk, vv in v.items() if kk != "failures"}
            if isinstance(v, dict)
            else v
            for k, v in survey_result.items()
        },
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
            "row_block": array.ROW_BLOCK,
            "nu0_hz": NU0,
            "short_baseline_m": SHORT_BASELINE_M,
        },
    }
    write_json(run_dir / "result.json", result)
    write_json(run_dir / "candidates.json", candidates)
    write_json(run_dir / "integrity.json", integrity)
    receipt = {
        "inputs": "integrity.json",
        "fetch_dir": None if fetch_dir is None else str(fetch_dir),
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
        "inputs": watched,
        "input_files_checked": sum(len(v) for v in before.values()),
        "inputs_unchanged": before == after,
        "changed": [
            f"{name}/{k}"
            for name in watched
            for k in set(before[name]) | set(after[name])
            if before[name].get(k) != after[name].get(k)
        ][:20],
        "git_status_unchanged": status_before == git_status(),
        "run_dir_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.iterdir()),
    }
    write_json(run_dir / "side-effects.json", audit)
    return result


# --- precondition ------------------------------------------------------------


IMAGE_KEYS = ("image_dirty_sha256", "image_psf_sha256")
TOLERANT_KEYS = ("image_residual_rms", "image_peak_jy_per_beam")


def compare_replay_tolerant(replay, k_result, k_candidates):
    """L1's `compare_replay` with the P2 exemption: image hashes are reported,
    the peak and residual RMS agree within IMAGE_TOLERANCE relative."""
    out = compare_replay(replay, k_result, k_candidates)
    exempt = {}
    for label, same in out["arms"].items():
        if not isinstance(same, dict):
            continue
        arm, k_arm = replay["arms"][label], k_result["arms"][label]
        record = {key: same.pop(key) for key in IMAGE_KEYS}
        for key in TOLERANT_KEYS:
            name = key.removeprefix("image_")
            a, b = arm["image"][name], k_arm["image"][name]
            relative = abs(a - b) / max(abs(b), 1e-300)
            same[key] = relative <= IMAGE_TOLERANCE
            record[f"{name}_relative_difference"] = relative
        exempt[label] = record
    out["image_hashes_reported"] = exempt
    # The residual-RMS call is an image product: its verdict must be equal
    # and its ratio within IMAGE_TOLERANCE; the MSE calls stay exact.
    hypotheses = []
    for h, k in zip(replay["hypotheses"], k_result["hypotheses"]):
        a, b = h["residual_rms"], k["residual_rms"]
        ratio_ok = (a["ratio"] is None and b["ratio"] is None) or (
            a["ratio"] is not None
            and b["ratio"] is not None
            and abs(a["ratio"] - b["ratio"]) <= IMAGE_TOLERANCE * abs(b["ratio"])
        )
        hypotheses.append(
            h["mse_test"] == k["mse_test"] and a["call"] == b["call"] and ratio_ok
        )
    out["hypotheses"] = hypotheses

    def flat(value):
        if isinstance(value, dict):
            return all(flat(v) for v in value.values())
        if isinstance(value, list):
            return all(flat(v) for v in value)
        return bool(value)

    out["all_equal"] = flat(
        {
            k: v
            for k, v in out.items()
            if k not in ("all_equal", "image_hashes_reported")
        }
    )
    return out


def precondition(out_dir):
    """The three gated parts of the protocol's precondition."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    stages = Stages()
    # 1. K's precondition, unedited, and the archive's numbers (L1's part 1).
    mark = stages.start()
    k_pre = core_campaign.precondition(out_dir / "k-precondition")
    stages.stop("k_precondition", mark)
    archive = json.loads(array.K_ARCHIVE.read_text())
    sec6 = k_pre["section6"]
    arch6 = archive["section6_reference"]
    part1 = {
        "k_checks_all_passed": k_pre["all_passed"],
        "chi2_equals_archive": k_pre["checks"]["chi2"]
        == archive["precondition"]["chi2"],
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
    # 2. The L2 driver replays K's run -01 on MAIN_1.
    k_result_path = array.K_RUN / "result.json"
    k_hash_ok = file_sha256(k_result_path) == archive["result_sha256"]
    mark = stages.start()
    replay = run(
        out_dir / "replay",
        "stored",
        group=K_GROUP,
        stations=core_campaign.STATIONS,
        image=core_campaign.IMAGE,
        groups=1,
        k_metrics=True,
        label="precondition replay of K run -01",
        with_survey=False,
    )
    stages.stop("replay", mark)
    replay["_candidates"] = json.loads(
        (out_dir / "replay" / "candidates.json").read_text()
    )
    part2 = compare_replay_tolerant(
        replay,
        json.loads(k_result_path.read_text()),
        json.loads((array.K_RUN / "candidates.json").read_text()),
    )
    part2["k_result_hash_matches_archive"] = k_hash_ok
    part2["pass"] = bool(part2["all_equal"] and k_hash_ok)
    # 3. The survey code reproduces the archived MAIN_2 survey.
    mark = stages.start()
    roots = roots_for(GROUP)
    arrays, rows, _ = decode_inputs(
        GROUP, roots, SURVEY_STATIONS, ("MODEL_DATA", "FLAG", "WEIGHT_SPECTRUM")
    )
    identity = survey(arrays)
    stages.stop("survey", mark)
    matches = survey_matches_archive(identity)
    part3 = {
        "survey": identity,
        "matches": matches,
        "rows": len(rows),
        "pass": all(matches.values()),
    }
    passed = {
        "k_precondition": part1["pass"],
        "replay": part2["pass"],
        "survey": part3["pass"],
    }
    result = {
        "protocol": "research/luno-1830-campaign.md",
        "stage": "precondition",
        "passed": passed,
        "all_passed": all(passed.values()),
        "k_precondition": part1,
        "replay": part2,
        "survey": part3,
        "replay_stages": replay["stages"],
        "stages": stages.records,
        "seconds": time.perf_counter() - started,
        "max_rss_mb": rss_mb(),
    }
    write_json(out_dir / "result.json", result)
    return result


# --- the checker and the verdict ---------------------------------------------


def headline(result):
    """The per-model headline: the matched-sample MSE_test call of tv-policy
    vs tricolour-firstpass, with the primary call and the residual RMS."""
    primary = result["hypotheses"][0]
    matched = next(
        p
        for p in result["amendment_1"]["pairs"]
        if p["candidate"] == "tv-policy" and p["reference"] == "tricolour-firstpass"
    )
    return {
        "primary_mse_test": primary["mse_test"],
        "matched_mse_test": matched["mse_test"],
        "dropped_test_samples": matched.get("dropped_test_cells"),
        "residual_rms": primary["residual_rms"],
        "cost_comparable": result["cost_clause"]["comparable"],
        "cost_ratio": result["cost_clause"]["ratio"],
        "tv_policy_selected": (result["arms"].get("tv-policy") or {}).get("policy"),
    }


def verdict(headlines):
    """The pre-registered L2 verdict from the per-model headlines."""
    calls = {arm: h["matched_mse_test"]["call"] for arm, h in headlines.items()}
    decided = {arm: c for arm, c in calls.items() if c != "undecidable"}
    if not decided:
        return {"verdict": "undecidable", "calls": calls}
    values = set(decided.values())
    one_model = len(decided) < len(calls)
    if len(values) > 1:
        out = "model-dependent (not established)"
    else:
        value = values.pop()
        if value == "better":
            ok = all(
                headlines[a]["residual_rms"]["call"] != "worse"
                and headlines[a]["cost_comparable"]
                for a in decided
            )
            out = "positive" if ok else "not established (residual or cost)"
        elif value == "worse":
            out = "TV worse"
        else:
            out = "null"
    return {
        "verdict": out,
        "calls": calls,
        "rests_on_one_model": one_model,
    }


def check(run_dirs, precondition_dir, fetch_dir, check_dir):
    """The protocol's criteria 1-8 for the two model-arm runs."""
    check_dir = Path(check_dir)
    check_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    pre = json.loads((Path(precondition_dir) / "result.json").read_text())
    fetched = json.loads((Path(fetch_dir) / "result.json").read_text())
    roots = roots_for(GROUP, fetch_dir)
    receipts = archived_receipts(roots)
    per_arm = {}
    results = {}
    for model_arm, run_dir in run_dirs.items():
        run_dir = Path(run_dir)
        result = json.loads((run_dir / "result.json").read_text())
        results[model_arm] = result
        integrity = json.loads((run_dir / "integrity.json").read_text())
        crit = {}
        rehashed = [
            verify_object(r["key"], receipts, roots) for r in integrity["objects"]
        ]
        same = all(
            a["sha256"] == b["sha256"] and a["bytes"] == b["bytes"]
            for a, b in zip(rehashed, integrity["objects"])
        )
        fetch_ok = (
            fetched["keys_complete"]
            and fetched["all_status_200"]
            and fetched["sizes_match_probe"]
            and fetched["hashes_match_files"]
            and fetched["bytes"] == fetched["expected_bytes"]
        )
        crit["1_input_integrity"] = {
            "pass": bool(
                all(r["ok"] for r in rehashed)
                and same
                and sorted(r["key"] for r in integrity["objects"])
                == sorted(input_keys(GROUP))
                and integrity["whole_tile_headers"]
                and fetch_ok
            ),
            "objects": len(rehashed),
            "bytes_hashed": sum(r["bytes"] for r in rehashed),
            "fetch_ok": fetch_ok,
            "fetched_bytes": fetched["bytes"],
            "fetched_seconds": fetched["seconds"],
            "mismatches": [r["key"] for r in rehashed if not r["ok"]][:10],
        }
        audit = json.loads((run_dir / "side-effects.json").read_text())
        arms = {k: v for k, v in result["arms"].items() if v is not None}
        flag_ok = {
            label: arm["superset_of_original"]
            and arm["row_flag_clause"]["equals_flag_row_or_all_flagged"]
            and arm["holdout_cells_added"] == 0
            for label, arm in arms.items()
        }
        stored_ok = {}
        for label in arms:
            with np.load(run_dir / "flags" / f"{label}.npz") as stored:
                stored_ok[label] = (
                    array_sha256(stored["additions"]) == arms[label]["additions_sha256"]
                )
        crit["2_flags_preserved"] = {
            "pass": bool(
                all(flag_ok.values())
                and all(stored_ok.values())
                and audit["inputs_unchanged"]
                and audit["git_status_unchanged"]
            ),
            "arms": flag_ok,
            "derived_rows": {
                k: v["row_flag_clause"]["derived_rows"] for k, v in arms.items()
            },
            "l1_literal_clause_equals_input_flag_row": {
                k: v["row_flag_clause"]["equals_input_flag_row"]
                for k, v in arms.items()
            },
            "stored_additions_match": stored_ok,
            "inputs_unchanged": audit["inputs_unchanged"],
            "input_files_checked": audit["input_files_checked"],
            "git_status_unchanged": audit["git_status_unchanged"],
        }
        solved = {}
        for label, arm in arms.items():
            m = arm["metrics"]
            with np.load(run_dir / "gains" / f"{label}.npz") as stored:
                finite = bool(np.isfinite(stored["gains"][stored["gain_valid"]]).all())
            solved[label] = bool(
                m["solver"]["converged_fraction"] >= 0.9
                and finite
                and m["losses"]["validation"] is not None
                and m["losses"]["test"] is not None
                and all(v == 0 for v in m["invalid_predictions"].values())
            )
        crit["4_arms_solve"] = {
            "pass": all(solved.values()) and not result["unavailable"],
            "arms": solved,
            "converged": {
                k: v["metrics"]["solver"]["converged_fraction"] for k, v in arms.items()
            },
            "invalid_predictions": {
                k: v["metrics"]["invalid_predictions"] for k, v in arms.items()
            },
            "unavailable": [k for k, v in result["arms"].items() if v is None],
        }
        crit["5_tricolour_well_formed"] = {
            "pass": all(t["checks"]["pass"] for t in result["tricolour"].values()),
            "checks": {
                k: {c: v for c, v in t["checks"].items() if c != "stage_fractions"}
                for k, t in result["tricolour"].items()
            },
        }

        def value(label, *path, arms=arms):
            v = arms.get(label)
            for key in path:
                if v is None:
                    return None
                v = v[key]
            return v

        recomputed = [
            {
                "mse_test": call(
                    value(h["candidate"], "metrics", "losses", "test"),
                    value(h["reference"], "metrics", "losses", "test"),
                ),
                "residual_rms": call(
                    value(h["candidate"], "image", "residual_rms"),
                    value(h["reference"], "image", "residual_rms"),
                ),
            }
            for h in result["hypotheses"]
        ]
        crit["6_hypotheses"] = {
            "pass": bool(
                all(
                    h["mse_test"]["call"] != "undecidable" for h in result["hypotheses"]
                )
                and all(
                    r["mse_test"] == h["mse_test"]
                    and r["residual_rms"] == h["residual_rms"]
                    for r, h in zip(recomputed, result["hypotheses"])
                )
            ),
            "recomputed_equal": all(
                r["mse_test"] == h["mse_test"]
                and r["residual_rms"] == h["residual_rms"]
                for r, h in zip(recomputed, result["hypotheses"])
            ),
            "calls": result["hypotheses"],
            "matched": [
                {
                    "candidate": p["candidate"],
                    "reference": p["reference"],
                    "mse_test": p["mse_test"],
                    "residual_rms": p["residual_rms"],
                    "dropped_test_cells": p.get("dropped_test_cells"),
                }
                for p in result["amendment_1"]["pairs"]
            ],
            "headline": headline(result),
        }
        files = {
            p.relative_to(run_dir).as_posix() for p in run_dir.rglob("*") if p.is_file()
        }
        required = {
            "result.json",
            "receipt.json",
            "side-effects.json",
            "candidates.json",
            "integrity.json",
            "survey.json",
            "environment.json",
        }
        required |= {f"flags/{k}.npz" for k in arms} | {f"gains/{k}.npz" for k in arms}
        required |= {f"images/{k}-dirty.fits" for k in arms}
        required |= {f"images/{k}-psf.fits" for k in arms}
        missing = sorted(required - files)
        crit["8_outputs"] = {"pass": not missing, "missing": missing}
        per_arm[model_arm] = crit
    # Across model arms.
    across = {}
    across["3_precondition"] = {
        "pass": bool(pre["all_passed"]),
        "passed": pre["passed"],
    }
    tri = {
        k: {a: results[a]["tricolour"][k]["additions_sha256"] for a in results}
        for k in core_campaign.STRATEGIES
    }
    across["5_tricolour_identical_across_models"] = {
        "pass": all(len(set(v.values())) == 1 for v in tri.values()),
        "additions_sha256": tri,
    }
    scalar = results.get("scalar", {}).get("model", {})
    fit = scalar.get("fit") or {}
    splits = {a: results[a]["split"]["sha256"] for a in results}
    across["7_model_arms_well_formed"] = {
        "pass": bool(
            scalar.get("predictor_check", {}).get("pass")
            and fit.get("tiles_used", 0) >= MIN_FIT_TILES
            and fit.get("i0_jy") is not None
            and math.isfinite(fit["i0_jy"])
            and fit["i0_jy"] > 0
            and len({json.dumps(v, sort_keys=True) for v in splits.values()}) == 1
        ),
        "fit": {k: v for k, v in fit.items() if k != "tiles"},
        "predictor_check": scalar.get("predictor_check"),
        "split_sha256": splits,
    }
    headlines = {a: per_arm[a]["6_hypotheses"]["headline"] for a in per_arm}
    summary = {
        "protocol": "research/luno-1830-campaign.md",
        "runs": {k: str(v) for k, v in run_dirs.items()},
        "precondition": str(precondition_dir),
        "fetch": str(fetch_dir),
        "per_model_arm": per_arm,
        "across_model_arms": across,
        "all_pass": all(c["pass"] for crit in per_arm.values() for c in crit.values())
        and all(c["pass"] for c in across.values()),
        "verdict": verdict(headlines),
        "headlines": headlines,
        "memory": {a: results[a]["memory"] for a in results},
        "max_rss_mb": {a: results[a]["max_rss_mb"] for a in results},
        "check_seconds": time.perf_counter() - started,
    }
    write_json(check_dir / "result.json", summary)
    return summary


__all__ = [
    "apply_model_arm",
    "check",
    "compare_replay_tolerant",
    "decode_extra",
    "decode_inputs",
    "derived_row_flags",
    "eligibility",
    "fetch",
    "fit_power_law",
    "headline",
    "precondition",
    "predict_scalar",
    "run",
    "survey",
    "survey_arm",
    "verdict",
    "verify_inputs",
]
