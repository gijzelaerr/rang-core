"""Big plan task P5 (research/p5-memory.md): every lean replacement equals
the code it replaces on the same cells. Synthetic and offline, except the
decode checks on the archived K fetch, which are skipped when it is absent.
"""

import ctypes
import json
from pathlib import Path

import numpy as np
import pytest
from rangtoy import core, core_campaign, core_fetch, core_flag, core_zarr
from rangtoy import core_campaign_array as array
from rangtoy.core_policy import (
    gain_tv,
    polar_gauge,
    policy_mask,
    protected_flags,
    split_holdout,
)
from rangtoy.core_workflow import gain_grid, solve_flags

# Task G's archived fetch of the four-station slice (K's fetch held the same
# bytes and has since been deleted, big-plan.md "User items").
K_FETCH = next(
    (
        p
        for p in (
            core_campaign.ROOT / "outputs/core-k-20261030-01/fetch",
            core_campaign.ROOT / "outputs/core-g-20261029-01",
        )
        if (p / "result.json").exists()
    ),
    core_campaign.ROOT / "outputs/core-g-20261029-01",
)


def _synthetic(seed=3, nchan=64, ntime=6, nant=5):
    rng = np.random.default_rng(seed)
    pairs = [(p, q) for p in range(nant) for q in range(p + 1, nant)]
    a1 = np.array([p for _ in range(ntime) for p, _ in pairs], np.int32)
    a2 = np.array([q for _ in range(ntime) for _, q in pairs], np.int32)
    times = np.repeat(np.arange(ntime, dtype=float), len(pairs))
    nrow = len(times)
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 10.0
    data = model + (
        (rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)) * 0.05
    ).astype(np.complex64)
    data[3, 10] += 0.8
    data[7, 40:44] += 0.5
    data[11, 5:9] *= 1.3
    weights = rng.uniform(1.0, 3.0, model.shape).astype(np.float32)
    flags = rng.random(model.shape) < 0.05
    flags[0, :4] = True
    flag_row = np.zeros(nrow, bool)
    flag_row[9] = True
    arrays = {
        "DATA": data,
        "MODEL_DATA": model,
        "WEIGHT_SPECTRUM": weights,
        "FLAG": flags,
        "FLAG_ROW": flag_row,
        "ANTENNA1": a1,
        "ANTENNA2": a2,
        "TIME": times,
    }
    extra = {
        "antenna_names": [f"m{i:03d}" for i in range(nant)],
        "chan_freq": 1.3e9 + 1e6 * np.arange(nchan),
    }
    return arrays, extra


def _state(**kwargs):
    arrays, extra = _synthetic(**kwargs)
    return array.build_state(arrays, extra, nant=len(extra["antenna_names"]))


@pytest.mark.parametrize("block", [1, 3, 7, 10**6])
def test_split_holdout_lean_equals_split_holdout(block):
    rng = np.random.default_rng(5)
    eligible = rng.random((37, 23)) < 0.6
    rows = np.arange(37)
    groups = (rows[:, None] // 4) * 10 + np.arange(23)[None] // 5
    expected = split_holdout(eligible, 7, groups=groups)
    mine = array.split_holdout_lean(eligible, 7, lambda s: groups[s], block=block)
    for a, b in zip(mine, expected):
        assert a.dtype == bool and np.array_equal(a, b)
    for minimum in (1, 3):
        expected = split_holdout(eligible, 11, groups=groups, minimum_train=minimum)
        mine = array.split_holdout_lean(
            eligible, 11, lambda s: groups[s], minimum_train=minimum, block=block
        )
        assert all(np.array_equal(a, b) for a, b in zip(mine, expected))


def test_build_state_equals_the_dense_eligibility_and_split():
    arrays, extra = _synthetic()
    nant = len(extra["antenna_names"])
    state = array.build_state(arrays, extra, nant=nant)
    protected, _ = protected_flags(
        arrays["FLAG"], arrays["FLAG_ROW"], np.zeros_like(arrays["FLAG"])
    )
    p, q = arrays["ANTENNA1"], arrays["ANTENNA2"]
    eligible = (
        ~protected.any(axis=-1)
        & (p != q)[:, None]
        & np.isfinite(arrays["DATA"]).all(axis=-1)
        & np.isfinite(arrays["WEIGHT_SPECTRUM"]).all(axis=-1)
        & (arrays["WEIGHT_SPECTRUM"] > 0).all(axis=-1)
        & np.isfinite(arrays["MODEL_DATA"]).all(axis=-1)
    )
    time_bins = np.unique(arrays["TIME"], return_inverse=True)[1] // 2
    freq_bins = np.arange(arrays["DATA"].shape[1]) // 32
    groups = (
        time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]
    ) * nant**2 + (p * nant + q)[:, None]
    expected = split_holdout(eligible, core_campaign.SPLIT_SEED, groups=groups)
    assert np.array_equal(state["eligible"], eligible)
    for key, value in zip(("train", "validation", "test"), expected):
        assert np.array_equal(state[key], value)


def test_solve_flags_lean_equals_solve_flags():
    state = _state()
    added = state["train"] & (np.arange(state["train"].shape[1]) % 5 == 0)
    flags, rows = array.solve_flags_lean(state, added, block=4)
    expected_flags, expected_rows = solve_flags(state, added)
    assert np.array_equal(flags, expected_flags)
    assert np.array_equal(rows, expected_rows)


def _dense_features(state, solve):
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    gains, valid = solve["diagnostics"]["gains"], solve["diagnostics"]["gain_valid"]
    labels = core.split_labels(
        train=state["train"], validation=state["validation"], test=state["test"]
    )
    amplitude = array.residual_amplitude(
        state, gains, valid, labels, time_map, freq_map
    )
    outliers = array.baseline_scores(
        amplitude, state["train"], state["antenna1"], state["antenna2"]
    )
    return outliers, time_map, freq_map


def test_sparse_policy_mask_equals_policy_mask_on_random_features():
    rng = np.random.default_rng(9)
    shape = (40, 30)
    train = rng.random(shape) < 0.7
    outliers = np.where(train, np.maximum(rng.normal(0, 2.0, shape), 0), 0)
    guidance = rng.exponential(1.0, shape)
    guidance[rng.random(shape) < 0.1] = 0
    guidance[0, :3] = [np.nan, np.inf, -1.0]
    positive = guidance[train & np.isfinite(guidance) & (guidance > 0)]
    cells = np.flatnonzero(train & (outliers >= 2))
    features = {
        "cells": cells,
        "outliers": outliers.reshape(-1)[cells],
        "guidance": guidance.reshape(-1)[cells],
        "guidance_scale": np.median(positive),
        "eligible_count": int(train.sum()),
    }
    for max_fraction in (0.02, 0.005, 0.0):
        for tv_weight in (0.0, 1.0, 3.0):
            for threshold in (8.0, 5.0, 3.0, 2.5):
                kw = {
                    "threshold": threshold,
                    "tv_weight": tv_weight,
                    "max_fraction": max_fraction,
                }
                expected = policy_mask(outliers, guidance, train, **kw)
                mine = array.sparse_policy_mask(features, shape, **kw)
                assert np.array_equal(mine, expected), kw
    with pytest.raises(ValueError):
        array.sparse_policy_mask(
            features, shape, threshold=0, tv_weight=0, max_fraction=0
        )


def test_fused_features_equal_the_numpy_path_and_policy_masks():
    state = _state()
    base = array.solve_arm(state, np.zeros_like(state["train"]), "o", features=True)
    outliers, time_map, freq_map = _dense_features(state, base)
    gains, valid = base["diagnostics"]["gains"], base["diagnostics"]["gain_valid"]
    # Several baseline groups (6 rows each) against one group of every row.
    many = array.fused_candidates(state, gains, valid, time_map, freq_map, 6)
    one = array.fused_candidates(state, gains, valid, time_map, freq_map, 10**6)
    assert np.array_equal(many[0], one[0]) and np.array_equal(many[1], one[1])
    _, _, gt, gf = gain_grid(state, *core_campaign.GRID)
    aligned, tv_valid = polar_gauge(gains, valid)
    maps = gain_tv(aligned, tv_valid, gt, gf, scale=base["metrics"]["scale"])["map"]
    numpy_features = array.solve_features(
        state, gains, valid, time_map, freq_map, maps, scores="numpy"
    )
    assert np.array_equal(base["features"]["cells"], numpy_features["cells"])
    assert np.allclose(
        base["features"]["outliers"], numpy_features["outliers"], rtol=0, atol=1e-12
    )
    p, q = state["antenna1"], state["antenna2"]
    guidance = np.maximum(
        maps[time_map[:, None], freq_map[None], p[:, None]],
        maps[time_map[:, None], freq_map[None], q[:, None]],
    )
    assert len(base["features"]["cells"]) > 0
    for tv_weight in core_campaign.TV_WEIGHTS:
        for threshold in (*core_campaign.THRESHOLDS, 2.0):
            kw = {
                "threshold": threshold,
                "tv_weight": tv_weight,
                "max_fraction": core_campaign.MAX_FRACTION,
            }
            expected = policy_mask(outliers, guidance, state["train"], **kw)
            assert np.array_equal(
                array.sparse_policy_mask(numpy_features, outliers.shape, **kw), expected
            )
            assert np.array_equal(
                array.sparse_policy_mask(base["features"], outliers.shape, **kw),
                expected,
            )


def test_correct_stokes_i_equals_the_numpy_reference():
    state = _state()
    state["data"][5, 3, 0] = np.nan
    state["weights"][6, 4, 3] = np.nan
    solve = array.solve_arm(state, np.zeros_like(state["train"]), "o")
    gains = solve["diagnostics"]["gains"].copy()
    valid = solve["diagnostics"]["gain_valid"].copy()
    valid[1, 0, 2] = False
    added = state["train"] & (np.arange(state["train"].shape[1]) % 7 == 0)
    for a in (None, added):
        sample, weight = array.correct_stokes_i(state, gains, valid, a)
        ref_sample, ref_weight, _, _ = array.corrected_stokes_reference(
            state, gains, valid, a, block=4
        )
        assert np.array_equal(weight, ref_weight, equal_nan=True)
        assert np.array_equal(sample, ref_sample)
    # Into reused buffers, and through a solve's stored additions.
    buffers = (
        np.full(added.shape, np.nan, np.complex64),
        np.full(added.shape, np.nan, np.float32),
    )
    stored = {
        "added": np.flatnonzero(added),
        "diagnostics": {"gains": gains, "gain_valid": valid},
    }
    sample, weight = array.corrected_stokes(state, stored, *buffers)
    assert sample is buffers[0] and weight is buffers[1]
    ref_sample, ref_weight, _, _ = array.corrected_stokes_reference(
        state, gains, valid, added
    )
    assert np.array_equal(sample, ref_sample)
    assert np.array_equal(weight, ref_weight, equal_nan=True)


def test_final_flags_summary_and_model_mean_equal_the_dense_forms():
    state = _state()
    added = state["train"] & (np.arange(state["train"].shape[1]) % 3 == 0)
    final, final_rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.broadcast_to(added[..., None], state["original_flags"].shape),
    )
    summary = array.final_flags_summary(state, added, block=5)
    assert summary == {
        "final_flag_fraction": float(final.mean()),
        "flag_row_unchanged": bool(np.array_equal(final_rows, state["original_rows"])),
        "superset_of_original": bool(not np.any(state["original_flags"] & ~final)),
    }
    weight = np.where(added, 0, 1.5).astype(np.float32)
    model_i = np.real(state["model"][..., 0] + state["model"][..., 3]) * 0.5
    mean, count = array.model_stokes_mean(state["model"], weight, block=4)
    assert count == int((weight > 0).sum())
    assert mean == float(model_i[weight > 0].mean())


def test_additions_round_trip():
    state = _state()
    added = state["train"] & (np.arange(state["train"].shape[1]) % 4 == 1)
    assert np.array_equal(array.additions_dense(state, np.flatnonzero(added)), added)


def test_flag_rows_returns_bool_views():
    arrays, extra = _synthetic(nchan=16, ntime=4)
    nrow = len(arrays["TIME"])
    result = core_flag.flag_rows(
        arrays["DATA"],
        arrays["FLAG"],
        arrays["ANTENNA1"],
        arrays["ANTENNA2"],
        arrays["TIME"],
        np.array([[5109e3 + 10 * i, 2006e3, -3239e3] for i in range(5)]),
        extra["chan_freq"],
        np.full(16, 1e6),
        np.array([9, 10, 11, 12], np.int32),
        core_flag.parse_strategy(
            "strategies:\n  - name: nans\n    task: flag_nans_zeros\n"
            "  - name: combine\n    task: combine_with_input_flags\n"
        ),
        want_intensity=False,
    )
    flags = result["flags"]
    assert flags.dtype == bool and flags.base is not None
    assert flags.shape == (nrow, 16, 4)
    assert not np.any(arrays["FLAG"].any(-1) & ~flags.any(-1))
    assert all(
        v.dtype == bool and v.base is not None for v in result["stages"].values()
    )
    with pytest.raises(RuntimeError):
        core_flag._bool_view(np.array([0, 2], np.uint8))


def _memcpyed_chunk(payload, blocksize):
    header = bytes([2, 1, 0x02, 4])
    header += len(payload).to_bytes(4, "little")
    header += blocksize.to_bytes(4, "little")
    header += (16 + len(payload)).to_bytes(4, "little")
    return header + payload


def test_read_rows_into_writes_at_the_channel_offset(tmp_path):
    values = np.arange(20 * 3 * 2, dtype="<f4").reshape(20, 3, 2)
    path = tmp_path / "0.1.0"
    path.write_bytes(_memcpyed_chunk(values.tobytes(), blocksize=48))
    rows = np.array([1, 2, 7, 8, 19])
    out = np.full((len(rows), 9, 2), -1, "<f4")
    stats = core_fetch.read_rows_into(path, 24, rows, out, 3 * 2 * 4)
    assert np.array_equal(out[:, 3:6], values[rows])
    assert np.all(out[:, :3] == -1) and np.all(out[:, 6:] == -1)
    _raw, expected = core_zarr.read_rows(path, 24, rows)
    assert {k: stats[k] for k in ("bytes_read", "blocks_decoded", "blocks_total")} == {
        k: expected[k] for k in ("bytes_read", "blocks_decoded", "blocks_total")
    }
    with pytest.raises(ValueError):
        core_fetch.read_rows_into(path, 24, rows[::-1], out, 0)


def _decode_slice_unmodified(fetched):
    """`core_fetch.decode_slice` as it was before P5 (tobytes, concatenate)."""
    result = json.loads((fetched / "result.json").read_text())
    group = result["group"]
    rows = np.asarray(result["rows"], dtype=np.int64)
    arrays = {}
    for name in result["tile_columns"]:
        meta = json.loads((fetched / "objects" / group / name / ".zarray").read_text())
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        parts = []
        for tile in result["tiles"]:
            key = f"{group}/{name}/0.{tile}.0"
            plan = result["plans"][key]
            row_bytes = plan["row_bytes"]
            prefix = (fetched / "spans" / key / "head").read_bytes()
            _, _, used, _ = core_fetch.block_table(prefix)
            head = prefix[:used]
            out = np.empty((len(rows), row_bytes), np.uint8)
            _, blocksize, _, _ = core_zarr.header_fields(head)
            first_of = rows * row_bytes // blocksize
            last_of = ((rows + 1) * row_bytes - 1) // blocksize
            for first, count, _, _ in plan["runs"]:
                body = (fetched / "spans" / key / f"{first}-{count}").read_bytes()
                inside = np.flatnonzero(
                    (first_of >= first) & (last_of <= first + count - 1)
                )
                run_rows = np.ascontiguousarray(rows[inside], dtype=np.uintp)
                run_out = np.empty(len(inside) * row_bytes, np.uint8)
                assert not core_zarr.decode_span_rows(
                    head, first, count, body, row_bytes, run_rows, run_out
                )
                out[inside] = run_out.reshape(-1, row_bytes)
            parts.append(
                np.frombuffer(out.tobytes(), meta["dtype"]).reshape(
                    len(rows), nchan, ncorr
                )
            )
        arrays[name] = np.concatenate(parts, axis=1)
    return arrays


@pytest.mark.skipif(not K_FETCH.exists(), reason="archived K fetch not present")
def test_decode_slice_is_byte_identical_on_the_k_fetch():
    arrays, _ = core_fetch.decode_slice(K_FETCH)
    expected = _decode_slice_unmodified(K_FETCH)
    for name, value in expected.items():
        assert arrays[name].dtype == value.dtype
        assert arrays[name].tobytes() == value.tobytes(), name


@pytest.mark.skipif(
    not (array.SUPPORT.exists() and array.SOLVE_INPUTS.exists()),
    reason="archived LUNO tiles not present",
)
def test_decode_inputs_is_byte_identical_on_four_stations():
    arrays, rows, _ = array.decode_inputs([0, 1, 2, 3])
    lo, hi = array.CHANNELS
    for name in core_fetch.TILE_COLUMNS:
        meta = core_zarr.array_meta(array.resolve(f"{array.GROUP}/{name}"))
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        dtype = np.dtype(meta["dtype"])
        expected = np.empty((len(rows), hi - lo, ncorr), dtype)
        for tile in array.TILES:
            raw, _ = core_zarr.read_rows(
                array.resolve(f"{array.GROUP}/{name}/0.{tile}.0"),
                nchan * ncorr * dtype.itemsize,
                rows,
            )
            first = tile * nchan - lo
            expected[:, first : first + nchan] = np.frombuffer(raw, dtype).reshape(
                len(rows), nchan, ncorr
            )
        assert arrays[name].tobytes() == expected.tobytes(), name


def test_p5_bindings_are_in_the_extension():
    # Task P7 removed the standalone P5 library; the extension carries the
    # bindings and its binary still exports the C symbols.
    ext = core_fetch.p5_extension()
    for name in ("correct_stokes_i", "blosc_decode_span_rows_strided"):
        assert hasattr(ext, name)
    lib = ctypes.CDLL(ext.__file__)
    for name in (
        "rang_core_correct_stokes_i",
        "rang_core_blosc_decode_span_rows_strided",
    ):
        assert hasattr(lib, name)
    assert Path(core_fetch.__file__).exists()
