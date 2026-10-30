"""Measure patch-removal effects and fit a small gain-TV action predictor.

This is a black-box counterfactual pilot, not a differentiable QuartiCal solver
or an independent-observation generalization result. All visibility features
come from the training split. Action labels are measured by actual full-Jones
re-solves; test-action labels never fit or select the model.
"""

import json
import shutil
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import flagging_prepared
from .flagging import (
    assert_preserved,
    fixed_support_tv,
    residual_features,
    snapshot_flags,
)
from .flagging_workflow import (
    load_state,
    prepare,
    set_flags,
    solve,
    tree_digest,
    write_json,
)

FEATURE_NAMES = [
    "log_sample_count",
    "median_residual_z",
    "p95_residual_z",
    "max_residual_z",
    "median_relative_tv",
    "max_relative_tv",
    "mean_log_whitened_amplitude",
    "std_log_whitened_amplitude",
]


def candidate_patches(state, residuals, guidance, count=16, *, seed=29):
    """Disjoint baseline x gain-time x gain-frequency training patches.

    Cover the joint residual/TV score range rather than only high-TV patches.
    Never read validation/test residuals to construct or describe an action.
    """
    if count < 6:
        raise ValueError("at least six actions required for train/validation/test")
    train = state["train"]
    if residuals.shape != state["data"].shape or guidance.shape != train.shape:
        raise ValueError("visibility feature shapes differ")
    time_interval, freq_interval = state["action_intervals"]
    time_bins = np.unique(state["times"], return_inverse=True)[1] // time_interval
    freq_bins = np.arange(train.shape[1]) // freq_interval
    n_ant = len(state["names"])
    baseline = state["antenna1"] * n_ant + state["antenna2"]
    groups = (
        time_bins[:, None] * (freq_bins.max() + 1) + freq_bins[None]
    ) * n_ant**2 + baseline[:, None]
    whitened = residuals * np.sqrt(state["weights"])
    z = residual_features(whitened, train, state["antenna1"], state["antenna2"])
    amplitude = np.sqrt(np.sum(np.abs(whitened) ** 2, axis=-1))
    positive = guidance[train & np.isfinite(guidance) & (guidance > 0)]
    tv_scale = np.median(positive) if len(positive) else 1.0
    relative_tv = guidance / max(tv_scale, 1e-30)
    indices = np.flatnonzero(train)
    indices = indices[np.argsort(groups.flat[indices], kind="stable")]
    _, starts = np.unique(groups.flat[indices], return_index=True)
    patches = []
    for cells in np.split(indices, starts[1:]):
        # A fixed metadata-only size guard excludes negligible/sparse actions.
        if len(cells) < 8:
            continue
        local_z, local_tv = z.flat[cells], relative_tv.flat[cells]
        local_amp = np.log(np.maximum(amplitude.flat[cells], 1e-30))
        features = np.array(
            [
                np.log1p(len(cells)),
                np.median(local_z),
                np.quantile(local_z, 0.95),
                np.max(local_z),
                np.median(local_tv),
                np.max(local_tv),
                np.mean(local_amp),
                np.std(local_amp),
            ]
        )
        if not np.isfinite(features).all():
            continue
        row, channel = np.unravel_index(cells[0], train.shape)
        patches.append(
            {
                "indices": cells,
                "features": features,
                "time_bin": int(time_bins[row]),
                "frequency_bin": int(freq_bins[channel]),
                "antenna1": int(state["antenna1"][row]),
                "antenna2": int(state["antenna2"][row]),
                "score": float(features[2] * (1 + features[4])),
            }
        )
    if len(patches) < count:
        raise ValueError(f"only {len(patches)} eligible disjoint patches, need {count}")
    # Seed controls ties without introducing another feature-selection trial.
    rng = np.random.default_rng(seed)
    permutation = rng.permutation(len(patches))
    order = permutation[
        np.argsort([patches[i]["score"] for i in permutation], kind="stable")
    ]
    chosen = np.rint(np.linspace(0, len(order) - 1, count)).astype(int)
    return [patches[i] for i in order[chosen]]


def split_actions(count, seed=29):
    if count < 6:
        raise ValueError("at least six disjoint actions required")
    order = np.random.default_rng(seed).permutation(count)
    reserved = max(1, count // 5)
    return {
        "train": order[2 * reserved :],
        "validation": order[reserved : 2 * reserved],
        "test": order[:reserved],
    }


def fit_action_model(features, targets, split, *, penalties=(0.1, 1.0, 10.0)):
    """Ridge model predicting normalized fixed-support TV change.

    Standardization uses train actions only, ridge selection validation actions
    only. Missing labels are counted explicitly and never replaced by zero.
    """
    features, targets = np.asarray(features, float), np.asarray(targets, float)
    if (
        features.ndim != 2
        or targets.shape != (len(features),)
        or not np.isfinite(features).all()
        or not penalties
        or not np.isfinite(penalties).all()
        or min(penalties) <= 0
    ):
        raise ValueError("finite features and positive ridge penalties required")
    combined = np.concatenate([np.asarray(split[key]) for key in split])
    if len(combined) != len(features) or not np.array_equal(
        np.sort(combined), np.arange(len(features))
    ):
        raise ValueError("action splits must be a disjoint exhaustive partition")
    valid = np.isfinite(targets)
    train = np.asarray(split["train"])[valid[split["train"]]]
    validation = np.asarray(split["validation"])[valid[split["validation"]]]
    if len(train) < 3 or len(validation) < 1:
        raise ValueError("insufficient supported train/validation action labels")
    center = np.mean(features[train], axis=0)
    scale = np.maximum(np.std(features[train], axis=0), 1e-12)
    design = np.column_stack((np.ones(len(features)), (features - center) / scale))
    regularizer = np.eye(design.shape[1])
    regularizer[0, 0] = 0
    trials = []
    for penalty in penalties:
        coefficients = np.linalg.solve(
            design[train].T @ design[train] + penalty * regularizer,
            design[train].T @ targets[train],
        )
        predictions = design @ coefficients
        mse = float(np.mean((predictions[validation] - targets[validation]) ** 2))
        trials.append((mse, float(penalty), coefficients, predictions))
    mse, penalty, coefficients, predictions = min(trials, key=lambda item: item[:2])
    return {
        "feature_names": FEATURE_NAMES,
        "center": center.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "ridge_penalty": penalty,
        "validation_action_mse": mse,
        "tuning": [{"penalty": p, "validation_mse": m} for m, p, _, _ in trials],
        "missing_labels": {
            key: int(np.count_nonzero(~valid[indices]))
            for key, indices in split.items()
        },
    }, predictions


def proposal_from_model(
    patches, predictions, training_actions, shape, train_count, *, max_fraction=0.02
):
    """Choose only model-training actions; untouched test labels stay diagnostic.

    Penalize additional flags and retain the no-change action. A union requires
    a fresh solve because individual counterfactual effects need not add.
    """
    if not np.isfinite(predictions).all() or not 0 <= max_fraction < 1:
        raise ValueError("finite predictions and fraction below one required")
    mask = np.zeros(shape, bool)
    selected = []
    scores = [
        (float(predictions[i]) + 2 * len(patches[i]["indices"]) / train_count, int(i))
        for i in training_actions
    ]
    for score, index in sorted(scores):
        if score >= 0:
            continue
        cells = patches[index]["indices"]
        if np.count_nonzero(mask) + len(cells) > int(max_fraction * train_count):
            continue
        mask.flat[cells] = True
        selected.append(index)
    return mask, selected


def run(
    run_dir,
    archive=None,
    prepared_dir=None,
    seed=29,
    action_count=16,
    iterations=50,
):
    """Fresh real-MS counterfactual experiment, callable from Stimela2."""
    run_dir = Path(run_dir).resolve()
    if bool(archive) == bool(prepared_dir):
        raise ValueError("supply exactly one of archive or prepared_dir")
    prepared_digest = None
    if archive:
        prepare(run_dir, archive=archive, seed=7)
    else:
        run_dir, prepared_dir = flagging_prepared.reject_nested_paths(
            run_dir, prepared_dir
        )
        prepared_digest = tree_digest(prepared_dir)
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in ("state.npz", "manifest.json"):
            shutil.copy2(prepared_dir / name, run_dir / name)
        for name in ("original.ms", "work.ms"):
            shutil.copytree(prepared_dir / name, run_dir / name)
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    boundary = flagging_prepared.validate_prepared_state(run_dir, state, manifest)
    if prepared_dir:
        snapshot_flags(
            run_dir / "backups/original-flags.npz",
            state["original_flags"],
            state["original_rows"],
        )
    time_interval, freq_interval = manifest["split_gain_intervals"]
    state["action_intervals"] = np.array([time_interval, freq_interval])
    write_json(
        run_dir / "action-config.json",
        {
            "seed": seed,
            "action_count": action_count,
            "iterations": iterations,
            "prepared_input": str(prepared_dir) if prepared_dir else None,
            "prepared_input_digest": prepared_digest,
            "prepared_boundary": boundary,
            "boundary_module_sha256": sha256(
                Path(flagging_prepared.__file__).read_bytes()
            ).hexdigest(),
            "ridge_penalties": [0.1, 1, 10],
            "feature_source": "training visibilities and training-only solved gains",
            "target": "(fixed_support_TV(action)-TV(baseline))/TV(baseline)",
            "timing": "Linux amd64 emulation on macOS ARM; not native performance",
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "limitations": "Single reference-pointing scan; action holdouts are not independent observations. Prepared input may contain documented injections, whose truth is never read by this learner. No imaging or flux validation.",
        },
    )
    zero = np.zeros_like(state["train"])
    baseline, base_tv, residuals, guidance = solve(
        run_dir,
        state,
        manifest,
        zero,
        "baseline",
        time_interval,
        freq_interval,
        iterations,
    )
    if (
        fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None
        or baseline["losses"]["validation"] is None
    ):
        raise ValueError("unsupported baseline TV or heldout predictions")
    patches = candidate_patches(state, residuals, guidance, action_count, seed=seed)
    split = split_actions(len(patches), seed)
    features = np.array([patch["features"] for patch in patches])
    targets = np.full(len(patches), np.nan)
    records = []
    denominator = max(baseline["tv"], 1e-30)
    np.savez_compressed(
        run_dir / "backups/action-definitions.npz",
        features=features,
        **{f"action_{i}": patch["indices"] for i, patch in enumerate(patches)},
        **{f"split_{key}": value for key, value in split.items()},
    )
    for index, patch in enumerate(patches):
        added = np.zeros_like(zero)
        added.flat[patch["indices"]] = True
        trial = f"action-{index:03d}"
        metadata = {
            key: value
            for key, value in patch.items()
            if key not in ("indices", "features")
        }
        metadata["sample_count"] = len(patch["indices"])
        try:
            metrics, tv, _, _ = solve(
                run_dir,
                state,
                manifest,
                added,
                trial,
                time_interval,
                freq_interval,
                iterations,
                scale=baseline["scale"],
            )
            fixed_tv = fixed_support_tv(tv["edges"], base_tv["edges"])
            if fixed_tv is not None:
                targets[index] = (fixed_tv - baseline["tv"]) / denominator
            record = {
                **metrics,
                "action": metadata,
                "fixed_support_tv": fixed_tv,
                "normalized_tv_change": float(targets[index])
                if np.isfinite(targets[index])
                else None,
            }
        except RuntimeError as error:
            record = {"trial": trial, "action": metadata, "error": str(error)}
        records.append(record)
        write_json(run_dir / f"checkpoint-action-{index:03d}.json", record)
    model, predictions = fit_action_model(features, targets, split)
    # Test-action labels do not enter fitting, tuning or mask selection.
    proposed, chosen = proposal_from_model(
        patches,
        predictions,
        split["train"],
        zero.shape,
        np.count_nonzero(state["train"]),
    )
    selected, selected_mask, accepted = baseline, zero, False
    proposal = None
    if proposed.any():
        metrics, tv, _, _ = solve(
            run_dir,
            state,
            manifest,
            proposed,
            "learned-proposal",
            time_interval,
            freq_interval,
            iterations,
            scale=baseline["scale"],
        )
        fixed_tv = fixed_support_tv(tv["edges"], base_tv["edges"])
        val, val0 = metrics["losses"]["validation"], baseline["losses"]["validation"]
        admissible = fixed_tv is not None and val is not None and val <= 1.01 * val0
        objective = (
            fixed_tv / denominator
            + 2 * metrics["added_fraction"]
            + 0.25 * val / max(val0, 1e-30)
            if admissible
            else None
        )
        objective0 = baseline["tv"] / denominator + 0.25
        accepted = bool(admissible and objective < objective0)
        proposal = {
            **metrics,
            "fixed_support_tv": fixed_tv,
            "objective": objective,
            "accepted": accepted,
        }
        if accepted:
            selected, selected_mask = metrics, proposed
    set_flags(run_dir, state, selected_mask, "final", holdout=False)
    shutil.copytree(run_dir / "work.ms", run_dir / "flagged.ms")
    from casacore.tables import table

    with table(str(run_dir / "flagged.ms"), readonly=True, ack=False) as final:
        assert_preserved(
            state["original_flags"],
            state["original_rows"],
            final.getcol("FLAG"),
            final.getcol("FLAG_ROW"),
        )
        data_unchanged = bool(
            np.array_equal(state["data"], final.getcol("DATA"), equal_nan=True)
        )
        final_weights = (
            final.getcol("WEIGHT_SPECTRUM")
            if "WEIGHT_SPECTRUM" in final.colnames()
            else np.broadcast_to(
                final.getcol("WEIGHT")[:, None], state["weights"].shape
            )
        )
        weights_unchanged = bool(
            np.array_equal(state["weights"], final_weights, equal_nan=True)
        )
    original_unchanged = (
        tree_digest(run_dir / "original.ms")
        == manifest["source_digest"]
        == tree_digest(Path(manifest["source"]))
    )
    prepared_unchanged = (
        tree_digest(prepared_dir) == prepared_digest if prepared_dir else True
    )
    if not (
        data_unchanged
        and weights_unchanged
        and original_unchanged
        and prepared_unchanged
    ):
        raise RuntimeError("observation preservation audit failed")
    # Evaluation after selecting the model/mask; no test labels choose any setting.
    test = split["test"]
    valid_test = test[np.isfinite(targets[test])]
    test_mse = (
        float(np.mean((predictions[valid_test] - targets[valid_test]) ** 2))
        if len(valid_test)
        else None
    )
    train_targets = targets[split["train"]]
    supported_train = train_targets[np.isfinite(train_targets)]
    constant = float(np.mean(supported_train))
    model.update(
        {
            "kind": "ridge predictor of measured patch-removal gain-TV change",
            "predicted_changes": predictions.tolist(),
            "selected_training_actions": chosen,
            "proposal_accepted": accepted,
            "no_change": not accepted,
            "transfer_validated": False,
            "test_action_mse": test_mse,
            "constant_predictor_test_mse": float(
                np.mean((constant - targets[valid_test]) ** 2)
            )
            if len(valid_test)
            else None,
        }
    )
    write_json(run_dir / "model.json", model)
    write_json(
        run_dir / "result.json",
        {
            "baseline": baseline,
            "actions": records,
            "action_split": {key: value.tolist() for key, value in split.items()},
            "learned_proposal": proposal,
            "selected": selected,
            "model": model,
            "audit": {
                "original_flags_preserved": True,
                "original_unchanged": original_unchanged,
                "final_data_unchanged": data_unchanged,
                "prepared_input_unchanged": prepared_unchanged,
                "final_native_weights_unchanged": weights_unchanged,
                "holdout_additions": int(
                    np.count_nonzero(selected_mask & ~state["train"])
                ),
            },
            "limitations": "Counterfactual actions on one approximate-model pointing scan. Missing action labels are reported; no test-action labels select the policy. No independent-scan transfer, injected-RFI, image or flux validation in this branch.",
        },
    )
