"""Action splits, training-only features and withheld-label safeguards.

Live part of tests/test_flagging_actions.py at commit 2da566c
(now history/tests/test_flagging_actions.py,
sha256 7bb4743b4afe9de78290d933ab6cff7cbd6b9132619e81701214ed558df5a222):
the test functions that use only extracted names, with the helpers they
use, copied verbatim in source order; only import statements point at
the extracts (big plan task P11, research/p11-extract.md).
"""

import numpy as np
import pytest
from rangtoy.core_patches import (
    candidate_patches,
    fit_action_model,
    proposal_from_model,
    split_actions,
)


def test_action_model_never_uses_test_labels_or_test_features_for_standardization():
    rng = np.random.default_rng(10)
    features = rng.normal(size=(30, 8))
    targets = features[:, 1] * 0.02 + 0.003
    split = split_actions(30)
    model, predictions = fit_action_model(features, targets, split)
    changed = targets.copy()
    changed[split["test"]] = 1e9
    other, other_predictions = fit_action_model(features, changed, split)
    assert model == other
    np.testing.assert_array_equal(predictions, other_predictions)
    np.testing.assert_allclose(
        model["center"], np.mean(features[split["train"]], axis=0)
    )
    assert np.mean((predictions[split["test"]] - targets[split["test"]]) ** 2) < 1e-6


def test_action_splits_are_fixed_disjoint_and_exhaustive():
    splits = split_actions(16, 29)
    for key, indices in splits.items():
        np.testing.assert_array_equal(indices, split_actions(16, 29)[key])
    np.testing.assert_array_equal(
        np.sort(np.concatenate(list(splits.values()))), np.arange(16)
    )
    with pytest.raises(ValueError, match="six"):
        split_actions(5)


def test_missing_action_labels_are_explicit_not_zero_and_invalid_splits_rejected():
    rng = np.random.default_rng(2)
    features = rng.normal(size=(16, 8))
    targets = rng.normal(size=16)
    split = split_actions(16)
    targets[split["train"][0]] = np.nan
    model, _ = fit_action_model(features, targets, split)
    assert model["missing_labels"]["train"] == 1
    split["test"][0] = split["train"][0]
    with pytest.raises(ValueError, match="partition"):
        fit_action_model(features, targets, split)


def test_action_proposal_retains_no_change_budget_and_never_selects_test_actions():
    patches = [{"indices": np.arange(i * 10, (i + 1) * 10)} for i in range(8)]
    predictions = np.full(8, -0.5)
    mask, chosen = proposal_from_model(
        patches, predictions, [0, 1, 2], (10, 10), 100, max_fraction=0.2
    )
    assert chosen == [0, 1]
    assert mask.sum() == 20 and not mask.flat[30:80].any()
    mask, chosen = proposal_from_model(patches, np.ones(8), [0, 1], (10, 10), 100)
    assert not mask.any() and not chosen


def test_patch_features_ignore_holdout_residuals_and_actions_do_not_overlap():
    rng = np.random.default_rng(18)
    shape = (8, 64, 4)
    train = np.ones(shape[:2], bool)
    train[:, ::5] = False
    state = {
        "train": train,
        "data": np.zeros(shape, complex),
        "weights": np.ones(shape),
        "times": np.arange(8),
        "antenna1": np.zeros(8, int),
        "antenna2": np.ones(8, int),
        "names": np.array(["m000", "m001"]),
        "action_intervals": [2, 8],
    }
    residuals = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    guidance = rng.random(shape[:2])
    patches = candidate_patches(state, residuals, guidance, 12)
    altered, altered_tv = residuals.copy(), guidance.copy()
    altered[~train], altered_tv[~train] = 1e10, 1e10
    other = candidate_patches(state, altered, altered_tv, 12)
    for first, second in zip(patches, other):
        np.testing.assert_array_equal(first["indices"], second["indices"])
        np.testing.assert_array_equal(first["features"], second["features"])
        assert train.flat[first["indices"]].all()
    indices = np.concatenate([p["indices"] for p in patches])
    assert len(np.unique(indices)) == len(indices)
