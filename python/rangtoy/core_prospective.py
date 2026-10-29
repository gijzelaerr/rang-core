"""The prospective track on the Rust core (research/core-phase3b.md).

Replays `flagging_prospective.run` with `core_workflow.core_solve`. The
shortlist, TRAIN-only forecasts, validation scoring, confirmation choice and
action selection are the same functions in the same order; every forecast is
frozen in memory before any action is measured. No Measurement Set is copied
or written: the final physics mask is checked as an array instead.
"""

import json
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .core_workflow import core_solve, solve_flags
from .flagging import fixed_support_tv
from .flagging_caracal import score_control
from .flagging_prospective import (
    MARGIN,
    SEEDS,
    _freeze_view,
    forecast_family,
    make_shortlist,
    score_forecasts,
)
from .flagging_structured import _compact, choose_action
from .flagging_workflow import load_state

CASE_IDS = ("clean", "time-burst-seed107", "time-burst-seed109")


def _json_default(value):
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def run(run_dir, inputs_dir, iterations=50):
    """Three core baselines, every shortlisted action, frozen forecasts first."""
    if type(iterations) is not int or iterations != 50:
        raise ValueError("frozen 50-iteration solve required")
    started = time.perf_counter()
    run_dir, source = Path(run_dir), Path(inputs_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    config = {
        "input_source": str(source),
        "iterations": iterations,
        "grid": [2, 32],
        "maximum_action_confirmations": 2,
        "maximum_actual_QC_solves": 75,
        "minimum_benefit": MARGIN,
        "test_or_truth_selects": False,
        "solver": "rang core port of QuartiCal 0.2.7 complex (research/core-phase2.md)",
        "seeds": list(SEEDS),
    }
    prepared = {}
    for case_id in CASE_IDS:
        directory = source / "cases" / case_id
        state = load_state(directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        if (
            manifest["split_gain_intervals"] != [2, 32]
            or manifest["scope"]["telescope"].casefold() != "meerkat"
            or manifest["scope"]["band"] != "L"
        ):
            raise ValueError("MeerKAT L-band native 2x32 required")
        zero = np.zeros_like(state["train"])
        metrics, tv, residual, guidance, baseline = core_solve(
            state, zero, 2, 32, iterations, trial="baseline"
        )
        if not score_control(
            metrics, fixed_support_tv(tv["edges"], tv["edges"]), metrics
        )["guard_pass"]:
            raise ValueError("baseline unavailable")
        candidates, rankings, stats = make_shortlist(
            state, baseline, metrics, residual, guidance
        )
        if len(candidates) > 24 or len({x["mask_id"] for x in candidates}) != len(
            candidates
        ):
            raise ValueError("shortlist must contain <=24 distinct masks")
        forecast = forecast_family(state, baseline, metrics, candidates)
        prepared[case_id] = {
            "directory": directory,
            "state": state,
            "metrics": metrics,
            "baseline": baseline,
            "candidates": candidates,
            "rankings": rankings,
            "stats": stats,
            "forecast": forecast,
            "frozen_train_responses_sha256": sha256(
                json.dumps(
                    _freeze_view(forecast), sort_keys=True, default=_json_default
                ).encode()
            ).hexdigest(),
        }
    if 3 + sum(len(c["candidates"]) for c in prepared.values()) > 75:
        raise ValueError("campaign cannot exceed 75 solves")
    # Every TRAIN forecast from every case exists before any forecast VAL score.
    for case in prepared.values():
        score_forecasts(case["state"], case["forecast"])
        positive = [
            x
            for x in case["forecast"]["records"]
            if x["guard_pass"] and x.get("predicted_benefit", -np.inf) > MARGIN
        ]
        positive.sort(
            key=lambda x: (
                x["predicted_objective"],
                x["candidate"]["added_fraction"],
                x["mask_id"],
            )
        )
        case["confirm_ids"] = [x["mask_id"] for x in positive[:2]]
    results, margins = [], {}
    for case_id, case in prepared.items():
        state, metrics = case["state"], case["metrics"]
        records = []
        for i, candidate in enumerate(case["candidates"]):
            added = np.zeros_like(state["train"])
            added.flat[candidate["indices"]] = True
            record = {"mask_id": candidate["mask_id"], "candidate": _compact(candidate)}
            try:
                actual, tv, _, _, _ = core_solve(
                    state,
                    added,
                    2,
                    32,
                    iterations,
                    trial=f"prospective-{i:03d}",
                    scale=metrics["scale"],
                )
                fixed = fixed_support_tv(tv["edges"], case["baseline"]["edges"])
                record.update(
                    metrics=actual,
                    fixed_support_tv=fixed,
                    **score_control(actual, fixed, metrics),
                )
            except RuntimeError as error:
                record.update(error=str(error), guard_pass=False)
            records.append(record)

        def choose(ids, records=records):
            return choose_action(records, ids, 1.25 - MARGIN)

        selected = {
            mode: choose([x["mask_id"] for x in items])
            for mode, items in case["rankings"].items()
        }
        selected["physics_two_confirmation"] = choose(case["confirm_ids"])
        selected["full_union_reference"] = choose(
            [x["mask_id"] for x in case["candidates"]]
        )
        truth = None
        if (case["directory"] / "injection.npz").exists():
            with np.load(case["directory"] / "injection.npz") as saved:
                truth = saved["injected"]
        masks, diagnostics = {}, {}
        for mode, winner in selected.items():
            mask = np.zeros_like(state["train"])
            if winner is not None:
                mask.flat[
                    next(
                        x["indices"]
                        for x in case["candidates"]
                        if x["mask_id"] == winner
                    )
                ] = True
            masks[mode] = mask
            record = next((x for x in records if x["mask_id"] == winner), None)
            diagnostics[mode] = {
                "mask_id": winner,
                "no_change": winner is None,
                "objective": 1.25 if record is None else record["objective"],
                "test_MSE": metrics["losses"]["test"]
                if record is None
                else record["metrics"]["losses"]["test"],
                "flags_added": int(mask.sum()),
                "known_injection_recall": None
                if truth is None
                else float((mask & truth).sum() / truth.sum()),
                "outside_known_injection": None
                if truth is None
                else int((mask & ~truth).sum()),
            }
        final_flags, final_rows = solve_flags(
            state, masks["physics_two_confirmation"], holdout=False
        )
        audit = {
            "original_flags_preserved": bool(
                np.all(final_flags[state["original_flags"]])
                and np.all(final_rows[state["original_rows"]])
            ),
            "additions_only_on_train": bool(
                not np.any(masks["physics_two_confirmation"] & ~state["train"])
            ),
            "final_flags_sha256": sha256(final_flags.tobytes()).hexdigest(),
        }
        margins[case_id] = {
            "forecast_benefit_minus_margin": [
                {
                    "mask_id": r["mask_id"],
                    "value": r["predicted_benefit"] - MARGIN
                    if r.get("predicted_benefit") is not None
                    else None,
                }
                for r in case["forecast"]["records"]
            ],
            "action_threshold_minus_objective": [
                {
                    "mask_id": r["mask_id"],
                    "value": (1.25 - MARGIN) - r["objective"]
                    if r.get("objective") is not None
                    else None,
                }
                for r in records
            ],
        }
        results.append(
            {
                "case_id": case_id,
                "baseline": metrics,
                "forecasts": case["forecast"]["records"],
                "confirmation_ids": case["confirm_ids"],
                "actions": records,
                "selected": diagnostics,
                "audit": audit,
                "actual_QC_solves": 1 + len(records),
                "future_two_confirmation_QC_solves": 1 + len(case["confirm_ids"]),
                "reference_union_is_diagnostic": True,
                "frozen_train_responses_sha256": case["frozen_train_responses_sha256"],
            }
        )
    result = {
        "status": "measured prospective same-observation injection controls, Rust core",
        "configuration": config,
        "cases": results,
        "actual_QC_solves": sum(x["actual_QC_solves"] for x in results),
        "objective_margins": margins,
        "seconds_total": time.perf_counter() - started,
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=1, allow_nan=False, default=_json_default) + "\n"
    )
    return result
