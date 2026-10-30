"""Offline tests of the L1 array campaign pieces (research/luno-array-campaign.md).

Every array-scale reimplementation must be bit-identical to task K's code on
the same cells; these tests check that on synthetic data.
"""

import numpy as np
import pytest
from rangtoy import core, core_campaign, core_grid, core_weights
from rangtoy import core_campaign_array as array
from rangtoy.core_workflow import core_solve, gain_grid
from rangtoy.flagging import protected_flags, residual_features


def _synthetic(seed=3, nchan=64, ntime=4):
    rng = np.random.default_rng(seed)
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    a1 = np.array([p for _ in range(ntime) for p, _ in pairs], np.int32)
    a2 = np.array([q for _ in range(ntime) for _, q in pairs], np.int32)
    times = np.repeat(np.arange(ntime, dtype=float), len(pairs))
    nrow = len(times)
    model = np.zeros((nrow, nchan, 4), np.complex64)
    model[..., 0] = model[..., 3] = 10.0
    data = model + (
        (rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)) * 0.01
    ).astype(np.complex64)
    data[3, 10] += 0.5  # an outlier for the policy masks
    data[7, 40:44] += 0.3
    weights = rng.uniform(1.0, 3.0, model.shape).astype(np.float32)
    flags = np.zeros(model.shape, bool)
    flags[0, :4] = True
    arrays = {
        "DATA": data,
        "MODEL_DATA": model,
        "WEIGHT_SPECTRUM": weights,
        "FLAG": flags,
        "FLAG_ROW": np.zeros(nrow, bool),
        "ANTENNA1": a1,
        "ANTENNA2": a2,
        "TIME": times,
    }
    extra = {
        "antenna_names": ["m000", "m001", "m002", "m003"],
        "chan_freq": 1.3e9 + 1e6 * np.arange(nchan),
    }
    return arrays, extra


def test_build_state_equals_k_for_four_stations():
    arrays, extra = _synthetic()
    mine = array.build_state(arrays, extra, nant=4)
    theirs = core_campaign.build_state(arrays, extra)
    for key in ("eligible", "train", "validation", "test"):
        assert np.array_equal(mine[key], theirs[key])
    assert mine["names"] == theirs["names"]


def test_baseline_scores_equal_residual_features():
    rng = np.random.default_rng(1)
    nrow, nchan = 30, 17
    residuals = rng.normal(size=(nrow, nchan, 4)) + 1j * rng.normal(
        size=(nrow, nchan, 4)
    )
    residuals[4, 3] = np.nan
    a1 = rng.integers(0, 3, nrow)
    a2 = a1 + 1 + rng.integers(0, 2, nrow)
    eligible = rng.random((nrow, nchan)) < 0.7
    eligible[a1 == 0] = False  # one baseline set without training cells
    expected = residual_features(residuals, eligible, a1, a2)
    amplitude = np.sqrt(np.sum(np.abs(residuals) ** 2, axis=-1))
    assert np.array_equal(array.baseline_scores(amplitude, eligible, a1, a2), expected)


def test_solve_arm_matches_core_solve_and_k_features_bit_for_bit():
    arrays, extra = _synthetic()
    state = array.build_state(arrays, extra, nant=4)
    zero = np.zeros_like(state["train"])
    k = core_campaign.solve_arm(state, zero, "original")
    mine = array.solve_arm(state, zero, "original", features=True)
    assert np.array_equal(mine["diagnostics"]["gains"], k["diagnostics"]["gains"])
    assert mine["metrics"]["losses"] == k["metrics"]["losses"]
    for key in ("tv", "raw_tv", "scale", "median_diagonal_amplitude"):
        assert mine["metrics"][key] == k["metrics"][key]
    assert np.array_equal(mine["tv"]["edges"], k["tv"]["edges"], equal_nan=True)
    assert np.array_equal(mine["guidance"], k["guidance"])
    outliers = residual_features(
        k["residuals"] * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    assert np.array_equal(mine["outliers"], outliers)
    metrics, *_ = core_solve(state, zero, *core_campaign.GRID, core_campaign.ITERATIONS)
    assert metrics["losses"] == mine["metrics"]["losses"]


def test_residual_amplitude_is_block_independent():
    arrays, extra = _synthetic()
    state = array.build_state(arrays, extra, nant=4)
    solve = array.solve_arm(state, np.zeros_like(state["train"]), "o")
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    labels = core.split_labels(
        train=state["train"], validation=state["validation"], test=state["test"]
    )
    args = (state, solve["diagnostics"]["gains"], solve["diagnostics"]["gain_valid"])
    whole = array.residual_amplitude(*args, labels, time_map, freq_map, block=10**6)
    blocks = array.residual_amplitude(*args, labels, time_map, freq_map, block=5)
    assert np.array_equal(whole, blocks)


def test_tv_loop_records_equal_k():
    arrays, extra = _synthetic()
    state = array.build_state(arrays, extra, nant=4)
    zero = np.zeros_like(state["train"])
    k_base = core_campaign.solve_arm(state, zero, "original")
    base = array.solve_arm(state, zero, "original", features=True)
    scale = base["metrics"]["scale"]
    k_trials, k_best, _ = core_campaign.tv_loop(state, k_base, scale, "tv")
    trials, best, _ = array.tv_loop(state, base, scale, "tv")
    assert len(trials) == len(k_trials)
    assert any("mask_sha256" in t for t in trials)
    for mine, theirs in zip(trials, k_trials):
        for key in ("trial", "mask_count", "objective", "accepted", "mask_sha256"):
            assert mine.get(key) == theirs.get(key)
    assert np.array_equal(best["solve"]["added"], k_best["solve"]["added"])


def test_corrected_stokes_blocks_equal_k_image_inputs():
    arrays, extra = _synthetic()
    state = array.build_state(arrays, extra, nant=4)
    solve = array.solve_arm(state, np.zeros_like(state["train"]), "o")
    solve["diagnostics"]["gain_valid"][1, 0, 2] = False
    solve["added"] = state["train"] & (np.arange(state["train"].shape[1]) % 7 == 0)
    sample, weight, _, _ = array.corrected_stokes(state, solve, block=4)
    time_map, freq_map, _, _ = gain_grid(state, *core_campaign.GRID)
    corrected, ok = core_campaign.apply_gains(
        state["data"],
        solve["diagnostics"]["gains"],
        solve["diagnostics"]["gain_valid"],
        state["antenna1"],
        state["antenna2"],
        time_map,
        freq_map,
    )
    final, rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.broadcast_to(solve["added"][..., None], state["original_flags"].shape),
    )
    k_sample, k_weight = core_grid.stokes_i_reader(
        corrected, state["weights"], final | ~ok[..., None], flag_rows=rows
    )
    assert np.array_equal(sample, k_sample) and np.array_equal(weight, k_weight)


def _point_source(nrow=200, nchan=8, seed=4):
    rng = np.random.default_rng(seed)
    uvw = np.column_stack(
        [rng.normal(0, 300, nrow), rng.normal(0, 300, nrow), rng.normal(0, 5, nrow)]
    )
    freqs = 1.3e9 + 1e7 * np.arange(nchan)
    sample = np.full((nrow, nchan), 2.0 + 0j, np.complex64)
    weight = np.ones((nrow, nchan), np.float32)
    weight[:, 2] = 0.0
    image = {
        "width": 64,
        "height": 64,
        "scale_arcsec": 20.0,
        "w_layers": 8,
        "kernel_size": 7,
        "oversampling": 63,
        "padding": 1.2,
    }
    imaging = core_weights.imaging_weights(
        uvw,
        core_weights.wsclean_wavelengths(freqs),
        weight,
        np.ones(nrow, bool),
        mode="briggs",
        robust=0.5,
        width=core_weights.padded_size(64, 1.2),
        height=core_weights.padded_size(64, 1.2),
        pixel_scale=core_weights.pixel_scale_radians(20.0),
        return_grid=False,
    )["weights"]
    return uvw, freqs, sample, weight, imaging, image


def test_grouped_invert_one_group_is_the_plain_call_and_groups_sum():
    uvw, freqs, sample, weight, imaging, image = _point_source()
    plain = core_grid.invert(uvw, freqs, sample, weight, imaging, **image)
    one = array.grouped_invert(uvw, freqs, sample, weight, imaging, image, 1)
    assert np.array_equal(one["dirty"], plain["dirty"])
    four = array.grouped_invert(uvw, freqs, sample, weight, imaging, image, 4)
    assert four["psf"][32, 32] == pytest.approx(1.0, abs=1e-12)
    peak = np.abs(plain["dirty"]).max()
    assert np.abs(four["dirty"] - plain["dirty"]).max() / peak < 1e-4
    assert np.abs(four["psf"] - plain["psf"]).max() < 1e-4
    assert four["stats"]["gridded_count"] == plain["stats"]["gridded_count"]
    assert four["stats"]["image_weight"] == pytest.approx(
        plain["stats"]["image_weight"]
    )
    weight[:, :2] = 0.0  # an empty group is skipped, not an error
    two = array.grouped_invert(uvw, freqs, sample, weight, imaging, image, 4)
    assert two["groups"][0]["skipped"] and not two["groups"][1]["skipped"]


def test_psf_fwhm_and_boxes_on_a_gaussian():
    n = 257
    y, x = np.mgrid[:n, :n]
    sigma = 3.0
    psf = np.exp(-((y - n // 2) ** 2 + (x - n // 2) ** 2) / (2 * sigma**2))
    fwhm = array.psf_fwhm(psf)
    true = 2 * np.sqrt(2 * np.log(2)) * sigma
    for value in fwhm["fwhm_pixels"].values():
        assert value == pytest.approx(true, rel=0.03)
    boxes = array.boxes_from_psf(psf, n)
    assert boxes["main_lobe_half_width"] == int(np.ceil(1.5 * fwhm["fwhm_max_pixels"]))
    assert boxes["far_half_width"] == min(
        n // 4, max(32, int(np.ceil(20 * fwhm["fwhm_max_pixels"])))
    )
    dirty = 4.0 * psf
    metrics = array.array_image_metrics(dirty, psf, boxes, model_flux=8.0)
    assert metrics["peak_jy_per_beam"] == pytest.approx(4.0)
    assert metrics["residual_rms"] < 1e-12
    assert metrics["flux_recovery"] == pytest.approx(0.5)
    assert metrics["psf_max_sidelobe"] < 1e-3
