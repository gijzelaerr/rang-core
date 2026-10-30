"""Full-matrix phase symmetry, frozen controls and missing outcome boundaries."""

import sys

import numpy as np
import pytest
from rangtoy import flagging_equivariance as equivariance
from rangtoy.flagging_caracal import score_control
from rangtoy.flagging_equivariance import (
    PATTERNS,
    cell_phases,
    checkpoint,
    gain_prediction,
    phase_factors,
    phase_replay,
    run,
)

# The frozen flagging modules size their writes with os.stat_result.st_blocks,
# which Windows lacks; they cannot change (research/p8-history.md), so these
# tests are skipped there (research/x1-crossplatform.md, task P7).
needs_st_blocks = pytest.mark.skipif(
    sys.platform == "win32", reason="frozen module reads st_blocks (absent on Windows)"
)


def fixture():
    rng = np.random.default_rng(431)
    rows, channels = 8, 64
    gains = np.broadcast_to(np.eye(2), (2, 2, 4, 2, 2)).astype(complex).copy()
    gains += 0.08 * (rng.normal(size=gains.shape) + 1j * rng.normal(size=gains.shape))
    model = np.zeros((rows, channels, 4), complex)
    model[..., 0] = model[..., 3] = 4.0
    times = np.repeat([100.0, 108.0, 116.0, 124.0], 2)
    frequencies = np.linspace(1.07e9, 1.1e9, channels)
    a1 = np.tile([0, 1], 4)
    a2 = np.tile([2, 3], 4)
    train = np.ones((rows, channels), bool)
    train[:, :2] = False
    validation, test = np.zeros_like(train), np.zeros_like(train)
    validation[:, 0], test[:, 1] = True, True
    state = {
        "data": np.zeros_like(model),
        "model": model,
        "times": times,
        "frequencies": frequencies,
        "antenna1": a1,
        "antenna2": a2,
        "weights": rng.uniform(1, 3, model.shape),
        "train": train,
        "validation": validation,
        "test": test,
    }
    state["data"] = gain_prediction(state, gains) + 0.1 * (
        rng.normal(size=model.shape) + 1j * rng.normal(size=model.shape)
    )
    gain_times = np.array([104.0, 120.0])
    gain_frequencies = np.array([np.mean(frequencies[:32]), np.mean(frequencies[32:])])
    return state, gains, gain_times, gain_frequencies


@pytest.mark.parametrize("pattern", list(PATTERNS))
def test_all_frozen_patterns_preserve_full_jones_weighted_residuals(pattern):
    state, gains, times, frequencies = fixture()
    factors = phase_factors(times, frequencies, pattern)
    np.testing.assert_allclose(np.abs(factors), 1, rtol=0, atol=3e-16)
    np.testing.assert_array_equal(factors[..., 0], 1)
    phase = cell_phases(state, factors)
    rotated_prediction = gain_prediction(state, gains * factors[..., None, None])
    np.testing.assert_allclose(
        rotated_prediction, gain_prediction(state, gains) * phase[..., None], atol=1e-14
    )
    before = (
        np.abs(state["data"] - gain_prediction(state, gains)) ** 2 * state["weights"]
    )
    after = (
        np.abs(state["data"] * phase[..., None] - rotated_prediction) ** 2
        * state["weights"]
    )
    np.testing.assert_allclose(after, before, atol=1e-14)
    metrics, _, _ = phase_replay(
        state, gains, np.ones(gains.shape[:3], bool), times, frequencies, 1, pattern
    )
    assert metrics["maximum_cell_weighted_MSE_invariance_error"] < 1e-14
    assert metrics["maximum_visibility_prediction_equivariance_error_jy"] < 1e-14


def test_legitimate_smooth_phase_can_increase_tv_without_residual_change():
    state, gains, times, frequencies = fixture()
    gains[:] = np.eye(2)
    valid = np.ones(gains.shape[:3], bool)
    zero, _, _ = phase_replay(state, gains, valid, times, frequencies, 1, "identity")
    smooth, _, _ = phase_replay(state, gains, valid, times, frequencies, 1, "both")
    assert zero["tv"] == 0
    assert smooth["tv"] > 0.1
    for split in ("train", "validation", "test"):
        assert smooth["losses"][split] == pytest.approx(
            zero["losses"][split], abs=1e-12
        )


def test_identity_and_short_time_span_freeze():
    factors = phase_factors([0, 0.25], [1.07e9], "smooth-time")
    np.testing.assert_allclose(
        factors[1, 0], np.exp(1j * np.array([0, 0.2, -0.2, 0.4]))
    )
    np.testing.assert_array_equal(
        phase_factors([5], [1.07e9], "smooth-time"), np.ones((1, 1, 4))
    )
    np.testing.assert_array_equal(
        phase_factors([1, 2], [1.07e9, 1.08e9], "identity"), np.ones((2, 2, 4))
    )


@pytest.mark.parametrize(
    "times,frequencies,pattern",
    [
        ([], [1.07e9], "identity"),
        ([0, 0], [1.07e9], "identity"),
        ([0], [np.nan], "both"),
        ([0], [1.07e9], "not-frozen"),
    ],
)
def test_invalid_phase_controls_refused(times, frequencies, pattern):
    with pytest.raises(ValueError):
        phase_factors(times, frequencies, pattern)


def test_native_gain_grid_change_refused():
    state, gains, _, _ = fixture()
    with pytest.raises(ValueError, match="grid"):
        gain_prediction(state, gains[:1])


def test_existing_or_nested_outputs_refused_without_creation(tmp_path):
    source, output = tmp_path / "source", tmp_path / "existing"
    source.mkdir()
    output.mkdir()
    for target in (output, source / "nested", tmp_path):
        with pytest.raises(ValueError):
            run(target, source)
    assert not (source / "nested").exists()


def test_test_values_do_not_affect_tv_or_validation_objective():
    state, gains, times, frequencies = fixture()
    valid = np.ones(gains.shape[:3], bool)
    before, _, _ = phase_replay(state, gains, valid, times, frequencies, 1, "both")
    state["data"][state["test"]] += 1000 + 500j
    after, _, _ = phase_replay(state, gains, valid, times, frequencies, 1, "both")
    for metrics in (before, after):
        metrics["added_fraction"] = 0.001
    assert after["losses"]["test"] > 10000 * before["losses"]["test"]
    assert after["losses"]["train"] == before["losses"]["train"]
    assert after["losses"]["validation"] == before["losses"]["validation"]
    assert score_control(after, after["tv"], before) == score_control(
        before, before["tv"], before
    )


@needs_st_blocks
def test_checked_checkpoint_is_exclusive_and_stops_before_budget_breach(
    tmp_path, monkeypatch
):
    checkpoint(tmp_path, "first.json", {"complete": True})
    with pytest.raises(ValueError, match="fresh"):
        checkpoint(tmp_path, "first.json", {"complete": False})
    monkeypatch.setattr(equivariance, "ALLOCATION_BYTES", 1)
    with pytest.raises(ValueError, match="budget"):
        checkpoint(tmp_path, "second.json", {"complete": False})
    assert not (tmp_path / "second.json").exists()
