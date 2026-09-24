"""Tracked follow-up evidence, matched coverage and unknown-outcome boundaries."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

RESULTS = Path(__file__).resolve().parents[1] / "research/results"


def load(name):
    return json.loads((RESULTS / name).read_text())


def rows(archive, case):
    return [
        dict(zip(archive["comparison_columns"], row, strict=True))
        for row in case["comparisons"]
    ]


def test_physical_response_matches_existing_counterfactual_labels_and_costs():
    archive = load("gain-tv-influence.json")
    original = load("gain-tv-balanced.json")
    old_cases = {c["case_id"]: c for c in original["cases"]}
    all_rows = []
    for case in archive["cases"]:
        old = {
            r[0]: dict(zip(original["action_columns"], r, strict=True))
            for r in old_cases[case["case_id"]]["actions"]
        }
        for r in rows(archive, case):
            previous = old[r["mask_id"]]
            assert r["actual_guard_pass"] == previous["guard_pass"]
            assert r["actual_benefit"] == 1.25 - previous["objective"]
            assert r["added_fraction"] == previous["added_fraction"]
            assert r["known_flag_cost_prediction"] == -2 * r["added_fraction"]
            assert r["actual_cost_removed_benefit"] == pytest.approx(
                r["actual_benefit"] + 2 * r["added_fraction"], abs=1e-15
            )
            if r["guard_pass"]:
                assert r["max_relative_station_step"] <= 0.1
                assert r["predicted_cost_removed_benefit"] == pytest.approx(
                    r["predicted_benefit"] + 2 * r["added_fraction"], abs=1e-15
                )
                assert len(r["canonical_gain_change"]) == 5
            else:
                assert r["predicted_benefit"] is None
                assert r["max_relative_station_step"] > 0.1
            all_rows.append(r)
    assert len(all_rows) == archive["actual_labels"] == 123
    assert sum(r["guard_pass"] for r in all_rows) == 120
    assert archive["new_QC_solves"] == archive["added_flags"] == 0
    assert archive["audit"] == {
        "source_unchanged": True,
        "runtime_unchanged": True,
        "injection_truth_test_values_used": False,
    }


@pytest.mark.parametrize(
    "group,suffix",
    [
        ("clean", "clean"),
        ("train", "101"),
        ("validation", "103"),
        ("test_case_group_retrospective", "105"),
    ],
)
def test_matched_coverage_errors_are_not_flag_cost_only(group, suffix):
    archive = load("gain-tv-influence.json")
    records = [
        r
        for case in archive["cases"]
        if case["case_id"].endswith(suffix)
        for r in rows(archive, case)
    ]
    covered = [r for r in records if r["guard_pass"]]
    summary = archive["summary"][group]
    assert summary["labels"] == len(records)
    assert summary["covered"] == len(covered)
    assert summary["abstentions"] == len(records) - len(covered)
    for key in ("predicted_benefit", "known_flag_cost_prediction"):
        rmse = math.sqrt(
            np.mean([(r[key] - r["actual_benefit"]) ** 2 for r in covered])
        )
        assert summary["matched_coverage_RMSE"][key] == pytest.approx(rmse, abs=1e-15)
    residual_rmse = math.sqrt(
        np.mean(
            [
                (r["predicted_cost_removed_benefit"] - r["actual_cost_removed_benefit"])
                ** 2
                for r in covered
            ]
        )
    )
    assert summary["matched_coverage_cost_removed_RMSE"]["physics_response"] == (
        pytest.approx(residual_rmse, abs=1e-15)
    )


def test_physics_recommendation_regret_includes_abstained_best_action():
    archive = load("gain-tv-influence.json")
    recommendations = archive["retrospective_one_slot_rankings_on_existing_union"]
    for case in archive["cases"]:
        records = rows(archive, case)
        positive = [
            r for r in records if r["guard_pass"] and r["predicted_benefit"] > 0
        ]
        selected = (
            min(
                positive,
                key=lambda r: (
                    -r["predicted_benefit"],
                    r["added_fraction"],
                    r["mask_id"],
                ),
            )
            if positive
            else None
        )
        recommendation = recommendations[case["case_id"]]["physics"]
        assert recommendation["mask_id"] == (selected["mask_id"] if selected else None)
        optimum = max([0.0] + [r["actual_benefit"] for r in records])
        actual = selected["actual_benefit"] if selected else 0.0
        assert recommendation["regret"] == pytest.approx(optimum - actual, abs=1e-15)
        assert recommendation["requires_actual_guarded_confirmation"]
    assert recommendations["time-burst-seed105"]["physics"]["regret"] > 0


def test_phase_archive_identity_objective_invariance_and_unknown_outcomes():
    archive = load("gain-tv-equivariance.json")
    original = load("gain-tv-balanced.json")
    old_cases = {c["case_id"]: c for c in original["cases"]}
    total = 0
    for case in archive["cases"]:
        metadata = [
            dict(zip(archive["action_metadata_columns"], row, strict=True))
            for row in case["action_metadata"]
        ]
        available = {r["mask_registry_index"] for r in metadata}
        old = {
            r[0]: dict(zip(original["action_columns"], r, strict=True))
            for r in old_cases[case["case_id"]]["actions"]
        }
        identity = case["patterns"]["identity"]
        for pattern, p in case["patterns"].items():
            assert p["reranked_actions_not_selected"]
            for mode in ("residual", "random"):
                assert (
                    p["recomputed_TRAIN_rankings"][mode]
                    == (identity["recomputed_TRAIN_rankings"][mode])
                )
            for mode, indices in p["unknown_reranked_action_indices"].items():
                assert not available.intersection(indices)
                assert set(indices) <= set(p["recomputed_TRAIN_rankings"][mode])
                chosen = p["selected_on_old_fixed_sets"][mode]
                assert (
                    chosen is None
                    or archive["mask_registry"].index(chosen) in available
                )
            for meta, row in zip(metadata, p["actions"], strict=True):
                r = dict(zip(archive["action_columns"], row, strict=True))
                mask = archive["mask_registry"][meta["mask_registry_index"]]
                previous = old[mask]
                # Original native-weight VAL losses are invariant under phases.
                objective = (
                    r["fixed_support_tv"] / p["baseline"]["tv"]
                    + 2 * meta["added_fraction"]
                    + 0.25
                    * previous["validation_MSE"]
                    / p["baseline"]["losses"]["validation"]
                )
                assert r["objective"] == pytest.approx(objective, abs=1e-12)
                assert r["cell_weighted_MSE_invariance_linf"] <= 4e-13
                assert r["prediction_equivariance_linf_jy"] <= 6e-15
                assert r["guard_pass"] and not r["guard_reasons"]
                if pattern == "identity":
                    assert r["objective"] == pytest.approx(
                        previous["objective"], abs=1e-12
                    )
                total += 1
    assert total == 492
    assert archive["transformed_gain_replays"] == total + 28 == 520
    assert archive["new_QC_solves"] == archive["added_flags"] == 0
    assert all(v is True or v == 0 for v in archive["audit"].values())
