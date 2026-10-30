"""Independent numerical/geometry checks for frozen TRAIN trend guidance."""

import copy

import numpy as np
import pytest
from rangtoy.flagging import gain_tv
from rangtoy.flagging_trend import (
    detrended_tv,
    estimate_trend,
    guidance_from_tv,
    training_gain_support,
)


def full_jones_fixture():
    times = np.array([0.0, 1.0, 2.5, 4.0, 6.0])
    frequencies = 1.2e9 + np.array([0, 2, 4, 5, 8, 10, 11]) * 1e6
    slopes = np.array([[0.021, 5e-8], [-0.042, -2e-8], [0.063, 8e-8]])
    matrices = np.array(
        [
            [[1.2 + 0.2j, 0.13 + 0.27j], [-0.15 + 0.04j, 0.9 - 0.1j]],
            [[0.8 - 0.07j, -0.09 + 0.04j], [0.18 + 0.19j, 1.3 + 0.06j]],
            [[1.1 + 0.1j, 0.3 - 0.2j], [-0.07 - 0.1j, 0.95 + 0.05j]],
        ]
    )
    amplitude = (
        1
        + 0.03 * np.arange(len(times))[:, None, None]
        + 0.02 * np.arange(len(frequencies))[None, :, None]
    )
    plain = amplitude[..., None, None] * matrices[None, None]
    phase = (
        1.47
        + times[:, None, None] * slopes[None, None, :, 0]
        + (frequencies - frequencies[0])[None, :, None] * slopes[None, None, :, 1]
    )
    gains = plain * np.exp(1j * phase)[..., None, None]
    valid = np.ones(gains.shape[:3], bool)
    return gains, plain, valid, times, frequencies, slopes


def independent_slopes(gains, used, times, frequencies):
    """NumPy determinant oracle, independently indexed and phase-wrapped."""
    phases = np.angle(np.linalg.det(gains))
    slopes = np.full((gains.shape[2], 2), np.nan)
    counts = np.zeros(slopes.shape, int)
    for axis, coordinates in enumerate((times, frequencies)):
        gaps = np.diff(coordinates)
        for antenna in range(gains.shape[2]):
            gradients = []
            for t in range(gains.shape[0]):
                for f in range(gains.shape[1]):
                    index = (t, f, antenna)
                    neighbour = (
                        (t + 1, f, antenna) if axis == 0 else (t, f + 1, antenna)
                    )
                    k = index[axis]
                    if k >= len(gaps) or gaps[k] > 3 * np.median(gaps):
                        continue
                    if used[index] and used[neighbour]:
                        difference = phases[neighbour] - phases[index]
                        wrapped = (difference + np.pi) % (2 * np.pi) - np.pi
                        gradients.append(wrapped / (2 * gaps[k]))
            counts[antenna, axis] = len(gradients)
            if len(gradients) >= (2 if axis == 0 else 4):
                slopes[antenna, axis] = np.median(gradients)
    return slopes, counts


def test_general_complex_jones_and_nonuniform_coordinates_match_independent_oracle():
    gains, _, valid, t, f, expected = full_jones_fixture()
    slopes, counts = estimate_trend(gains, valid, t, f, valid)
    oracle, oracle_counts = independent_slopes(gains, valid, t, f)
    np.testing.assert_allclose(slopes, expected, rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(slopes, oracle, rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(counts, oracle_counts)
    np.testing.assert_array_equal(counts, np.tile([28, 30], (3, 1)))


def test_actual_determinant_branch_crossings_do_not_alias_unaliased_scalar_steps():
    gains, _, valid, t, f, expected = full_jones_fixture()
    phases = np.angle(np.linalg.det(gains))
    assert np.any(np.abs(np.diff(phases, axis=1)) > np.pi)
    slopes, _ = estimate_trend(gains, valid, t, f, valid)
    np.testing.assert_allclose(slopes, expected, rtol=1e-12, atol=1e-15)


def test_scalar_alias_limit_is_not_certifiable_from_wrapped_determinants():
    t, f = np.arange(3.0), np.arange(5.0)
    phase = 0.9 * np.pi * t[:, None, None] + np.zeros((3, 5, 1))
    gains = np.exp(1j * phase)[..., None, None] * np.eye(2)
    valid = np.ones(gains.shape[:3], bool)
    slopes, _ = estimate_trend(gains, valid, t, f, valid)
    assert slopes[0, 0] == pytest.approx(-0.1 * np.pi, abs=2e-15)
    assert slopes[0, 0] != pytest.approx(0.9 * np.pi)


def test_dephasing_all_four_entries_preserves_full_matrix_tv_geometry():
    gains, plain, valid, t, f, slopes = full_jones_fixture()
    corrected = detrended_tv(gains, valid, t, f, slopes, scale=1.7)
    expected = gain_tv(plain, valid, t, f, scale=1.7)
    np.testing.assert_allclose(corrected["edges"], expected["edges"], atol=2e-14)
    np.testing.assert_allclose(corrected["map"], expected["map"], atol=2e-14)
    assert corrected["total"] == pytest.approx(expected["total"], abs=2e-14)
    assert np.linalg.norm(plain[..., 0, 1]) > 0
    assert np.linalg.norm(plain[..., 1, 0]) > 0


@pytest.mark.parametrize("amplitude", [1e-300, 1e300])
def test_determinant_normalization_avoids_finite_gain_scale_underflow_overflow(
    amplitude,
):
    gains, _, valid, t, f, expected = full_jones_fixture()
    slopes, counts = estimate_trend(gains * amplitude, valid, t, f, valid)
    np.testing.assert_allclose(slopes, expected, rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(counts, np.tile([28, 30], (3, 1)))


def test_real_large_coordinate_gap_is_excluded_in_estimator_and_tv():
    t, f = np.array([0.0, 1.0, 2.0, 100.0, 101.0]), np.arange(6.0)
    phase = 0.07 * t[:, None, None] + 0.09 * f[None, :, None]
    phase[3:] += 0.71
    gains = np.exp(1j * phase)[..., None, None] * np.eye(2)
    valid = np.ones(gains.shape[:3], bool)
    slopes, counts = estimate_trend(gains, valid, t, f, valid)
    np.testing.assert_allclose(slopes, [[0.07, 0.09]], atol=2e-15)
    np.testing.assert_array_equal(counts, [[18, 25]])
    tv = detrended_tv(gains, valid, t, f, slopes)
    assert not np.isfinite(tv["edges"][0, 2]).any()
    assert np.nanmax(tv["edges"]) < 3e-14


def test_invalid_missing_and_untrained_cells_remove_only_incident_edges():
    gains, _, valid, t, f, _ = full_jones_fixture()
    support = valid.copy()
    support[2, :, 0] = False
    valid[:, 3, 1] = False
    used = support & valid
    first, counts = estimate_trend(gains, valid, t, f, support)
    oracle, expected_counts = independent_slopes(gains, used, t, f)
    np.testing.assert_allclose(first, oracle, rtol=1e-12, atol=1e-15)
    np.testing.assert_array_equal(counts, expected_counts)
    gains[~used] = complex(np.nan, np.inf)
    poisoned, poisoned_counts = estimate_trend(gains, valid, t, f, support)
    np.testing.assert_array_equal(first, poisoned)
    np.testing.assert_array_equal(counts, poisoned_counts)


def test_near_singular_station_cannot_manufacture_a_supported_fit_or_edges():
    gains, _, valid, t, f, _ = full_jones_fixture()
    gains[:, :, 1] = np.diag([1.0, 1e-12])
    slopes, counts = estimate_trend(gains, valid, t, f, valid)
    assert np.isnan(slopes[1]).all()
    np.testing.assert_array_equal(counts[1], [0, 0])
    tv = detrended_tv(gains, valid, t, f, slopes)
    assert not np.isfinite(tv["edges"][..., 1]).any()


@pytest.mark.parametrize("shape", [(1, 1, 2), (1, 4, 2), (2, 1, 2)])
def test_insufficient_axis_edge_support_remains_missing(shape):
    gains = np.broadcast_to(np.eye(2, dtype=complex), (*shape, 2, 2)).copy()
    valid = np.ones(shape, bool)
    slopes, counts = estimate_trend(
        gains, valid, np.arange(shape[0]), np.arange(shape[1]), valid
    )
    assert np.isnan(slopes).all()
    assert np.all(counts[:, 0] < 2) and np.all(counts[:, 1] < 4)


@pytest.mark.parametrize(
    "argument", ["valid", "support", "gains", "times", "frequencies"]
)
def test_malformed_binding_shapes_or_nonbool_masks_rejected(argument):
    gains, _, valid, t, f, _ = full_jones_fixture()
    kwargs = {
        "gains": gains,
        "valid": valid,
        "training_support": valid,
        "times": t,
        "frequencies": f,
    }
    if argument == "valid":
        kwargs["valid"] = valid.astype(np.uint8)
    elif argument == "support":
        kwargs["training_support"] = valid[..., :1]
    elif argument == "gains":
        kwargs["gains"] = gains[..., 0]
    else:
        kwargs[argument] = kwargs[argument][:-1]
    with pytest.raises(ValueError):
        estimate_trend(**kwargs)


def geometry_state():
    train = np.zeros((4, 96), bool)
    train[0, 0], train[1, 40], train[2, 70] = True, True, True
    return {
        "train": train,
        "validation": np.zeros_like(train),
        "test": ~train,
        "times": np.array([100.0, 100.0, 104.0, 104.0]),
        "frequencies": np.arange(96.0),
        "antenna1": np.array([0, 1, 1, 0]),
        "antenna2": np.array([2, 2, 0, 2]),
        "data": np.ones((*train.shape, 4), complex),
        "model": np.ones((*train.shape, 4), complex),
        "weights": np.ones((*train.shape, 4)),
    }


def test_training_gain_geometry_and_guidance_use_both_station_ids_native_grid():
    state = geometry_state()
    actual = training_gain_support(state, (1, 3, 3))
    expected = np.zeros((1, 3, 3), bool)
    expected[0, 0, [0, 2]] = True
    expected[0, 1, [1, 2]] = True
    expected[0, 2, [0, 1]] = True
    np.testing.assert_array_equal(actual, expected)
    maps = np.arange(9.0).reshape(1, 3, 3)
    guidance = guidance_from_tv(state, {"map": maps})
    assert guidance[0, 0] == 2 and guidance[1, 40] == 5 and guidance[2, 70] == 7


def test_training_gain_membership_does_not_read_data_model_weights_or_heldout_values():
    state = geometry_state()
    expected = training_gain_support(state, (1, 3, 3))
    poisoned = copy.deepcopy(state)
    poisoned["data"][:] = complex(np.nan, np.inf)
    poisoned["model"][:] = -1e308
    poisoned["weights"][:] = -np.inf
    poisoned["validation"] = ~poisoned["train"] & (np.arange(96)[None, :] % 2 == 0)
    poisoned["test"] = ~poisoned["train"] & ~poisoned["validation"]
    np.testing.assert_array_equal(training_gain_support(poisoned, (1, 3, 3)), expected)


def test_finite_endpoints_with_overflowing_coordinate_difference_rejected():
    gains = np.broadcast_to(np.eye(2, dtype=complex), (2, 5, 1, 2, 2)).copy()
    valid = np.ones(gains.shape[:3], bool)
    with np.errstate(over="ignore"), pytest.raises(ValueError, match="coordinates"):
        estimate_trend(gains, valid, [-1e308, 1e308], np.arange(5.0), valid)


@pytest.mark.parametrize(
    "corruption", ["nonbool", "FLAG", "FLAG_ROW", "heldout", "antenna", "grid"]
)
def test_training_gain_membership_rejects_corrupted_or_protected_geometry(corruption):
    state, shape = geometry_state(), (1, 3, 3)
    state["original_flags"] = np.zeros((*state["train"].shape, 4), bool)
    state["original_rows"] = np.zeros(4, bool)
    if corruption == "nonbool":
        state["train"] = state["train"].astype(int)
    elif corruption == "FLAG":
        state["original_flags"][0, 0, 2] = True
    elif corruption == "FLAG_ROW":
        state["original_rows"][0] = True
    elif corruption == "heldout":
        state["validation"][0, 0] = True
    elif corruption == "antenna":
        state["antenna1"][0] = 3
    else:
        shape = (1, 2, 3)
    with pytest.raises(ValueError):
        training_gain_support(state, shape)
