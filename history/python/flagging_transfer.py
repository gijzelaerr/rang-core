"""Fitted case-group-held-out prediction of actual guarded action benefit.

Only completed counterfactual outcomes supply labels. Model and feature-only
rankings are frozen before test-label diagnostics. This workflow writes no MS.
"""

import json
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging_prepared import reject_nested_paths
from .flagging_workflow import write_json

PENALTIES = (0.1, 1.0, 10.0)
FEATURE_NAMES = (
    "log_sample_count",
    "added_fraction",
    "log_frequency_width",
    "all_times",
    "global_group",
    "antenna_star_group",
    "baseline_group",
    "log_residual_score",
    "log_tv_score",
    "log_tv_residual_ratio",
    "baseline_supported_gain_fraction",
)
SPLITS = ("train", "validation", "test")


def candidate_features(candidate, baseline):
    """Fixed TRAIN-score/geometry features; no evaluation losses are inputs."""
    metadata = candidate["metadata"]
    group = metadata["group"]
    count, fraction = candidate["sample_count"], candidate["added_fraction"]
    width = metadata["frequency_stop"] - metadata["frequency_start"]
    residual, tv = candidate["residual_score"], candidate["tv_score"]
    support = baseline["valid_gain_fraction"]
    if (
        group not in ("global", "antenna-star", "baseline")
        or metadata["time_mode"] not in ("single", "all")
        or width not in (16, 32, 64, 128)
        or count < 8
        or not np.isfinite([count, fraction, residual, tv, support]).all()
        or not 0 < fraction <= 0.02
        or min(residual, tv) < 0
        or not 0 < support <= 1
    ):
        raise ValueError("unsupported candidate semantics or TRAIN feature domain")
    result = np.array(
        [
            np.log1p(count),
            fraction,
            np.log1p(width),
            metadata["time_mode"] == "all",
            group == "global",
            group == "antenna-star",
            group == "baseline",
            np.log1p(residual),
            np.log1p(tv),
            np.log1p(tv / max(residual, 1e-12)),
            support,
        ],
        float,
    )
    if not np.isfinite(result).all():
        raise ValueError("nonfinite candidate features")
    return result


def guarded_benefit(record, baseline_record):
    """Invalid/missing counterfactuals remain missing labels, not no-change zeros."""
    objective, baseline = record.get("objective"), baseline_record.get("objective")
    fixed_tv = record.get("fixed_support_tv")
    if (
        record.get("guard_pass") is not True
        or baseline_record.get("guard_pass") is not True
        or objective is None
        or baseline is None
        or not np.isfinite([objective, baseline]).all()
        or "metrics" not in record
        or fixed_tv is None
        or not np.isfinite(fixed_tv)
        or fixed_tv < 0
    ):
        return np.nan
    return float(baseline - objective)


def validate_source_domain(manifest):
    """Reject unknown telescope/band/solver grids rather than extrapolate quietly."""
    scope = manifest.get("scope", {})
    frequencies = np.asarray(scope.get("frequency_range_mhz", []), float)
    if (
        str(scope.get("telescope", "")).strip().casefold() != "meerkat"
        or scope.get("band") != "L"
        or frequencies.shape != (2,)
        or not np.isfinite(frequencies).all()
        or not 856 <= frequencies[0] < frequencies[1] <= 1712
        or manifest.get("split_gain_intervals") != [2, 32]
        or not isinstance(manifest.get("source_digest"), str)
        or not manifest["source_digest"]
    ):
        raise ValueError(
            "unknown source domain; MeerKAT L-band and gain grid2/32 required"
        )
    return manifest["source_digest"]


def _partition(split, groups, size):
    if set(split) != set(SPLITS):
        raise ValueError("exact train/validation/test case-group partition required")
    normalized = {}
    for key in SPLITS:
        values = np.asarray(split[key])
        if values.ndim != 1 or values.dtype.kind not in "iu":
            raise ValueError("integer partition indices required")
        normalized[key] = values
    indices = np.concatenate(list(normalized.values()))
    if not np.array_equal(np.sort(indices), np.arange(size)):
        raise ValueError("disjoint exhaustive partition required")
    membership = {}
    for key, indices in normalized.items():
        for group in np.unique(groups[indices]):
            if group in membership and membership[group] != key:
                raise ValueError("case/scan group crosses held-out splits")
            membership[group] = key
    return normalized


def _weights(groups):
    unique, inverse, count = np.unique(groups, return_inverse=True, return_counts=True)
    return 1 / (len(unique) * count[inverse])


def _domain(model, features):
    lower, upper = np.array(model["domain_lower"]), np.array(model["domain_upper"])
    return (
        np.isfinite(features).all(axis=1)
        & (features >= lower).all(axis=1)
        & (features <= upper).all(axis=1)
    )


def predict_actions(model, features):
    """Refuse out-of-domain features; predictions alone cannot authorize flagging."""
    features = np.asarray(features, float)
    if features.ndim != 2 or features.shape[1] != len(model["feature_names"]):
        raise ValueError("fixed action feature matrix required")
    inside = _domain(model, features)
    predictions = np.full(len(features), np.nan)
    design = np.column_stack(
        (
            np.ones(int(inside.sum())),
            (features[inside] - model["center"]) / np.array(model["scale"]),
        )
    )
    predictions[inside] = design @ np.array(model["coefficients"])
    return predictions, {
        "refused_indices": np.flatnonzero(~inside).tolist(),
        "reason": "outside TRAIN feature envelope; no-change/refuse",
        "deployment_requires_actual_guarded_confirmation": True,
    }


def fit_grouped_ridge(features, targets, groups, split, *, penalties=PENALTIES):
    """TRAIN fitting/normalization and validation tuning; never inspect test labels."""
    features, targets = np.asarray(features, float), np.asarray(targets, float)
    groups = np.asarray(groups, str)
    if (
        features.ndim != 2
        or features.shape[1] != len(FEATURE_NAMES)
        or targets.shape != (len(features),)
        or groups.shape != targets.shape
        or np.any(groups == "")
        or not np.isfinite(features).all()
        or tuple(penalties) != PENALTIES
    ):
        raise ValueError("finite fixed features, groups and frozen penalties required")
    split = _partition(split, groups, len(features))
    train = split["train"][np.isfinite(targets[split["train"]])]
    validation = split["validation"][np.isfinite(targets[split["validation"]])]
    if len(train) < 3 or not len(validation):
        raise ValueError("insufficient guarded TRAIN/validation labels")
    weights = _weights(groups[train])
    center = np.sum(features[train] * weights[:, None], axis=0)
    std = np.sqrt(np.sum((features[train] - center) ** 2 * weights[:, None], axis=0))
    scale = np.maximum(std, 1e-12)
    padding = np.where(std > 1e-12, 3 * std, 1e-8)
    lower, upper = (
        features[train].min(axis=0) - padding,
        features[train].max(axis=0) + padding,
    )
    model = {
        "feature_names": list(FEATURE_NAMES),
        "center": center.tolist(),
        "scale": scale.tolist(),
        "domain_lower": lower.tolist(),
        "domain_upper": upper.tolist(),
        "supported_train_actions": len(train),
        "missing_labels_train": len(split["train"]) - len(train),
        "domain": "MeerKAT L band; frozen whole-rectangle TRAIN-only semantics",
        "label": "baseline_guarded_objective - actual_candidate_guarded_objective",
    }
    inside = _domain(model, features[validation])
    validation = validation[inside]
    if not len(validation):
        raise ValueError("no supported in-domain validation labels; refuse fit")
    valweights = _weights(groups[validation])

    def design(indices):
        return np.column_stack(
            (np.ones(len(indices)), (features[indices] - center) / scale)
        )

    xtrain, xval = design(train), design(validation)
    regularizer = np.eye(xtrain.shape[1])
    regularizer[0, 0] = 0
    trials = []
    for penalty in PENALTIES:
        coefficients = np.linalg.solve(
            xtrain.T @ (weights[:, None] * xtrain) + penalty * regularizer,
            xtrain.T @ (weights * targets[train]),
        )
        predictions = xval @ coefficients
        mse = float(np.sum(valweights * (predictions - targets[validation]) ** 2))
        trials.append((mse, penalty, coefficients, predictions))
    mse, penalty, coefficients, valpredictions = min(
        trials, key=lambda trial: trial[:2]
    )
    model.update(
        {
            "coefficients": coefficients.tolist(),
            "ridge_penalty": penalty,
            "validation_group_MSE": mse,
            "tuning": [
                {"penalty": p, "validation_group_MSE": m} for m, p, _, _ in trials
            ],
            "optimism_margin": max(
                float(np.quantile(valpredictions - targets[validation], 0.9)), 0
            ),
            "minimum_predicted_benefit": 1e-6,
            "training_mean_constant": float(np.sum(weights * targets[train])),
            "missing_labels_validation": int(
                np.count_nonzero(~np.isfinite(targets[split["validation"]]))
            ),
            "validation_domain_refusals": int(np.count_nonzero(~inside)),
            "test_labels_used_for_fitting_or_selection": False,
        }
    )
    return model, predict_actions(model, features)[0]


def rank_predictions(mask_ids, predictions):
    """Stable feature-only ranking; an empty ranking means no-change/refusal."""
    if len(mask_ids) != len(predictions) or len(set(mask_ids)) != len(mask_ids):
        raise ValueError("unique mask IDs with matched predictions required")
    return sorted(
        (i for i, value in enumerate(predictions) if np.isfinite(value)),
        key=lambda i: (-predictions[i], mask_ids[i]),
    )


def _evaluate(indices, targets, predictions, groups, constant):
    supported = indices[
        np.isfinite(targets[indices]) & np.isfinite(predictions[indices])
    ]
    result = {
        "actions": len(indices),
        "missing_guarded_labels": int(np.count_nonzero(~np.isfinite(targets[indices]))),
        "domain_refusals": int(np.count_nonzero(~np.isfinite(predictions[indices]))),
        "evaluated": len(supported),
    }
    if not len(supported):
        return {**result, "group_MSE": None, "constant_group_MSE": None}
    weights = _weights(groups[supported])
    pred, actual = predictions[supported], targets[supported]
    error = pred - actual
    variance = float(np.sum(weights * (pred - np.sum(weights * pred)) ** 2))
    result.update(
        {
            "group_MSE": float(np.sum(weights * error**2)),
            "constant_group_MSE": float(np.sum(weights * (constant - actual) ** 2)),
            "mean_prediction_bias": float(np.sum(weights * error)),
            "calibration_slope": float(
                np.sum(
                    weights
                    * (pred - np.sum(weights * pred))
                    * (actual - np.sum(weights * actual))
                )
                / variance
            )
            if variance > 1e-20
            else None,
        }
    )
    return result


def run(run_dir, cases_path):
    """Retrospective fitted-model run on fresh outputs, with immutable inputs."""
    cases_path = Path(cases_path).resolve()
    run_dir = Path(run_dir).resolve()
    if cases_path == run_dir or run_dir in cases_path.parents:
        raise ValueError("output must not contain the input manifest")
    specification = json.loads(cases_path.read_text())
    cases = specification["cases"] if isinstance(specification, dict) else specification
    cases = [dict(case) for case in cases]
    for case in cases:
        if "run_dir" not in case and "result_path" in case:
            path = Path(case["result_path"])
            if path.name != "result.json":
                raise ValueError("completed source result.json required")
            case["run_dir"] = str(path.parent)
        if "seed" in case:
            key = {101: "train", 103: "validation", 105: "test"}.get(case["seed"])
            if key is None:
                raise ValueError("frozen new seed101/103/105 cases required")
            case.setdefault("split", key)
            case.setdefault("group_id", f"seed{case['seed']}")
    if not cases or len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("unique completed case specifications required")
    sources = [Path(case["run_dir"]).resolve() for case in cases]
    if len(set(sources)) != len(sources):
        raise ValueError("source case reused across splits")
    for source in sources:
        reject_nested_paths(run_dir, source)
    rows, features, labels, provenance, observations = [], [], [], [], set()
    split = {key: [] for key in SPLITS}
    groups = []
    for case, source in zip(cases, sources):
        if case["split"] not in SPLITS or not case["group_id"]:
            raise ValueError("fixed split and case/scan group IDs required")
        if (
            "seed" in case
            and {101: "train", 103: "validation", 105: "test"}.get(case["seed"])
            != case["split"]
        ):
            raise ValueError("new seed101/103/105 grouping is frozen")
        result_path, manifest_path = source / "result.json", source / "manifest.json"
        result_bytes, manifest_bytes = (
            result_path.read_bytes(),
            manifest_path.read_bytes(),
        )
        result, manifest = json.loads(result_bytes), json.loads(manifest_bytes)
        original_observation = validate_source_domain(manifest)
        if not result.get("audit") or not all(result["audit"].values()):
            raise ValueError("completed source preservation audit required")
        baseline_record = result["baseline"]
        baseline = baseline_record["metrics"]
        observation = case.get("observation_id", original_observation)
        observations.add(original_observation)
        provenance.append(
            {
                "case_id": case["case_id"],
                "run_dir": str(source),
                "split": case["split"],
                "group_id": case["group_id"],
                "observation_id": observation,
                "original_source_digest": original_observation,
                "result_sha256": sha256(result_bytes).hexdigest(),
                "manifest_sha256": sha256(manifest_bytes).hexdigest(),
                "actual_source_solves": result["actual_solve_count"],
            }
        )
        for action in result["actions"]:
            candidate = action["candidate"]
            index = len(rows)
            split[case["split"]].append(index)
            groups.append(case["group_id"])
            features.append(candidate_features(candidate, baseline))
            labels.append(guarded_benefit(action, baseline_record))
            rows.append(
                {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "mask_id": action["mask_id"],
                    "source_guard_pass": action.get("guard_pass", False),
                }
            )
    features, targets, groups = np.array(features), np.array(labels), np.array(groups)
    split = {key: np.array(indices, dtype=int) for key, indices in split.items()}
    _partition(split, groups, len(rows))
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        run_dir / "config.json",
        {
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "cases_manifest_sha256": sha256(cases_path.read_bytes()).hexdigest(),
            "sources": provenance,
            "ridge_penalties": PENALTIES,
            "new_QuartiCal_solves": 0,
            "no_original_MS_flags_DATA_or_weights_written": True,
        },
    )
    start = time.monotonic()
    model, predictions = fit_grouped_ridge(features, targets, groups, split)
    fit_seconds = time.monotonic() - start
    forecasts = []
    for case in cases:
        indices = [i for i, row in enumerate(rows) if row["case_id"] == case["case_id"]]
        ids = [rows[i]["mask_id"] for i in indices]
        order = rank_predictions(ids, predictions[indices])
        chosen = None
        if (
            order
            and predictions[indices[order[0]]] - model["optimism_margin"]
            > model["minimum_predicted_benefit"]
        ):
            chosen = ids[order[0]]
        forecasts.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "predicted_ranking": [ids[i] for i in order],
                "predictions": {
                    ids[j]: float(predictions[i])
                    if np.isfinite(predictions[i])
                    else None
                    for j, i in enumerate(indices)
                },
                "feature_only_recommendation": chosen,
                "no_change": chosen is None,
                "selected_or_exported_flags": False,
                "test_prediction_only": case["split"] == "test",
            }
        )
    # Freeze all feature-only decisions before any evaluation of test labels.
    write_json(run_dir / "model.json", model)
    write_json(run_dir / "frozen-predictions.json", forecasts)
    np.savez_compressed(
        run_dir / "dataset.npz",
        features=features,
        targets=targets,
        groups=groups,
        **split,
    )
    evaluation = {
        key: _evaluate(
            indices, targets, predictions, groups, model["training_mean_constant"]
        )
        for key, indices in split.items()
    }
    rank_diagnostics = []
    for forecast in forecasts:
        indices = np.array(
            [i for i, row in enumerate(rows) if row["case_id"] == forecast["case_id"]]
        )
        supported = indices[
            np.isfinite(targets[indices]) & np.isfinite(predictions[indices])
        ]
        inversions, pairs = 0, 0
        for j, left in enumerate(supported):
            for right in supported[j + 1 :]:
                actual = targets[left] - targets[right]
                if actual != 0:
                    pairs += 1
                    inversions += (predictions[left] - predictions[right]) * actual < 0
        chosen = forecast["feature_only_recommendation"]
        chosen_value = (
            0.0
            if chosen is None
            else next(targets[i] for i in indices if rows[i]["mask_id"] == chosen)
        )
        available = targets[indices][np.isfinite(targets[indices])]
        rank_diagnostics.append(
            {
                "case_id": forecast["case_id"],
                "rank_inversion_fraction": float(inversions / pairs) if pairs else None,
                "supported_rank_pairs": pairs,
                "retrospective_objective_regret": float(
                    max(0, max(available)) - chosen_value
                )
                if len(available) and np.isfinite(chosen_value)
                else None,
                "unsupported_recommendation": chosen is not None
                and not np.isfinite(chosen_value),
                "diagnostics_only_never_select": True,
            }
        )
    unchanged = all(
        sha256((Path(p["run_dir"]) / "result.json").read_bytes()).hexdigest()
        == p["result_sha256"]
        and sha256((Path(p["run_dir"]) / "manifest.json").read_bytes()).hexdigest()
        == p["manifest_sha256"]
        for p in provenance
    )
    if not unchanged:
        raise RuntimeError("source outcome artifacts changed during model fitting")
    result = {
        "model": model,
        "forecasts": forecasts,
        "evaluation": evaluation,
        "rank_diagnostics": rank_diagnostics,
        "sources": provenance,
        "cost": {
            "fitting_seconds": fit_seconds,
            "new_QC_solves": 0,
            "source_actual_solves": sum(p["actual_source_solves"] for p in provenance),
            "native_runtime_comparison": False,
        },
        "audit": {
            "source_results_and_manifests_unchanged": unchanged,
            "test_never_fit_or_tune": True,
            "predictions_frozen_before_test_diagnostics": True,
            "no_truth_decoded_or_used": True,
            "no_flags_exported": True,
        },
        "distinct_observation_count": len(observations),
        "original_observation_digests": sorted(observations),
        "same_original_scan_across_splits": len(observations) == 1,
        "independent_observation_generalization_established": False,
        "limitations": "Fitted retrospective guarded-benefit estimator, not deployed flagging. Reused within-scan seeded cases are not independent-observation tests. Unsupported counterfactuals are missing, not zero. TRAIN-envelope refusals and all nulls retained; recommendations need fresh full2x2 guarded confirmation. No imaging, flux/signal preservation, SOTA or native-cost advantage established.",
    }
    write_json(run_dir / "result.json", result)
    return str(run_dir / "result.json")
