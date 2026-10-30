"""Synthetic control construction and scoring do not require casacore.

Live part of tests/test_flagging_injections.py at commit 2da566c
(now history/tests/test_flagging_injections.py,
sha256 818c0bf747ef3f4286e1b7cec11a07427085d6eccadda071269f114329fa1b0b):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
import pytest
from rangtoy.core_injection_model import (
    injection_scores,
    make_injection,
    reference_distance,
)


def state():
    p = np.tile([0, 0, 1, 0], 4)
    q = np.tile([1, 2, 2, 0], 4)
    shape = (len(p), 128, 4)
    flags = np.zeros(shape, bool)
    flags[:, 40:50] = True
    rows = np.zeros(len(p), bool)
    rows[1] = True
    eligible = ~flags.any(axis=-1) & ~rows[:, None] & (p != q)[:, None]
    train = eligible.copy()
    train[:, ::7] = False
    return {
        "data": np.ones(shape, complex),
        "weights": np.full(shape, 4.0),
        "original_flags": flags,
        "original_rows": rows,
        "train": train,
        "validation": eligible & ~train,
        "test": np.zeros(shape[:2], bool),
        "times": np.repeat(np.arange(4), 4),
        "antenna1": p,
        "antenna2": q,
        "window": np.ones(shape[1], bool),
    }


@pytest.mark.parametrize("pattern", ["narrowband", "time-burst", "antenna-local"])
def test_injections_are_repeatable_training_only_and_protect_input(pattern):
    source = state()
    data_before = source["data"].copy()
    mask, delta, metadata = make_injection(source, pattern, 3, 19)
    other_mask, other_delta, other_metadata = make_injection(source, pattern, 3, 19)
    np.testing.assert_array_equal(mask, other_mask)
    np.testing.assert_array_equal(delta, other_delta)
    np.testing.assert_array_equal(source["data"], data_before)
    assert metadata == other_metadata
    assert mask.any() and not mask[~source["train"]].any()
    assert not delta[~mask].any()
    np.testing.assert_allclose(np.abs(delta[mask]), 1.5)
    if pattern == "time-burst":
        assert len(np.unique(source["times"][np.nonzero(mask)[0]])) == 1
    if pattern == "antenna-local":
        rows = np.nonzero(mask)[0]
        antenna = metadata["antenna"]
        assert (
            (source["antenna1"][rows] == antenna)
            | (source["antenna2"][rows] == antenna)
        ).all()
    _, stronger, _ = make_injection(source, pattern, 10, 19)
    np.testing.assert_allclose(stronger, delta * (10 / 3))


def test_injections_reject_overlap_and_protected_training():
    source = state()
    source["train"][0, 40] = True
    with pytest.raises(ValueError, match="protected"):
        make_injection(source, "narrowband", 3, 19)
    source = state()
    source["validation"][0, 1] = True
    with pytest.raises(ValueError, match="overlap"):
        make_injection(source, "narrowband", 3, 19)


def test_injections_validate_pattern_and_native_weights():
    source = state()
    with pytest.raises(ValueError, match="unknown injection"):
        make_injection(source, "not-rfi", 3, 19)
    with pytest.raises(ValueError, match="positive strength"):
        make_injection(source, "narrowband", 0, 19)
    source["weights"][:] = 0
    with pytest.raises(ValueError, match="positive native weights"):
        make_injection(source, "narrowband", 3, 19)


def test_injection_score_distinguishes_known_recovery_and_unlabeled_additions():
    train = np.ones((2, 4), bool)
    truth = np.zeros_like(train)
    truth[0, :2] = True
    added = np.zeros_like(train)
    added[0, 1:3] = True
    score = injection_scores(added, truth, train)
    assert score["injection_recall"] == 0.5
    assert score["additions_outside_injections"] == 1
    assert score["outside_additions_are_not_proven_false_positives"]
    train[0, 2] = False
    with pytest.raises(ValueError, match="outside training"):
        injection_scores(added, truth, train)


def test_reference_distance_keeps_fixed_clean_support():
    source = state()
    clean = {
        "residuals": np.zeros_like(source["data"]),
        "gauge_gains": np.ones((2, 3, 2, 2, 2), complex),
        "tv_valid": np.ones((2, 3, 2), bool),
    }
    candidate = {**clean, "tv_valid": clean["tv_valid"].copy()}
    # Ensure both diagnostic splits are nonempty in this small pure-Python test.
    source["test"] = source["validation"].copy()
    result = reference_distance(source, clean["residuals"], candidate, source, clean)
    assert result["polar_gauge_gain_mse_to_clean"] == 0
    assert result["weighted_prediction_mse_to_clean"] == {"validation": 0, "test": 0}
    candidate["tv_valid"][0, 0, 0] = False
    result = reference_distance(source, clean["residuals"], candidate, source, clean)
    assert result["unsupported_clean_gain_bins"] == 1
    assert result["polar_gauge_gain_mse_to_clean"] is None
