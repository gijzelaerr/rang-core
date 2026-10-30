"""Matched structured-action search with actual frozen full-Jones TV objectives.

This is counterfactual policy selection, not a trained transfer model. Identical
whole-rectangle families and top-eight ranking budgets compare residual-only
with TV-conditioned evidence. Test losses and injection truth never select an
action. Original masks/data/weights are authoritative; every solve is backed up.
"""

import json
import os
import shutil
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import flagging_prepared, flagging_structured_proposals
from .flagging import fixed_support_tv, protected_flags, residual_features
from .flagging_caracal import score_control
from .flagging_workflow import load_state, set_flags, solve, tree_digest, write_json

RANKINGS = ("residual", "tv")


def choose_action(records, ranking_ids, baseline_objective):
    """Choose an admissible strict improvement without consulting any test loss."""
    admissible = [
        record
        for record in records
        if record["mask_id"] in ranking_ids
        and record.get("guard_pass", False)
        and record.get("objective") is not None
        and np.isfinite(record["objective"])
        and record["objective"] < baseline_objective
    ]
    return (
        min(
            admissible,
            key=lambda record: (
                record["objective"],
                record["metrics"]["added_fraction"],
                record["mask_id"],
            ),
        )["mask_id"]
        if admissible
        else None
    )


def _compact(candidate):
    return {key: value for key, value in candidate.items() if key != "indices"}


def _export_audit(path, state, proposal):
    from casacore.tables import table

    expected_flags, expected_rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.broadcast_to(proposal[..., None], state["original_flags"].shape),
    )
    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as ms:
        weights = (
            ms.getcol("WEIGHT_SPECTRUM")
            if "WEIGHT_SPECTRUM" in ms.colnames()
            else np.broadcast_to(ms.getcol("WEIGHT")[:, None], state["weights"].shape)
        )
        audit = {
            "exact_protected_flags_and_rows": bool(
                np.array_equal(ms.getcol("FLAG"), expected_flags)
                and np.array_equal(ms.getcol("FLAG_ROW"), expected_rows)
            ),
            "data_unchanged": bool(
                np.array_equal(ms.getcol("DATA"), state["data"], equal_nan=True)
            ),
            "native_weights_unchanged": bool(
                np.array_equal(weights, state["weights"], equal_nan=True)
            ),
            "additions_only_on_train": not bool(np.any(proposal & ~state["train"])),
        }
    if not all(audit.values()):
        raise RuntimeError(f"structured export preservation failed: {path}")
    return audit


def run(run_dir, prepared_dir, ranking_budget=8, iterations=50):
    """Run matched frozen rankings on a fresh protected prepared-MS copy."""
    run_dir, prepared_dir = flagging_prepared.reject_nested_paths(run_dir, prepared_dir)
    if (
        any(
            not isinstance(value, (int, np.integer))
            or isinstance(value, (bool, np.bool_))
            or value < 1
            for value in (ranking_budget, iterations)
        )
        or ranking_budget != 8
    ):
        raise ValueError(
            "frozen ranking budget8 and positive integer iterations required"
        )
    source_digest = tree_digest(prepared_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    for name in ("state.npz", "manifest.json"):
        shutil.copy2(prepared_dir / name, run_dir / name)
    for name in ("original.ms", "work.ms"):
        shutil.copytree(prepared_dir / name, run_dir / name)
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    boundary = flagging_prepared.validate_prepared_state(run_dir, state, manifest)
    write_json(
        run_dir / "structured-config.json",
        {
            "prepared_input": str(prepared_dir),
            "prepared_input_digest": source_digest,
            "prepared_boundary": boundary,
            "rankings": RANKINGS,
            "ranking_budget": ranking_budget,
            "iterations": iterations,
            "frequency_widths": flagging_structured_proposals.FREQUENCY_WIDTHS,
            "time_scopes": ["one integration", "all integrations"],
            "baseline_groups": ["global", "antenna-star", "single-baseline"],
            "minimum_train_samples": 8,
            "maximum_added_fraction": 0.02,
            "validation_degradation_limit": 0.01,
            "residual_score": "mean(max(training whitened robust residual z,0))",
            "tv_score": "mean(z_positive*(1+clip(TV/train_positive_TV_median,0,5)))",
            "objective": "fixed_support_TV/TV0 +2*added_fraction +.25*validation_MSE/MSE0",
            "mask_semantics": "whole eligible TRAIN rectangles; reject oversized; never trim",
            "kernel": "existing Rust full2x2 TV; bounded Python proposal orchestration",
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "proposal_module_sha256": sha256(
                Path(flagging_structured_proposals.__file__).read_bytes()
            ).hexdigest(),
            "boundary_module_sha256": sha256(
                Path(flagging_prepared.__file__).read_bytes()
            ).hexdigest(),
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "truth_or_test_selection": False,
            "timing": "amd64 Linux emulation; no native performance claim",
        },
    )
    zero = np.zeros_like(state["train"])
    ti, fi = manifest["split_gain_intervals"]
    baseline, base_tv, residuals, guidance = solve(
        run_dir, state, manifest, zero, "baseline", ti, fi, iterations
    )
    fixed_baseline = fixed_support_tv(base_tv["edges"], base_tv["edges"])
    baseline_score = score_control(baseline, fixed_baseline, baseline)
    if not baseline_score["guard_pass"] or baseline_score["objective"] is None:
        raise ValueError(
            "baseline requires fixed TV support and validation predictions"
        )
    z = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    family, stats = flagging_structured_proposals.generate_candidates(
        state, z, guidance, return_stats=True
    )
    rankings = {
        mode: flagging_structured_proposals.rank_candidates(
            family, mode=mode, limit=ranking_budget
        )
        for mode in RANKINGS
    }
    write_json(run_dir / "candidate-family.json", [_compact(item) for item in family])
    family_hash = sha256(
        "\n".join(sorted(item["mask_id"] for item in family)).encode()
    ).hexdigest()
    family_report = {
        "stats": stats,
        "family_mask_ids_sha256": family_hash,
        "rankings": {
            mode: [_compact(item) for item in items] for mode, items in rankings.items()
        },
    }
    write_json(run_dir / "frozen-rankings.json", family_report)
    # One actual solve per distinct mask; shared actions reuse exactly that solve.
    distinct = {}
    for items in rankings.values():
        for item in items:
            distinct.setdefault(item["mask_id"], item)
    np.savez_compressed(
        run_dir / "backups/frozen-actions.npz",
        **{f"action_{i}": item["indices"] for i, item in enumerate(distinct.values())},
    )
    records = []
    for index, candidate in enumerate(distinct.values()):
        proposal = np.zeros_like(zero)
        proposal.flat[candidate["indices"]] = True
        label = f"structured-{index:03d}"
        record = {"mask_id": candidate["mask_id"], "candidate": _compact(candidate)}
        try:
            metrics, tv, _, _ = solve(
                run_dir,
                state,
                manifest,
                proposal,
                label,
                ti,
                fi,
                iterations,
                scale=baseline["scale"],
            )
            fixed_tv = fixed_support_tv(tv["edges"], base_tv["edges"])
            record.update(
                {
                    "metrics": metrics,
                    "fixed_support_tv": fixed_tv,
                    **score_control(metrics, fixed_tv, baseline),
                }
            )
        except RuntimeError as error:
            record.update({"error": str(error), "guard_pass": False})
        records.append(record)
        write_json(run_dir / f"checkpoint-{label}.json", record)
    selected, selected_masks = {}, {}
    for mode, items in rankings.items():
        winner = choose_action(
            records, [item["mask_id"] for item in items], baseline_score["objective"]
        )
        selected[mode] = {
            "mask_id": winner,
            "no_change": winner is None,
            "selected": next(
                (record for record in records if record["mask_id"] == winner),
                {"metrics": baseline, **baseline_score},
            ),
        }
        proposal = np.zeros_like(zero)
        if winner is not None:
            proposal.flat[distinct[winner]["indices"]] = True
        selected_masks[mode] = proposal
        set_flags(run_dir, state, proposal, f"final-{mode}", holdout=False)
        shutil.copytree(run_dir / "work.ms", run_dir / f"flagged-{mode}.ms")
        selected[mode]["export_audit"] = _export_audit(
            run_dir / f"flagged-{mode}.ms", state, proposal
        )
    np.savez_compressed(run_dir / "selected-masks.npz", **selected_masks)
    final_boundary = flagging_prepared.validate_prepared_state(run_dir, state, manifest)
    audit = {
        "prepared_source_unchanged": tree_digest(prepared_dir) == source_digest,
        "original_source_unchanged": tree_digest(manifest["source"])
        == manifest["source_digest"],
        "copied_original_unchanged": tree_digest(run_dir / "original.ms")
        == manifest["source_digest"],
        "main_work_boundary_validated": final_boundary["validated"],
        "no_truth_decoded_or_used_for_selection": True,
        "test_never_selects": True,
    }
    if not all(audit.values()):
        raise RuntimeError("structured source preservation failed")
    write_json(
        run_dir / "result.json",
        {
            "baseline": {"metrics": baseline, **baseline_score},
            "candidate_family": family_report,
            "distinct_action_solves": len(records),
            "actual_solve_count": 1 + len(records),
            "actions": records,
            "selected": selected,
            "audit": audit,
            "limitations": "Four-antenna pointing scan, reused within-scan splits. Equal ranking budgets, shared-mask solves cached; no native runtime comparison. Single-rectangle actions only; no greedy unions or truth tuning. Actual frozen full2x2 QuartiCal solves with Rust TV and original bounds. No fitted transfer model, independent-observation generalization or imaging/flux/SOTA improvement claimed.",
        },
    )
