"""Frozen geometry-balanced whole-rectangle search, not observation transfer.

Each ranking reserves two slots per canonical global/star/baseline group in the
existing admissible family. Empty groups never donate slots. Whole TRAIN masks,
stable hash ties, random seed137 and the gain-TV objective were frozen before
measurement in research/flagging-concurrent.md. Injection construction is a
separate API; neither ranking nor selection reads its truth or test losses.
"""

import json
import os
import shutil
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import flagging_prepared, flagging_structured_proposals
from .flagging import fixed_support_tv, residual_features, snapshot_flags
from .flagging_caracal import score_control
from .flagging_injections import _write_data, make_injection
from .flagging_structured import _compact, _export_audit, choose_action
from .flagging_workflow import load_state, set_flags, solve, tree_digest, write_json

GROUPS = ("global", "antenna-star", "baseline")
RANKINGS = ("residual", "tv", "random")
RANDOM_SEED = 137
WEIGHT_COLUMNS = ("WEIGHT", "WEIGHT_SPECTRUM", "SIGMA", "SIGMA_SPECTRUM")


def balanced_rank(candidates, mode="residual", per_group=2, random_seed=RANDOM_SEED):
    """Pick two distinct canonical masks per group without borrowing slots.

    Geometry aliases follow the existing generator's first canonical metadata;
    a mask cannot count as two different groups. Random draws use lists sorted
    by mask SHA256 and one seed137 RNG consumed in GROUPS order. Neither family
    iteration order, score values (random mode) nor held-out values affect draws.
    """
    if mode not in RANKINGS or per_group != 2 or random_seed != RANDOM_SEED:
        raise ValueError(
            "frozen residual/tv/random ranking, two slots and seed137 required"
        )
    if len({item["mask_id"] for item in candidates}) != len(candidates):
        raise ValueError("balanced ranking requires distinct masks")
    if any(item["metadata"]["group"] not in GROUPS for item in candidates):
        raise ValueError("unexpected canonical geometry group")
    rng = np.random.default_rng(random_seed)
    result = []
    for group in GROUPS:
        items = [item for item in candidates if item["metadata"]["group"] == group]
        if mode == "random":
            items = sorted(items, key=lambda item: item["mask_id"])
            if items:
                indices = rng.choice(
                    len(items), min(per_group, len(items)), replace=False
                )
                result.extend(items[int(index)] for index in indices)
        else:
            result.extend(
                flagging_structured_proposals.rank_candidates(
                    items, mode=mode, limit=per_group
                )
            )
    return result


def _clone(run_dir, prepared_dir, *, state_backup=False):
    output, source = flagging_prepared.reject_nested_paths(run_dir, prepared_dir)
    digest = tree_digest(source)
    output.mkdir(parents=True, exist_ok=False)
    (output / "backups").mkdir()
    shutil.copy2(source / "manifest.json", output / "manifest.json")
    state_path = output / ("backups/source-state.npz" if state_backup else "state.npz")
    shutil.copy2(source / "state.npz", state_path)
    for name in ("original.ms", "work.ms"):
        shutil.copytree(source / name, output / name)
    return output, source, digest


def _all_weights(path):
    from casacore.tables import table

    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as ms:
        return {
            name: ms.getcol(name) for name in WEIGHT_COLUMNS if name in ms.colnames()
        }


def _weights_equal(path, reference):
    actual = _all_weights(path)
    return actual.keys() == reference.keys() and all(
        np.array_equal(actual[name], value, equal_nan=True)
        for name, value in reference.items()
    )


def make_case(
    run_dir,
    prepared_dir,
    pattern,
    strength=10.0,
    seed=101,
    occupancy=0.005,
):
    """Create a compatible backed-up TRAIN-only injected copy from clean DATA.

    This simulation constructor writes truth. It does not rank/train/select any
    policy. The learner consumes state/manifest/MS files only, not case-config,
    injection.npz or injection.json. Original DATA must equal source state/work
    DATA, so an already contaminated prepared source is rejected before writing.
    """
    if pattern not in ("time-burst", "antenna-local"):
        raise ValueError("frozen fresh controls use time-burst or antenna-local")
    if (
        not isinstance(seed, (int, np.integer))
        or isinstance(seed, (bool, np.bool_))
        or seed not in (101, 103, 105)
        or strength != 10.0
        or occupancy != 0.005
    ):
        raise ValueError(
            "frozen seeds101/103/105, strength10 and occupancy0.005 required"
        )
    output, source, digest = _clone(run_dir, prepared_dir, state_backup=True)
    with np.load(output / "backups/source-state.npz", allow_pickle=False) as saved:
        state = {key: saved[key] for key in saved.files}
    manifest = json.loads((output / "manifest.json").read_text())
    boundary = flagging_prepared.validate_prepared_state(output, state, manifest)
    if boundary["working_data_differs_from_original"]:
        raise ValueError(
            "injection construction requires clean original/state/work DATA"
        )
    snapshot_flags(
        output / "backups/original-flags.npz",
        state["original_flags"],
        state["original_rows"],
    )
    original_weights = _all_weights(output / "work.ms")
    truth, delta, metadata = make_injection(state, pattern, strength, seed, occupancy)
    injected_data = state["data"] + delta
    # Freeze the construction and truth before the sole backed-up DATA write.
    write_json(output / "injection.json", metadata)
    with (output / "injection.npz").open("xb") as stream:
        np.savez_compressed(stream, injected=truth, delta=delta[truth])
    data_backup_sha = _write_data(output, injected_data, "fresh-injection")
    state["data"] = injected_data
    with (output / "state.npz").open("xb") as stream:
        np.savez_compressed(stream, **state)
    final_boundary = flagging_prepared.validate_prepared_state(output, state, manifest)
    audit = {
        "prepared_source_unchanged": tree_digest(source) == digest,
        "copied_original_unchanged": tree_digest(output / "original.ms")
        == manifest["original_copy_digest"],
        "original_source_unchanged": tree_digest(manifest["source"])
        == manifest["source_digest"],
        "all_weight_sigma_columns_unchanged": _weights_equal(
            output / "work.ms", original_weights
        ),
        "training_only_injection": not bool(np.any(truth & ~state["train"])),
        "full_original_data_backup_created": True,
        "boundary_validated": final_boundary["validated"],
    }
    if not all(audit.values()):
        raise RuntimeError("fresh injection preservation audit failed")
    report = {
        "prepared_source": str(source),
        "prepared_source_digest": digest,
        "injection": metadata,
        "data_backup_sha256": data_backup_sha,
        "source_state_sha256": sha256(
            (output / "backups/source-state.npz").read_bytes()
        ).hexdigest(),
        "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "injection_module_sha256": sha256(
            Path(make_injection.__code__.co_filename).read_bytes()
        ).hexdigest(),
        "prepared_boundary": final_boundary,
        "audit": audit,
        "limitations": "Synthetic training-only additions on the same short MeerKAT pointing scan; new seeds do not establish observation transfer.",
    }
    write_json(output / "case-config.json", report)
    print(f"Fresh compatible {pattern} seed{seed}: {output}", flush=True)
    return report


def run(run_dir, prepared_dir, iterations=50):
    """Actual guarded full-Jones re-solves for three matched six-slot rankings."""
    if (
        not isinstance(iterations, (int, np.integer))
        or isinstance(iterations, (bool, np.bool_))
        or iterations != 50
    ):
        raise ValueError("frozen calibration uses50 iterations")
    output, source, source_digest = _clone(run_dir, prepared_dir)
    state = load_state(output)
    manifest = json.loads((output / "manifest.json").read_text())
    boundary = flagging_prepared.validate_prepared_state(output, state, manifest)
    weights = _all_weights(output / "work.ms")
    write_json(
        output / "balanced-config.json",
        {
            "prepared_input": str(source),
            "prepared_input_digest": source_digest,
            "prepared_boundary": boundary,
            "rankings": RANKINGS,
            "group_order": GROUPS,
            "slots_per_canonical_group": 2,
            "ranking_budget": 6,
            "empty_group_slots_borrowed": False,
            "random_seed": RANDOM_SEED,
            "iterations": iterations,
            "objective": "fixed_support_TV/TV0+2*added_fraction+.25*validation_MSE/MSE0",
            "maximum_added_fraction": 0.02,
            "validation_degradation_limit": 0.01,
            "mask_semantics": "single whole eligible TRAIN rectangle; no trimming/unions",
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "proposal_module_sha256": sha256(
                Path(flagging_structured_proposals.__file__).read_bytes()
            ).hexdigest(),
            "boundary_module_sha256": sha256(
                Path(flagging_prepared.__file__).read_bytes()
            ).hexdigest(),
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "no_truth_decoded_or_used_for_selection": True,
            "test_never_selects": True,
            "timing": "Linux amd64 emulation; not native runtime evidence",
        },
    )
    zero = np.zeros_like(state["train"])
    ti, fi = manifest["split_gain_intervals"]
    baseline, base_tv, residuals, guidance = solve(
        output, state, manifest, zero, "baseline", ti, fi, iterations
    )
    baseline_score = score_control(
        baseline, fixed_support_tv(base_tv["edges"], base_tv["edges"]), baseline
    )
    if not baseline_score["guard_pass"]:
        raise ValueError("baseline lacks valid support/validation objective")
    z = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    family, stats = flagging_structured_proposals.generate_candidates(
        state, z, guidance, return_stats=True
    )
    rankings = {mode: balanced_rank(family, mode) for mode in RANKINGS}
    report = {
        "stats": stats,
        "family_mask_ids_sha256": sha256(
            "\n".join(sorted(item["mask_id"] for item in family)).encode()
        ).hexdigest(),
        "rankings": {
            mode: [_compact(item) for item in items] for mode, items in rankings.items()
        },
        "ranking_slot_counts": {
            mode: {
                group: sum(item["metadata"]["group"] == group for item in items)
                for group in GROUPS
            }
            for mode, items in rankings.items()
        },
    }
    write_json(output / "candidate-family.json", [_compact(item) for item in family])
    write_json(output / "frozen-rankings.json", report)
    distinct = {}
    for items in rankings.values():
        for item in items:
            distinct.setdefault(item["mask_id"], item)
    with (output / "backups/frozen-actions.npz").open("xb") as stream:
        np.savez_compressed(
            stream,
            **{
                f"action_{i}": item["indices"]
                for i, item in enumerate(distinct.values())
            },
        )
    records = []
    for index, candidate in enumerate(distinct.values()):
        proposal = np.zeros_like(zero)
        proposal.flat[candidate["indices"]] = True
        label = f"balanced-{index:03d}"
        record = {"mask_id": candidate["mask_id"], "candidate": _compact(candidate)}
        try:
            metrics, tv, _, _ = solve(
                output,
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
        write_json(output / f"checkpoint-{label}.json", record)
    selected, masks = {}, {}
    for mode, items in rankings.items():
        winner = choose_action(
            records, [item["mask_id"] for item in items], baseline_score["objective"]
        )
        proposal = np.zeros_like(zero)
        if winner is not None:
            proposal.flat[distinct[winner]["indices"]] = True
        masks[mode] = proposal
        set_flags(output, state, proposal, f"final-{mode}", holdout=False)
        export = output / f"flagged-{mode}.ms"
        shutil.copytree(output / "work.ms", export)
        export_audit = {
            **_export_audit(export, state, proposal),
            "all_weight_sigma_columns_unchanged": _weights_equal(export, weights),
        }
        if not all(export_audit.values()):
            raise RuntimeError("balanced export weight preservation failed")
        selected[mode] = {
            "mask_id": winner,
            "no_change": winner is None,
            "selected": next(
                (record for record in records if record["mask_id"] == winner),
                {"metrics": baseline, **baseline_score},
            ),
            "export_audit": export_audit,
        }
    with (output / "selected-masks.npz").open("xb") as stream:
        np.savez_compressed(stream, **masks)
    final_boundary = flagging_prepared.validate_prepared_state(output, state, manifest)
    audit = {
        "prepared_source_unchanged": tree_digest(source) == source_digest,
        "original_source_unchanged": tree_digest(manifest["source"])
        == manifest["source_digest"],
        "copied_original_unchanged": tree_digest(output / "original.ms")
        == manifest["original_copy_digest"],
        "main_work_boundary_validated": final_boundary["validated"],
        "all_weight_sigma_columns_unchanged": _weights_equal(
            output / "work.ms", weights
        ),
        "no_truth_decoded_or_used_for_selection": True,
        "test_never_selects": True,
    }
    if not all(audit.values()):
        raise RuntimeError("balanced source preservation failed")
    result = {
        "baseline": {"metrics": baseline, **baseline_score},
        "candidate_family": report,
        "distinct_action_solves": len(records),
        "actual_solve_count": 1 + len(records),
        "actions": records,
        "selected": selected,
        "audit": audit,
        "limitations": "Within one four-antenna pointing scan; fresh injection seeds are not independent observations. Counterfactual selection, not a trained model. Same-family six slots per rank, no borrowing, shared-mask solves cached. No truth/test tuning, unions, native performance, imaging/flux/SOTA advantage claimed.",
    }
    write_json(output / "result.json", result)
    return result
