"""Fitted guarded-benefit labels with grouped, not neighboring-action holdouts."""

import json

import numpy as np
import pytest
from rangtoy import flagging_transfer as transfer


def model_fixture():
    rng = np.random.default_rng(88)
    features = rng.normal(size=(50, len(transfer.FEATURE_NAMES)))
    targets = 0.004 * features[:, 0] + 0.001 * features[:, 1]
    groups = np.array(["a"] * 15 + ["b"] * 15 + ["val"] * 10 + ["test"] * 10)
    split = {
        "train": np.arange(30),
        "validation": np.arange(30, 40),
        "test": np.arange(40, 50),
    }
    return features, targets, groups, split


def test_test_targets_never_fit_normalize_tune_or_rank():
    features, targets, groups, split = model_fixture()
    model, prediction = transfer.fit_grouped_ridge(features, targets, groups, split)
    other_targets = targets.copy()
    other_targets[split["test"]] = np.nan
    other, other_prediction = transfer.fit_grouped_ridge(
        features, other_targets, groups, split
    )
    assert other == model
    np.testing.assert_array_equal(prediction, other_prediction)
    np.testing.assert_allclose(model["center"], features[split["train"]].mean(axis=0))


def test_case_groups_cannot_cross_splits_even_if_action_indices_are_disjoint():
    features, targets, groups, split = model_fixture()
    groups[45] = "a"
    with pytest.raises(ValueError, match="group crosses"):
        transfer.fit_grouped_ridge(features, targets, groups, split)


def test_unsupported_guard_labels_are_missing_not_zero_and_penalties_are_frozen():
    baseline = {"objective": 1.25, "guard_pass": True}
    valid = {
        "objective": 1.2,
        "guard_pass": True,
        "metrics": {},
        "fixed_support_tv": 0.5,
    }
    assert transfer.guarded_benefit(valid, baseline) == pytest.approx(0.05)
    for changed in (
        {"guard_pass": False},
        {"objective": None},
        {"objective": np.nan},
        {"fixed_support_tv": None},
        {"fixed_support_tv": np.nan},
        {"fixed_support_tv": np.inf},
        {"fixed_support_tv": -1},
    ):
        assert np.isnan(transfer.guarded_benefit({**valid, **changed}, baseline))
    features, targets, groups, split = model_fixture()
    targets[0] = np.nan
    model, _ = transfer.fit_grouped_ridge(features, targets, groups, split)
    assert model["missing_labels_train"] == 1
    with pytest.raises(ValueError, match="frozen penalties"):
        transfer.fit_grouped_ridge(features, targets, groups, split, penalties=(0.001,))


def test_extreme_test_features_refuse_but_cannot_change_model():
    features, targets, groups, split = model_fixture()
    model, _ = transfer.fit_grouped_ridge(features, targets, groups, split)
    features[split["test"]] = 1e100
    other, predictions = transfer.fit_grouped_ridge(features, targets, groups, split)
    assert other == model
    assert np.isnan(predictions[split["test"]]).all()
    _, audit = transfer.predict_actions(other, features)
    assert audit["refused_indices"] == split["test"].tolist()


def test_rank_ties_are_stable_and_missing_predictions_do_not_become_zero():
    assert transfer.rank_predictions(["c", "a", "b"], [0.1, 0.1, np.nan]) == [1, 0]
    assert not transfer.rank_predictions(["a"], [np.nan])
    with pytest.raises(ValueError, match="unique"):
        transfer.rank_predictions(["a", "a"], [0.1, 0.2])


def candidate(score):
    return {
        "metadata": {
            "group": "baseline",
            "time_mode": "single",
            "frequency_start": 1024,
            "frequency_stop": 1056,
        },
        "sample_count": 20,
        "added_fraction": 0.0003,
        "residual_score": score,
        "tv_score": 2 * score,
    }


def test_features_never_include_validation_test_losses():
    baseline = {"valid_gain_fraction": 0.33, "losses": {"test": 10, "validation": 20}}
    first = transfer.candidate_features(candidate(2), baseline)
    baseline["losses"] = {"test": np.nan, "validation": 1e100}
    np.testing.assert_array_equal(
        first, transfer.candidate_features(candidate(2), baseline)
    )


def test_fitted_run_accepts_compact_case_manifest_and_writes_no_MS(tmp_path):
    cases = []
    for seed in (101, 103, 105):
        source = tmp_path / f"seed{seed}"
        source.mkdir()
        actions = [
            {
                "mask_id": f"mask{i}",
                "candidate": candidate(i + 1),
                "metrics": {},
                "objective": 1.25 + 0.001 * (i + 1),
                "guard_pass": True,
                "fixed_support_tv": 0.15,
            }
            for i in range(5)
        ]
        (source / "manifest.json").write_text(
            json.dumps(
                {
                    "source_digest": "same-original-observation",
                    "scope": {
                        "telescope": "MeerKAT",
                        "band": "L",
                        "frequency_range_mhz": [856, 1711.79],
                    },
                    "split_gain_intervals": [2, 32],
                }
            )
        )
        (source / "result.json").write_text(
            json.dumps(
                {
                    "baseline": {
                        "metrics": {"valid_gain_fraction": 0.33},
                        "objective": 1.25,
                        "guard_pass": True,
                    },
                    "actions": actions,
                    "actual_solve_count": 6,
                    "audit": {"source_preserved": True},
                }
            )
        )
        cases.append(
            {
                "case_id": f"case{seed}",
                "seed": seed,
                "result_path": str(source / "result.json"),
            }
        )
    specification = tmp_path / "cases.json"
    specification.write_text(json.dumps(cases))
    output = tmp_path / "fitted"
    transfer.run(output, specification)
    result = json.loads((output / "result.json").read_text())
    assert result["model"]["ridge_penalty"] in transfer.PENALTIES
    assert result["evaluation"]["test"]["evaluated"] == 5
    assert result["distinct_observation_count"] == 1
    assert result["same_original_scan_across_splits"]
    assert result["cost"]["source_actual_solves"] == 18
    assert result["cost"]["new_QC_solves"] == 0
    assert all(
        c["no_change"] and not c["selected_or_exported_flags"]
        for c in result["forecasts"]
    )
    assert result["forecasts"][-1]["test_prediction_only"]
    assert not list(output.glob("*.ms"))
    with pytest.raises(FileExistsError):
        transfer.run(output, specification)
    with pytest.raises(ValueError, match="nested"):
        transfer.run(tmp_path / "seed101" / "nested", specification)
    assert not (tmp_path / "seed101" / "nested").exists()


@pytest.mark.parametrize(
    "mutation", ["missing", "telescope", "band", "frequencies", "grid"]
)
def test_unknown_source_telescope_band_and_solver_domain_are_refused(mutation):
    manifest = {
        "scope": {
            "telescope": "MeerKAT",
            "band": "L",
            "frequency_range_mhz": [856, 1712],
        },
        "split_gain_intervals": [2, 32],
        "source_digest": "original",
    }
    if mutation == "missing":
        manifest.pop("scope")
    elif mutation == "telescope":
        manifest["scope"]["telescope"] = "VLA"
    elif mutation == "band":
        manifest["scope"]["band"] = "UHF"
    elif mutation == "frequencies":
        manifest["scope"]["frequency_range_mhz"] = [400, 1712]
    else:
        manifest["split_gain_intervals"] = [1, 16]
    with pytest.raises(ValueError, match="unknown source domain"):
        transfer.validate_source_domain(manifest)
