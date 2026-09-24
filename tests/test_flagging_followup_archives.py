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


def test_calibration_response_freeze_support_and_protected_columns():
    archive = load("gain-tv-response.json")
    config = archive["configuration"]
    freeze = archive["frozen_controls"]
    assert config["frozen_before_solve"]
    assert config["grids"] == [[2, 32], [14, 128]]
    assert config["planned_QC_solves"] == archive["actual_QC_diagnostic_solves"] == 10
    assert len(archive["baselines"]) == 2
    assert len(freeze["arms"]) == len(archive["methods"]) == 8
    assert not freeze["test_or_source_truth_used_to_select"]
    assert not archive["policy_search_or_selection"]
    assert archive["added_flags"] == archive["native_flagger_solves"] == 0
    assert archive["common_TEST_samples"] == archive["original_TEST_samples"] == 9169
    assert archive["lost_common_TEST_samples"] == 0
    invocations = archive["calibration_invocations"]
    assert invocations["successful_fresh_run"] == 10
    assert invocations["retained_precision_failed_run"] == 10
    assert invocations["total_actual"] == 20
    assert invocations["frozen_physical_controls"] == 10
    assert not invocations["independent_replicates"]
    assert not invocations["retained_failed_copies_exportable"]
    for key in (
        "prepared_source_unchanged",
        "raw_source_unchanged",
        "module_unchanged",
        "all_helper_modules_unchanged",
        "native_library_unchanged",
    ):
        assert archive["audit"][key]
    for copy in archive["audit"]["copies"].values():
        for key in (
            "FLAG_exact_original",
            "FLAG_ROW_exact_original",
            "DATA_exact_documented_state",
            "base_model_column_exact",
            "native_weight_sigma_exact",
        ):
            assert copy[key]
    resources = archive["resource_receipt"]
    assert resources["allocated_regular_file_bytes"] < config["allocation_bytes"]
    assert resources["observed_host_free_bytes"] > config["disk_reserve_bytes"]
    assert not resources["os_enforced_quota"]
    assert not resources["native_cost_benchmark"]


@pytest.mark.parametrize("case,sign", [("positive", 1), ("negative", -1)])
def test_calibration_response_reference_uses_signed_fixed_spectra(case, sign):
    archive = load("gain-tv-response.json")
    reference = archive["reference_fits"][case]
    source_flux = [source["flux_jy"] for source in archive["configuration"]["sources"]]
    assert reference["available"] and reference["rank"] == 2
    assert reference["condition"] <= 1e8
    assert reference["sample_count"] == archive["common_TEST_samples"]
    assert reference["flux_jy"] == pytest.approx(
        np.asarray(source_flux) * sign, abs=1e-8
    )
    assert reference["spectral_indices"] == "fixed evaluation family; not fitted"
    assert not reference["positivity_or_parameter_bounds"]
    assert reference["confidence_intervals"].startswith("not claimed")


@pytest.mark.parametrize("arm_index", range(8))
def test_calibration_response_exact_paired_decomposition_and_ratios(arm_index):
    archive = load("gain-tv-response.json")
    arm = archive["methods"][arm_index]
    frozen = archive["frozen_controls"]["arms"][arm_index]
    assert all(arm[key] == value for key, value in frozen.items())
    assert arm["diagnostic_only"] and not arm["selected_for_deployment"]
    assert arm["unsupported_original_TEST_samples"] == 0
    assert arm["metrics"]["added_count"] == arm["metrics"]["added_fraction"] == 0
    for fit in arm["fits"].values():
        assert fit["available"] and fit["rank"] == 2
        assert fit["condition"] <= 1e8
        assert fit["sample_count"] == archive["common_TEST_samples"]
        assert not fit["positivity_or_parameter_bounds"]
    total, direct, adaptation = (
        np.asarray(arm["fits"][key]["flux_jy"])
        for key in ("total", "direct", "adaptation")
    )
    assert total == pytest.approx(direct + adaptation, abs=1e-15)
    reference = np.asarray(archive["reference_fits"][arm["case"]]["flux_jy"])
    assert arm["response_fraction_vs_fixedG0"] == pytest.approx(
        total / reference, abs=1e-15
    )
    assert arm["visibility_decomposition_closure_linf_jy"] <= 1e-10
    assert arm["linear_fit_decomposition_closure_linf_jy"] <= 1e-15


def test_calibration_response_retains_lower_tv_worse_prediction_control():
    archive = load("gain-tv-response.json")
    fine, coarse = archive["baselines"]
    assert coarse["metrics"]["tv"] < fine["metrics"]["tv"]
    assert (
        coarse["metrics"]["losses"]["validation"]
        > fine["metrics"]["losses"]["validation"]
    )
    positive_fine = {
        arm["sky"]: arm
        for arm in archive["methods"]
        if arm["case"] == "positive" and arm["grid"] == [2, 32]
    }
    omitted, complete = (
        positive_fine[key] for key in ("omitted", "complete-diagnostic")
    )
    assert omitted["metrics"]["tv"] < fine["metrics"]["tv"]
    assert omitted["metrics"]["tv"] < complete["metrics"]["tv"]
    assert np.all(
        np.asarray(omitted["response_fraction_vs_fixedG0"])
        < np.asarray(complete["response_fraction_vs_fixedG0"])
    )


def test_response_audit_retains_non_bit_identical_reproduction_findings():
    audit = load("gain-tv-response-audit.json")
    checks = audit["checks"]
    assert audit["check_count"] == len(checks) == 614
    assert audit["pass_count"] == sum(checks.values()) == 602
    assert set(audit["failures"]) == {key for key, ok in checks.items() if not ok}
    assert len(audit["failures"]) == 12
    summary = audit["check_summary"]
    assert not summary["bit_identical_gain_reproduction"]
    assert summary["native_QC_gain_trees_exact"] == 9
    assert summary["total_native_QC_gain_trees"] == 10
    assert summary["all_native_calibration_inputs_and_protocol_exact"]
    assert summary["all10_prediction_losses_exact"]
    for key, count in (
        ("qualified_reproduction", 24),
        ("additional_backup_boundary_checks", 30),
    ):
        section = audit[key]
        assert len(section["checks"]) == section["pass_count"] == count
        assert all(section["checks"].values()) and not section["failures"]
    assert audit["execution_counts"]["additional_QC_audit"] == 0
    assert audit["execution_counts"]["actual_QC_total"] == 20
    assert audit["execution_counts"]["distinct_physical_controls"] == 10


def test_response_audit_independent_reconstruction_matches_all_arms():
    archive = load("gain-tv-response.json")
    audit = load("gain-tv-response-audit.json")
    assert (
        audit["provenance"]["result_file_sha256"]
        == archive["raw_receipts_sha256"]["result.json"]
    )
    assert audit["common_TEST"]["supported"] == archive["common_TEST_samples"]
    assert audit["common_TEST"]["lost"] == 0
    old = {(arm["case"], arm["trial"]): arm for arm in archive["methods"]}
    assert len(audit["methods_replayed"]) == len(old) == 8
    for replay in audit["methods_replayed"]:
        arm = old[(replay["case"], replay["trial"])]
        assert replay["visibility_closure_linf_jy"] <= 1e-10
        assert replay["coefficient_closure_linf_jy"] <= 1e-10
        assert replay["unsupported_TEST_samples"] == 0
        assert replay["response_fraction_vs_fixedG0"] == pytest.approx(
            arm["response_fraction_vs_fixedG0"], abs=1e-13
        )
        for term in ("total", "direct", "adaptation"):
            fit = replay["fits"][term]
            assert fit["rank"] == 2
            assert fit["sample_count"] == archive["common_TEST_samples"]
            assert fit["flux_jy"] == pytest.approx(
                arm["fits"][term]["flux_jy"], abs=1e-14
            )
    provenance = audit["provenance"]
    for prefix in ("failed", "fresh"):
        assert provenance[f"{prefix}_tree_before"] == provenance[f"{prefix}_tree_after"]
        assert provenance[f"final_{prefix}_tree"] == provenance[f"{prefix}_tree_before"]
