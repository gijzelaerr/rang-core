"""The patch-removal actions stage on the Rust core (research/core-phase3-actions.md).

Replays `flagging_actions.run` with `core_workflow.core_solve`. Candidate
patches, the action split, the ridge fit and the proposal are the same
functions; targets, objective and acceptance use the same arithmetic. It
starts from a prepared state and writes one result.json; no Measurement Set is
copied or written.
"""

import json
import time
from pathlib import Path

import numpy as np

from .core_workflow import core_solve, solve_flags
from .flagging import fixed_support_tv
from .flagging_actions import (
    candidate_patches,
    fit_action_model,
    proposal_from_model,
    split_actions,
)
from .flagging_workflow import load_state


def _json_default(value):
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def run(run_dir, prepared_dir, seed=29, action_count=16, iterations=50):
    """Core-native counterfactual patch-removal experiment."""
    started = time.perf_counter()
    run_dir, prepared = Path(run_dir), Path(prepared_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    state = load_state(prepared)
    manifest = json.loads((prepared / "manifest.json").read_text())
    time_interval, freq_interval = manifest["split_gain_intervals"]
    state["action_intervals"] = np.array([time_interval, freq_interval])
    configuration = {
        "seed": seed,
        "action_count": action_count,
        "iterations": iterations,
        "ridge_penalties": [0.1, 1, 10],
        "prepared_input": str(prepared),
        "solver": "rang core port of QuartiCal 0.2.7 complex (research/core-phase2.md)",
    }
    zero = np.zeros_like(state["train"])
    settings = (time_interval, freq_interval, iterations)
    baseline, base_tv, residuals, guidance, _ = core_solve(
        state, zero, *settings, trial="baseline"
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
            metrics, tv, _, _, _ = core_solve(
                state, added, *settings, trial=trial, scale=baseline["scale"]
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
    model, predictions = fit_action_model(features, targets, split)
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
        metrics, tv, _, _, _ = core_solve(
            state,
            proposed,
            *settings,
            trial="learned-proposal",
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
    final_flags, final_rows = solve_flags(state, selected_mask, holdout=False)
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
    result = {
        "configuration": configuration,
        "baseline": baseline,
        "actions": records,
        "action_split": {key: value.tolist() for key, value in split.items()},
        "learned_proposal": proposal,
        "selected": selected,
        "model": model,
        "audit": {
            "original_flags_preserved": bool(
                np.all(final_flags[state["original_flags"]])
                and np.all(final_rows[state["original_rows"]])
            ),
            "holdout_additions": int(np.count_nonzero(selected_mask & ~state["train"])),
        },
        "seconds_total": time.perf_counter() - started,
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=1, allow_nan=False, default=_json_default) + "\n"
    )
    result["actual_QC_solves"] = 1 + len(records) + (proposal is not None)
    return result
