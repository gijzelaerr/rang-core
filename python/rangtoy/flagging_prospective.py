"""Prospective TRAIN-only gain-response forecasts and bounded confirmation.

The candidate family and all response forecasts are frozen before opening
new action outcomes. TEST and injection truth never select an action.
"""

import json
import os
import shutil
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import flagging_prepared
from .flagging import (
    fixed_support_tv,
    gain_tv,
    polar_gauge,
    residual_features,
    snapshot_flags,
)
from .flagging_balanced import _all_weights, _weights_equal, balanced_rank
from .flagging_caracal import score_control
from .flagging_influence import (
    _npz,
    _predict,
    _training_bundle,
    anchored_response,
    training_normals,
)
from .flagging_injections import _write_data, make_injection
from .flagging_response import RESERVE_BYTES, Budget, allocated_bytes, copy_bound
from .flagging_structured import _compact, _export_audit, choose_action
from .flagging_structured_proposals import generate_candidates
from .flagging_trend import (
    detrended_tv,
    estimate_trend,
    guidance_from_tv,
    training_gain_support,
)
from .flagging_workflow import load_state, set_flags, solve, tree_digest
from .projector import _native_library

SEEDS = (107, 109)
MARGIN = 1e-6


class CampaignBudget(Budget):
    def __init__(self, root, limit):
        super().__init__(root)
        self.limit = limit

    def check(self, needed=0):
        used = allocated_bytes(self.root)
        if needed < 0 or used + needed > self.limit:
            raise ValueError("campaign checked allocation budget exceeded")
        ancestor = self.root
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < RESERVE_BYTES + needed:
            raise ValueError("campaign operation would violate 8GiB disk reserve")
        return used


def _clone(source, destination, budget, state_backup=False):
    source, destination = Path(source), Path(destination)
    budget.mkdir(destination)
    budget.mkdir(destination / "backups")
    budget.copy(source / "manifest.json", destination / "manifest.json")
    budget.copy(
        source / "state.npz",
        destination / ("backups/source-state.npz" if state_backup else "state.npz"),
    )
    for name in ("original.ms", "work.ms"):
        budget.copy(source / name, destination / name)


def prepare_inputs(run_dir, prepared_dir):
    """Create three small backed-up inputs; constructor truth is separate."""
    output, source = flagging_prepared.reject_nested_paths(run_dir, prepared_dir)
    digest = tree_digest(source)
    budget = CampaignBudget(output, 768 * 1024**2)
    budget.mkdir(output)
    budget.json(
        output / "config.json",
        {
            "source": str(source),
            "source_digest": digest,
            "seeds": SEEDS,
            "strength_inverse_weight_units": 10,
            "occupancy": 0.005,
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "native_sha256": sha256(
                Path(_native_library()._name).read_bytes()
            ).hexdigest(),
            "allocation_limit_bytes": budget.limit,
            "reserve_bytes": RESERVE_BYTES,
        },
    )
    budget.mkdir(output / "cases")
    cases = []
    for seed in (None, *SEEDS):
        case_id = "clean" if seed is None else f"time-burst-seed{seed}"
        directory = output / "cases" / case_id
        _clone(source, directory, budget, state_backup=seed is not None)
        state = _npz(
            directory / ("state.npz" if seed is None else "backups/source-state.npz")
        )
        manifest = json.loads((directory / "manifest.json").read_text())
        boundary = flagging_prepared.validate_prepared_state(directory, state, manifest)
        if boundary["working_data_differs_from_original"]:
            raise ValueError("new injections require clean original DATA")
        weights = _all_weights(directory / "work.ms")
        with budget.operation(
            state["original_flags"].nbytes + 128 * 1024, "original flag backup"
        ):
            snapshot_flags(
                directory / "backups/original-flags.npz",
                state["original_flags"],
                state["original_rows"],
            )
        if seed is not None:
            truth, delta, metadata = make_injection(
                state, "time-burst", 10.0, seed, 0.005
            )
            budget.json(directory / "injection.json", metadata)
            budget.npz(directory / "injection.npz", injected=truth, delta=delta[truth])
            data = state["data"] + delta
            # The shared writer creates a full DATA backup before the sole write.
            with budget.operation(
                2 * data.nbytes + copy_bound(directory / "work.ms") + 1024**2,
                "backed-up DATA injection",
            ):
                backup = _write_data(directory, data, "prospective-injection")
            state["data"] = data
            budget.npz(directory / "state.npz", **state)
            budget.json(directory / "data-backup.json", {"sha256": backup})
        final = flagging_prepared.validate_prepared_state(directory, state, manifest)
        audit = {
            "source_unchanged": tree_digest(source) == digest,
            "copied_original_unchanged": tree_digest(directory / "original.ms")
            == manifest["original_copy_digest"],
            "weights_sigma_unchanged": _weights_equal(directory / "work.ms", weights),
            "boundary_validated": final["validated"],
        }
        if not all(audit.values()):
            raise RuntimeError("input construction preservation failed")
        cases.append(
            {
                "case_id": case_id,
                "path": str(directory),
                "seed": seed,
                "digest": tree_digest(directory),
                "audit": audit,
            }
        )
        budget.json(directory / "case-config.json", cases[-1])
        # Include the case receipt in the final source digest.
        cases[-1]["digest"] = tree_digest(directory)
    result = {
        "cases": cases,
        "source_unchanged": tree_digest(source) == digest,
        "allocated_bytes": budget.check(),
        "allocation_limit_bytes": budget.limit,
    }
    budget.json(output / "cases.json", result)
    return result


def make_shortlist(state, baseline, metrics, residuals, guidance):
    """Two whole rectangles per group per ranking; at most 24 distinct masks."""
    z = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    family, stats = generate_candidates(state, z, guidance, return_stats=True)
    rankings = {
        mode: balanced_rank(family, mode) for mode in ("residual", "tv", "random")
    }
    aligned, valid = polar_gauge(baseline["gains"], baseline["gain_valid"])
    slopes, counts = estimate_trend(
        aligned,
        valid,
        baseline["gain_times"],
        baseline["gain_frequencies"],
        training_gain_support(state, valid.shape),
    )
    if np.isfinite(slopes).all():
        tv = detrended_tv(
            aligned,
            valid,
            baseline["gain_times"],
            baseline["gain_frequencies"],
            slopes,
            scale=metrics["scale"],
        )
        detrended = generate_candidates(state, z, guidance_from_tv(state, tv))
        if {x["mask_id"] for x in detrended} != {x["mask_id"] for x in family}:
            raise RuntimeError("guidance changed the admissible geometry family")
        rankings["detrended"] = balanced_rank(detrended, "tv")
    else:
        rankings["detrended"] = []
    distinct = {}
    for items in rankings.values():
        for item in items:
            distinct.setdefault(item["mask_id"], item)
    stats = {
        "generator": stats,
        "family_mask_ids_sha256": sha256(
            "\n".join(sorted(x["mask_id"] for x in family)).encode()
        ).hexdigest(),
        "trend_slopes": np.where(np.isfinite(slopes), slopes, None).tolist(),
        "trend_edge_counts": counts.tolist(),
        "detrended_guidance_available": bool(np.isfinite(slopes).all()),
        "maximum_distinct": 24,
    }
    return list(distinct.values()), rankings, stats


def forecast_family(state, baseline, metrics, candidates, cache_path=None):
    """TRAIN-only curvature/response/TV; validation deliberately separate."""
    bundle = _training_bundle(state, baseline)
    start = time.perf_counter()
    full_h, full_b, _ = training_normals(
        **{k: v for k, v in bundle.items() if k != "flat_indices"}
    )
    normal_seconds = time.perf_counter() - start
    records, raw = [], []
    for candidate in candidates:
        indices = np.asarray(candidate["indices"])
        if (
            indices.dtype.kind not in "iu"
            or indices.ndim != 1
            or np.any(indices[1:] <= indices[:-1])
            or not 8 <= len(indices) <= int(0.02 * state["train"].sum())
        ):
            raise ValueError("sorted unique bounded whole-TRAIN mask required")
        if (
            sha256(indices.astype("<i8").tobytes()).hexdigest() != candidate["mask_id"]
            or len(indices) != candidate["sample_count"]
            or candidate["added_fraction"] != len(indices) / state["train"].sum()
        ):
            raise ValueError("candidate index/count/fraction/SHA mismatch")
        positions = np.searchsorted(bundle["flat_indices"], indices)
        if np.any(positions >= len(bundle["flat_indices"])) or not np.array_equal(
            bundle["flat_indices"][positions], indices
        ):
            raise ValueError("candidate contains non-TRAIN cells")
        drop = {
            k: v[positions]
            for k, v in bundle.items()
            if k not in ("gains", "flat_indices")
        }
        start = time.perf_counter()
        drop_h, drop_b, _ = training_normals(bundle["gains"], **drop)
        predicted = baseline["gains"].copy().reshape(-1, 4, 2, 2)
        audits = []
        for bin_id in np.unique(drop["bin_ids"]):
            active = np.array(
                [
                    np.trace(full_h[bin_id, 8 * i : 8 * (i + 1), 8 * i : 8 * (i + 1)])
                    > 0
                    for i in range(4)
                ]
            )
            response = anchored_response(
                full_h[bin_id],
                full_b[bin_id],
                drop_h[bin_id],
                drop_b[bin_id],
                bundle["gains"][bin_id],
                active,
            )
            audits.append(
                {
                    "bin_id": int(bin_id),
                    **{k: v for k, v in response.items() if k != "delta"},
                }
            )
            if response["guard_pass"]:
                predicted[bin_id] += response["delta"]
        guard = all(x["guard_pass"] for x in audits)
        predicted = predicted.reshape(baseline["gains"].shape)
        record = {
            "mask_id": candidate["mask_id"],
            "candidate": _compact(candidate),
            "bin_audits": audits,
            "guard_pass": guard,
            "reason": None if guard else "curvature/trust abstention",
            "native_response_seconds": time.perf_counter() - start,
        }
        if guard:
            aligned, valid = polar_gauge(predicted, baseline["gain_valid"])
            tv = gain_tv(
                aligned,
                valid,
                baseline["gain_times"],
                baseline["gain_frequencies"],
                scale=metrics["scale"],
            )
            fixed = fixed_support_tv(tv["edges"], baseline["edges"])
            record["predicted_fixed_tv"] = fixed
            if fixed is None:
                record.update(guard_pass=False, reason="fixed TV support lost")
        records.append(record)
        raw.append(
            predicted
            if record["guard_pass"]
            else np.full_like(predicted, complex(np.nan, np.nan))
        )
    payload = np.stack(raw) if raw else np.empty((0, *baseline["gains"].shape), complex)
    if cache_path is not None:
        budget = CampaignBudget(Path(cache_path).parent, 256 * 1024**2)
        budget.npz(cache_path, raw_predicted_gains=payload)
    return {
        "records": records,
        "raw_predicted_gains": payload,
        "bundle": bundle,
        "full_h": full_h,
        "full_b": full_b,
        "baseline": baseline,
        "metrics": metrics,
        "full_training_normals_seconds": normal_seconds,
    }


def score_forecasts(state, forecast):
    """Only call after complete TRAIN records are serialized by the caller."""
    metrics = forecast["metrics"]
    for i, record in enumerate(forecast["records"]):
        if not record["guard_pass"]:
            continue
        rows, channels, prediction = _predict(
            state, forecast["raw_predicted_gains"][i], state["validation"]
        )
        val = float(
            np.mean(
                np.mean(
                    np.abs(state["data"][rows, channels] - prediction) ** 2
                    * state["weights"][rows, channels],
                    axis=-1,
                )
            )
        )
        if not np.isfinite(val) or val > 1.01 * metrics["losses"]["validation"]:
            record.update(guard_pass=False, reason="validation guard")
            continue
        objective = (
            record["predicted_fixed_tv"] / max(metrics["tv"], 1e-30)
            + 2 * record["candidate"]["added_fraction"]
            + 0.25 * val / max(metrics["losses"]["validation"], 1e-30)
        )
        record.update(
            predicted_validation_MSE=val,
            predicted_objective=objective,
            predicted_benefit=1.25 - objective,
            predicted_cost_removed_benefit=1.25
            - objective
            + 2 * record["candidate"]["added_fraction"],
        )
    return forecast


def _freeze_view(forecast):
    return {
        "records": forecast["records"],
        "full_training_normals_seconds": forecast["full_training_normals_seconds"],
    }


def run(run_dir, inputs_dir, iterations=50):
    """Three new baselines, <=72 new actions; two-confirmation frozen policy."""
    if type(iterations) is not int or iterations != 50:
        raise ValueError("frozen 50-iteration solve required")
    output, source = flagging_prepared.reject_nested_paths(run_dir, inputs_dir)
    digest = tree_digest(source)
    cases = json.loads((source / "cases.json").read_text())["cases"]
    expected_ids = ["clean", "time-burst-seed107", "time-burst-seed109"]
    if [x["seed"] for x in cases] != [None, *SEEDS] or [
        x["case_id"] for x in cases
    ] != expected_ids:
        raise ValueError("frozen clean/seed107/seed109 input ordering required")
    paths = [Path(x["path"]).resolve() for x in cases]
    if len(set(paths)) != 3 or any(
        p != source / "cases" / name for p, name in zip(paths, expected_ids)
    ):
        raise ValueError("distinct exact frozen case paths required")
    for item, path in zip(cases, paths):
        if (
            not item.get("audit")
            or not all(v is True for v in item["audit"].values())
            or item.get("digest") != tree_digest(path)
        ):
            raise ValueError("case digest/preservation receipt mismatch")
    budget = CampaignBudget(output, 3 * 1024**3)
    budget.mkdir(output)
    runtime = {
        p: sha256(Path(p).read_bytes()).hexdigest()
        for p in (
            str(Path(__file__).resolve()),
            str(Path(_native_library()._name).resolve()),
        )
    }
    config = {
        "input_source": str(source),
        "source_digest": digest,
        "runtime": runtime,
        "image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "iterations": iterations,
        "grid": [2, 32],
        "maximum_action_confirmations": 2,
        "maximum_actual_QC_solves": 75,
        "minimum_benefit": MARGIN,
        "allocation_limit_bytes": budget.limit,
        "test_or_truth_selects": False,
        "finite_QC_comparison": "Linux amd64 execution; no native cost/speedup claim",
    }
    budget.json(output / "config.json", config)
    prepared = {}
    for item in cases:
        case_id, case_source = item["case_id"], Path(item["path"])
        if not case_source.resolve().is_relative_to(source):
            raise ValueError("case must remain within immutable inputs")
        directory = output / case_id
        _clone(case_source, directory, budget)
        state = load_state(directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        boundary = flagging_prepared.validate_prepared_state(directory, state, manifest)
        if (
            manifest["split_gain_intervals"] != [2, 32]
            or manifest["scope"]["telescope"].casefold() != "meerkat"
            or manifest["scope"]["band"] != "L"
        ):
            raise ValueError("MeerKAT L-band native 2x32 required")
        weights = _all_weights(directory / "work.ms")
        with budget.operation(80 * 1024**2, "baseline QuartiCal"):
            metrics, tv, residual, guidance = solve(
                directory,
                state,
                manifest,
                np.zeros_like(state["train"]),
                "baseline",
                2,
                32,
                iterations,
            )
        baseline = _npz(directory / "trials/baseline/diagnostics.npz")
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
        report = {
            "stats": stats,
            "rankings": {k: [_compact(x) for x in v] for k, v in rankings.items()},
        }
        budget.json(directory / "frozen-rankings.json", report)
        budget.npz(
            directory / "frozen-actions.npz",
            **{f"action_{i}": x["indices"] for i, x in enumerate(candidates)},
        )
        forecast = forecast_family(state, baseline, metrics, candidates)
        budget.npz(
            directory / "gain-forecasts.npz",
            raw_predicted_gains=forecast["raw_predicted_gains"],
        )
        budget.json(directory / "frozen-train-responses.json", _freeze_view(forecast))
        prepared[case_id] = {
            "directory": directory,
            "source": case_source,
            "source_digest": tree_digest(case_source),
            "state": state,
            "manifest": manifest,
            "baseline": baseline,
            "metrics": metrics,
            "weights": weights,
            "boundary": boundary,
            "candidates": candidates,
            "rankings": rankings,
            "forecast": forecast,
        }
    if 3 + sum(len(c["candidates"]) for c in prepared.values()) > 75:
        raise ValueError("campaign cannot exceed75 QC solves")
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
        budget.json(
            case["directory"] / "frozen-forecasts.json",
            {**_freeze_view(case["forecast"]), "confirm_ids": case["confirm_ids"]},
        )
    results = []
    for case_id, case in prepared.items():
        directory, state, metrics = case["directory"], case["state"], case["metrics"]
        records = []
        for i, candidate in enumerate(case["candidates"]):
            added = np.zeros_like(state["train"])
            added.flat[candidate["indices"]] = True
            record = {"mask_id": candidate["mask_id"], "candidate": _compact(candidate)}
            try:
                with budget.operation(80 * 1024**2, "candidate QuartiCal"):
                    actual, tv, _, _ = solve(
                        directory,
                        state,
                        case["manifest"],
                        added,
                        f"prospective-{i:03d}",
                        2,
                        32,
                        iterations,
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
            budget.json(directory / f"checkpoint-{i:03d}.json", record)

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
        budget.json(directory / "frozen-selection.json", selected)
        # Only after the final selection freeze, decode constructor truth.
        truth = None
        if (case["source"] / "injection.npz").exists():
            truth = _npz(case["source"] / "injection.npz", ("injected",))["injected"]
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
        budget.npz(directory / "selected-masks.npz", **masks)
        with budget.operation(4 * 1024**2, "backed-up final flags"):
            set_flags(
                directory,
                state,
                masks["physics_two_confirmation"],
                "final-physics",
                holdout=False,
            )
        audit = {
            **_export_audit(
                directory / "work.ms", state, masks["physics_two_confirmation"]
            ),
            "weights_sigma_unchanged": _weights_equal(
                directory / "work.ms", case["weights"]
            ),
            "prepared_case_unchanged": tree_digest(case["source"])
            == case["source_digest"],
            "copied_original_unchanged": tree_digest(directory / "original.ms")
            == case["manifest"]["original_copy_digest"],
            "original_source_unchanged": tree_digest(case["manifest"]["source"])
            == case["manifest"]["source_digest"],
        }
        if not all(audit.values()):
            raise RuntimeError("prospective preservation failed")
        result = {
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
        }
        budget.json(directory / "result.json", result)
        results.append(result)
    audit = {
        "inputs_unchanged": tree_digest(source) == digest,
        "runtime_unchanged": all(
            sha256(Path(p).read_bytes()).hexdigest() == h for p, h in runtime.items()
        ),
    }
    if not all(audit.values()):
        raise RuntimeError("prospective campaign source/runtime changed")
    result = {
        "status": "measured prospective same-observation injection controls",
        "configuration": config,
        "cases": results,
        "audit": audit,
        "actual_QC_solves": sum(x["actual_QC_solves"] for x in results),
        "allocated_bytes": budget.check(),
        "limitations": "New candidates and seeds, not independent observation transfer; full union measured as a reference; known injection truth is not RFI precision; no native runtime or imaging superiority claim.",
    }
    budget.json(output / "result.json", result)
    return result
