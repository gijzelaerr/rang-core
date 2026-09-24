"""TRAIN-only local signal transfer constraint with frozen paired QC controls.

Known templates constrain a bounded diagnostic family, not an unknown sky.
TEST/source truth never chooses a mask; complete sky is diagnostic only.
"""

import json
import os
import platform
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from . import flagging_influence as influence
from . import flagging_response as response
from .flagging import fixed_support_tv
from .flagging_caracal import score_control
from .flagging_injections import injection_scores
from .flagging_prepared import reject_nested_paths, validate_prepared_state
from .flagging_workflow import load_state, solve, tree_digest
from .projector import _native_library

SEEDS = (107, 109)
GRID = (2, 32)
PROBE_JY = 0.001
TRANSFER_LIMIT = 0.1
MINIMUM_BENEFIT = 1e-6
MAXIMUM_SOLVES = 18


def inverse_tangent(data, injected, gp, gq, dp, dq, weights):
    """First-order corrected trace, including correction of SAME original DATA."""
    data, injected = np.asarray(data), np.asarray(injected)
    matrices = [np.asarray(x, complex) for x in (gp, gq, dp, dq)]
    weights = np.asarray(weights, float)
    n = len(data)
    if (
        data.shape != (n, 4)
        or injected.shape != data.shape
        or weights.shape != data.shape
        or any(x.shape != (n, 2, 2) for x in matrices)
        or not all(np.isfinite(x).all() for x in (data, injected, weights, *matrices))
        or (weights <= 0).any()
    ):
        raise ValueError("finite matched four-correlation TRAIN samples required")
    gp, gq, dp, dq = matrices
    if (np.linalg.cond(gp) > 1e8).any() or (np.linalg.cond(gq) > 1e8).any():
        raise ValueError("TRAIN Jones inverse condition exceeds1e8")
    ip, iq = np.linalg.inv(gp), np.linalg.inv(gq)
    iqh = iq.conj().swapaxes(-1, -2)
    corrected = ip @ data.reshape(n, 2, 2) @ iqh
    direct = ip @ injected.reshape(n, 2, 2) @ iqh
    adaptation = -ip @ dp @ corrected - corrected @ (iq @ dq).conj().swapaxes(-1, -2)

    def trace(x):
        return 0.5 * np.trace(x, axis1=-2, axis2=-1)

    return trace(direct + adaptation), trace(direct), trace(adaptation)


def fit_transfer(total, direct, adaptation, templates, weights):
    """Real unit-Jy transfer columns; no positivity, slope fit or support pruning."""
    terms = [np.asarray(x) for x in (total, direct, adaptation)]
    templates, weights = np.asarray(templates), np.asarray(weights, float)
    if templates.ndim != 2 or any(x.shape != templates.shape for x in terms):
        raise ValueError("one TRAIN response per frozen template required")
    mask = np.ones(templates.shape[1], bool)
    fits = {
        name: [
            response.linear_response(value, templates, weights, mask)
            for value in values
        ]
        for name, values in zip(("total", "direct", "adaptation"), terms)
    }
    available = all(fit["available"] for values in fits.values() for fit in values)
    matrices = (
        {
            name: np.asarray([f["flux_jy"] for f in values], float).T
            for name, values in fits.items()
        }
        if available
        else {}
    )
    error = (
        float(np.linalg.norm(matrices["total"] - np.eye(len(templates)), 2))
        if available
        else None
    )
    closure = (
        float(
            np.max(
                np.abs(matrices["total"] - matrices["direct"] - matrices["adaptation"])
            )
        )
        if available
        else None
    )
    if closure is not None and closure > 1e-10:
        raise RuntimeError("TRAIN transfer decomposition closure failed")
    return {
        "available": available,
        "guard_pass": bool(available and error <= TRANSFER_LIMIT),
        "absolute_transfer_operator_error": error,
        "transfer_matrices": {name: value.tolist() for name, value in matrices.items()},
        "fits": fits,
        "coefficient_closure_linf": closure,
        "support": "same original TRAIN, no candidate-specific pruning",
        "semantics": "absolute near identity; no relative fallback; local known-family diagnostic only",
    }


def train_signal_guard(state, baseline, predicted_gains, indices, templates):
    """Native retained-TRAIN tangent curvature; fixed original-TRAIN evaluation."""
    bundle = influence._training_bundle(state, baseline)
    flat, bins = bundle["flat_indices"], bundle["bin_ids"]
    indices = np.asarray(indices)
    if (
        indices.dtype.kind not in "iu"
        or indices.ndim != 1
        or np.any(indices[1:] <= indices[:-1])
    ):
        raise ValueError("sorted unique TRAIN indices required")
    positions = np.searchsorted(flat, indices)
    if np.any(positions >= len(flat)) or not np.array_equal(flat[positions], indices):
        raise ValueError("signal guard mask contains non-TRAIN cells")
    retained = np.ones(len(flat), bool)
    retained[positions] = False
    gains = np.asarray(predicted_gains, complex)
    if gains.shape != baseline["gains"].shape:
        raise ValueError("forecast full-Jones grid differs from baseline")
    gains = gains.reshape(-1, 4, 2, 2)
    rows, channels = np.where(state["train"])
    p, q = bundle["p"], bundle["q"]
    gp, gq = gains[bins, p], gains[bins, q]
    if (
        not np.isfinite(gp).all()
        or not np.isfinite(gq).all()
        or (np.linalg.cond(gp) > 1e8).any()
        or (np.linalg.cond(gq) > 1e8).any()
    ):
        return {
            "available": False,
            "guard_pass": False,
            "reason": "forecast original TRAIN inverse support lost",
        }
    original_active = np.zeros(gains.shape[:2], bool)
    original_active[bins, p] = True
    original_active[bins, q] = True
    ref = bundle["gains"]
    rp, rq = ref[bins, p], ref[bins, q]
    data, weights = state["data"][rows, channels], bundle["weights"]
    sample_templates = np.asarray(templates)[:, rows, channels]
    _, variance, valid = response._correct(
        data, weights, (rp, rq, np.ones(len(rows), bool))
    )
    if not valid.all():
        return {
            "available": False,
            "guard_pass": False,
            "reason": "fixed original TRAIN reference support lost",
        }
    native_audits, total, direct, adaptation = [], [], [], []
    for source_template in sample_templates:
        injected = (
            rp
            @ (PROBE_JY * source_template[:, None, None] * np.eye(2))
            @ rq.conj().swapaxes(-1, -2)
        ).reshape(-1, 4)
        h, b, counts = influence.training_normals(
            gains,
            bundle["models"][retained],
            injected[retained].reshape(-1, 2, 2),
            weights[retained],
            p[retained],
            q[retained],
            bins[retained],
        )
        tangent = np.zeros_like(gains)
        source_audits = []
        for bin_id in np.unique(bins):
            active = np.asarray(
                [
                    np.trace(h[bin_id, i * 8 : (i + 1) * 8, i * 8 : (i + 1) * 8]) > 0
                    for i in range(4)
                ]
            )
            if (
                not np.array_equal(active, original_active[bin_id])
                or counts[bin_id] == 0
            ):
                return {
                    "available": False,
                    "guard_pass": False,
                    "reason": "retained TRAIN station/bin support lost",
                }
            step = influence.anchored_response(
                h[bin_id],
                np.zeros(32),
                np.zeros((32, 32)),
                -b[bin_id],
                gains[bin_id],
                active,
            )
            source_audits.append(
                {
                    "bin_id": int(bin_id),
                    **{k: v for k, v in step.items() if k != "delta"},
                }
            )
            if not step["guard_pass"]:
                return {
                    "available": False,
                    "guard_pass": False,
                    "reason": "TRAIN probe curvature/gauge/trust abstention",
                    "native_audits": source_audits,
                }
            tangent[bin_id] = step["delta"]
        values = inverse_tangent(
            data, injected, gp, gq, tangent[bins, p], tangent[bins, q], weights
        )
        for target, value in zip((total, direct, adaptation), values):
            target.append(value / PROBE_JY)
        native_audits.append(source_audits)
    report = fit_transfer(total, direct, adaptation, sample_templates, 1 / variance)
    return {
        **report,
        "probe_jy": PROBE_JY,
        "native_audits": native_audits,
        "TEST_or_truth_used": False,
    }


def choose_slots(records, signal_guards):
    """Fixed two slots from frozen forecasts, never TEST loss or signal truth."""
    eligible = [
        r
        for r in records
        if r.get("guard_pass") and r.get("predicted_benefit", -np.inf) > MINIMUM_BENEFIT
    ]
    ordered = sorted(
        eligible,
        key=lambda r: (
            r["predicted_objective"],
            r["candidate"]["added_fraction"],
            r["mask_id"],
        ),
    )
    safe = [r for r in ordered if signal_guards[r["mask_id"]].get("guard_pass", False)]
    return {
        "without_signal_guard": ordered[0]["mask_id"] if ordered else None,
        "with_signal_guard": safe[0]["mask_id"] if safe else None,
    }


def actual_acceptance(metrics, fixed_tv, baseline_metrics, native_pass, signal_pass):
    score = score_control(metrics, fixed_tv, baseline_metrics)
    support = not any(metrics["invalid_predictions"].values())
    quality = bool(
        score["guard_pass"]
        and native_pass
        and support
        and score["objective"] < 1.25 - MINIMUM_BENEFIT
    )
    return {
        **score,
        "without_signal_guard_accept": quality,
        "with_signal_guard_accept": bool(quality and signal_pass),
        "TEST_loss_or_flux_used": False,
    }


def _solve(directory, state, manifest, proposal, trial, budget, scale=None):
    with budget.operation(
        response.SOLVE_RESERVATION_BYTES, "full-Jones signal-guard QC batch"
    ):
        return solve(
            directory, state, manifest, proposal, trial, *GRID, 50, scale=scale
        )


def _saved(directory, trial):
    return influence._npz(Path(directory) / "trials" / trial / "diagnostics.npz")


def _receipts(prospective):
    files = {
        "guard": Path(__file__),
        **{
            name: Path(module.__file__)
            for name, module in (
                ("influence", influence),
                ("response", response),
                ("prospective", prospective),
            )
        },
    }
    for name in (
        "flagging.py",
        "flagging_signal.py",
        "flagging_workflow.py",
        "flagging_prepared.py",
        "flagging_injections.py",
        "flagging_caracal.py",
        "flagging_trend.py",
        "flagging_balanced.py",
        "flagging_structured.py",
        "flagging_structured_proposals.py",
        "projector.py",
    ):
        files[name] = Path(__file__).parent / name
    native = Path(_native_library()._name).resolve()
    if native != Path(os.environ["RANG_TOY_LIB"]).resolve():
        raise ValueError("loaded Rust library differs from pinned runtime path")
    files["Rust.library"] = native
    return {
        name: {
            "path": str(path.resolve()),
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
        for name, path in files.items()
    }


def _inputs(run_dir, prepared_cases, iterations):
    if (
        type(iterations) is not int
        or iterations != 50
        or not isinstance(prepared_cases, (list, tuple))
        or len(prepared_cases) != 2
    ):
        raise ValueError("frozen50iterations and exactly two case paths required")
    root = Path(run_dir).resolve()
    if root.exists() or Path(run_dir).is_symlink():
        raise ValueError("choose a fresh exclusive signal-guard run")
    inputs = []
    for path in prepared_cases:
        _, source = reject_nested_paths(root, path)
        state = load_state(source)
        manifest = json.loads((source / "manifest.json").read_text())
        metadata = json.loads((source / "injection.json").read_text())
        if (
            metadata["seed"] not in SEEDS
            or metadata["pattern"] != "time-burst"
            or metadata["strength_inverse_weight_units"] != 10
            or metadata["target_train_occupancy"] != 0.005
            or manifest["split_gain_intervals"] != list(GRID)
            or manifest["seed"] != 7
            or len(state["names"]) != 4
            or len(np.unique(state["times"])) != 14
        ):
            raise ValueError(
                "frozen seed107/109 time-burst and native fine split required"
            )
        boundary = validate_prepared_state(source, state, manifest)
        response._audit_native(source, state, manifest["model_column"])
        _outside_train_source_boundary(source, state)
        if response.CONTROL_COLUMN in _columns(source / "work.ms"):
            raise ValueError("prepared source already has diagnostic complete column")
        inputs.append(
            {
                "seed": metadata["seed"],
                "source": source,
                "state": state,
                "manifest": manifest,
                "boundary": boundary,
                "digest": tree_digest(source),
            }
        )
    if (
        sorted(item["seed"] for item in inputs) != list(SEEDS)
        or len({item["source"] for item in inputs}) != 2
    ):
        raise ValueError("exactly distinct seeds107/109 required")
    inputs.sort(key=lambda item: item["seed"])
    for key in (
        "train",
        "validation",
        "test",
        "times",
        "frequencies",
        "antenna1",
        "antenna2",
        "names",
    ):
        if not np.array_equal(inputs[0]["state"][key], inputs[1]["state"][key]):
            raise ValueError("case split/grid/support metadata differ")
    return root, inputs


def _columns(path):
    from casacore.tables import table

    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as work:
        return work.colnames()


def _outside_train_source_boundary(source, state):
    from casacore.tables import table

    with table(
        str(source / "original.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as original:
        raw = original.getcol("DATA")
    if not np.array_equal(
        state["data"][~state["train"]], raw[~state["train"]], equal_nan=True
    ):
        raise ValueError("prepared RFI DATA differs outside frozen TRAIN")


def run(run_dir, prepared_cases, iterations=50):
    """At most18 true QC controls; freeze acceptance before injected TEST fits."""
    root, inputs = _inputs(run_dir, prepared_cases, iterations)
    from . import flagging_prospective as prospective

    budget = response.Budget(root)
    budget.check(response.ALLOCATION_BYTES)
    # Four copied trees, two whole-MS/state backups and two model-state backups.
    copy_forecast = sum(
        2
        * sum(
            response.copy_bound(item["source"] / n)
            for n in ("manifest.json", "state.npz", "original.ms", "work.ms")
        )
        + response.copy_bound(item["source"] / "work.ms")
        + 2 * response.copy_bound(item["source"] / "state.npz")
        for item in inputs
    )
    if copy_forecast + response.SOLVE_RESERVATION_BYTES > response.ALLOCATION_BYTES:
        raise ValueError("conservative copies exceed frozen signal-guard capacity")
    receipts = _receipts(prospective)
    config = {
        "frozen_before_solve": True,
        "seeds": list(SEEDS),
        "inputs": [
            {
                "seed": i["seed"],
                "path": str(i["source"]),
                "digest": i["digest"],
                "raw_source": i["manifest"]["source"],
                "raw_digest": i["manifest"]["source_digest"],
                "boundary": i["boundary"],
            }
            for i in inputs
        ],
        "sources": list(response.SOURCES),
        "reference_hz": response.REFERENCE_HZ,
        "probe_jy": PROBE_JY,
        "absolute_transfer_limit": TRANSFER_LIMIT,
        "grid": list(GRID),
        "iterations": iterations,
        "maximum_QC_solves": MAXIMUM_SOLVES,
        "objective": "TV/TV0+2*f+.25*VAL_MSE/VAL_MSE0",
        "minimum_benefit": MINIMUM_BENEFIT,
        "validation_degradation_limit": 0.01,
        "TEST_or_truth_selects": False,
        "absolute_not_relative_safety": True,
        "copy_forecast_bytes": copy_forecast,
        "allocated_cap_bytes": response.ALLOCATION_BYTES,
        "reserve_bytes": response.RESERVE_BYTES,
        "quota": "checked reservations, not OS-enforced; failures never erased",
        "receipts": receipts,
        "image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "versions": {
            n: version(n)
            for n in (
                "quartical",
                "numpy",
                "stimela",
                "codex-africanus",
                "python-casacore",
            )
        },
        "python_version": platform.python_version(),
    }
    budget.mkdir(root)
    budget.json(root / "signal-guard-config.json", config)
    cases, actual_solves = [], 0
    for item in inputs:
        directory = root / f"time-burst-seed{item['seed']}"
        budget.mkdir(directory)
        clean_dir = directory / "clean"
        state, manifest = response._clone(item["source"], clean_dir, budget)
        zero = np.zeros_like(state["train"])
        metrics, tv, residuals, guidance = _solve(
            clean_dir, state, manifest, zero, "baseline", budget
        )
        actual_solves += 1
        baseline = _saved(clean_dir, "baseline")
        candidates, rankings, stats = prospective.make_shortlist(
            state, baseline, metrics, residuals, guidance
        )
        if len(candidates) > 24 or len({c["mask_id"] for c in candidates}) != len(
            candidates
        ):
            raise ValueError("shared shortlist violates frozen24-unique-mask bound")
        forecast = prospective.forecast_family(state, baseline, metrics, candidates)
        if [r["mask_id"] for r in forecast["records"]] != [
            c["mask_id"] for c in candidates
        ] or forecast["raw_predicted_gains"].shape != (
            len(candidates),
            *baseline["gains"].shape,
        ):
            raise ValueError("shared forecast record/gain alignment differs")
        templates, predicted, error = response._predict(state, clean_dir)
        budget.npz(directory / "templates.npz", templates=templates)
        guards = {
            "nochange": train_signal_guard(
                state, baseline, baseline["gains"], np.empty(0, np.int64), templates
            )
        }
        actions = {candidate["mask_id"]: candidate for candidate in candidates}
        for index, record in enumerate(forecast["records"]):
            identifier = record["mask_id"]
            guards[identifier] = (
                train_signal_guard(
                    state,
                    baseline,
                    forecast["raw_predicted_gains"][index],
                    actions[identifier]["indices"],
                    templates,
                )
                if record["guard_pass"]
                else {
                    "available": False,
                    "guard_pass": False,
                    "reason": "native deletion response refused",
                }
            )
        budget.npz(
            directory / "frozen-TRAIN.npz",
            raw_predicted_gains=forecast["raw_predicted_gains"],
            **{f"action_{i}": c["indices"] for i, c in enumerate(candidates)},
        )
        budget.json(
            directory / "frozen-TRAIN.json",
            {
                "records": forecast["records"],
                "guards": guards,
                "candidates": [
                    {k: v for k, v in c.items() if k != "indices"} for c in candidates
                ],
                "rankings": rankings,
                "stats": stats,
                "predictor_reference_linf_jy": error,
                "TEST_or_truth_used": False,
            },
        )
        cases.append(
            {
                **item,
                "directory": directory,
                "clean_dir": clean_dir,
                "clean": state,
                "manifest": manifest,
                "metrics": metrics,
                "tv": tv,
                "baseline": baseline,
                "forecast": forecast,
                "guards": guards,
                "actions": actions,
                "templates": templates,
                "predicted": predicted,
            }
        )
    budget.json(
        root / "all-TRAIN-frozen.json",
        {
            "cases": [str(c["directory"]) for c in cases],
            "validation_scoring_started": False,
            "TEST_or_truth_used": False,
        },
    )
    for case in cases:
        prospective.score_forecasts(case["clean"], case["forecast"])
        slots = choose_slots(case["forecast"]["records"], case["guards"])
        case["slots"] = slots
        retained = [
            None,
            *dict.fromkeys(value for value in slots.values() if value is not None),
        ]
        case["retained"] = retained
        budget.json(
            case["directory"] / "frozen-slots.json",
            {
                "slots": slots,
                "nochange_retained": True,
                "scored_forecasts": case["forecast"]["records"],
                "TEST_or_flux_used": False,
            },
        )
        clean_arms = {}
        for index, identifier in enumerate(retained):
            proposal = np.zeros_like(case["clean"]["train"])
            if identifier is None:
                armmetrics, armtv, diagnostics = (
                    case["metrics"],
                    case["tv"],
                    case["baseline"],
                )
                trial = "baseline"
            else:
                proposal.flat[case["actions"][identifier]["indices"]] = True
                trial = f"candidate-{index}-{identifier[:12]}"
                armmetrics, armtv, _, _ = _solve(
                    case["clean_dir"],
                    case["clean"],
                    case["manifest"],
                    proposal,
                    trial,
                    budget,
                    case["metrics"]["scale"],
                )
                actual_solves += 1
                diagnostics = _saved(case["clean_dir"], trial)
            fixed_tv = fixed_support_tv(armtv["edges"], case["tv"]["edges"])
            native = (
                identifier is None
                or next(
                    r for r in case["forecast"]["records"] if r["mask_id"] == identifier
                )["guard_pass"]
            )
            signal = case["guards"][identifier or "nochange"].get("guard_pass", False)
            acceptance = actual_acceptance(
                armmetrics, fixed_tv, case["metrics"], native, signal
            )
            clean_arms[identifier] = {
                "proposal": proposal,
                "metrics": armmetrics,
                "diagnostics": diagnostics,
                "trial": trial,
                "acceptance": acceptance,
            }
        case["clean_arms"] = clean_arms
        case["acceptance"] = {
            policy: identifier
            if identifier is not None
            and clean_arms[identifier]["acceptance"][
                "with_signal_guard_accept"
                if policy == "with_signal_guard"
                else "without_signal_guard_accept"
            ]
            else None
            for policy, identifier in slots.items()
        }
    frozen_acceptance = [
        {
            "seed": c["seed"],
            "slots": c["slots"],
            "accepted": c["acceptance"],
            "nochange_signal_certified": c["guards"]["nochange"].get(
                "guard_pass", False
            ),
            "clean_controls": [
                {"mask_id": k, "metrics": a["metrics"], "acceptance": a["acceptance"]}
                for k, a in c["clean_arms"].items()
            ],
        }
        for c in cases
    ]
    budget.json(
        root / "frozen-acceptance.json",
        {
            "cases": frozen_acceptance,
            "source_DATA_injection_started": False,
            "TEST_or_flux_selected": False,
            "nochange_fallback_certified_safe": False,
        },
    )
    acceptance_path = root / "frozen-acceptance.json"
    acceptance_digest = sha256(acceptance_path.read_bytes()).hexdigest()
    for case in cases:
        positive = case["directory"] / "positive"
        state, manifest, delta = response._inject(
            case["source"], positive, 1, case["predicted"], case["baseline"], budget
        )
        case.update(
            {
                "positive_dir": positive,
                "positive": state,
                "positive_manifest": manifest,
                "delta": delta,
                "signal_arms": [],
            }
        )
        for sky in response.SKIES:
            control_state, control_manifest = state, manifest
            if sky == "complete-diagnostic":
                control_state, control_manifest = response._complete_model(
                    positive, state, manifest, case["predicted"], 1, budget
                )
            for index, identifier in enumerate(case["retained"]):
                trial = f"{sky}-mask{index}"
                metrics, tv, _, _ = _solve(
                    positive,
                    control_state,
                    control_manifest,
                    case["clean_arms"][identifier]["proposal"],
                    trial,
                    budget,
                    case["metrics"]["scale"],
                )
                actual_solves += 1
                record = {
                    "seed": case["seed"],
                    "sky": sky,
                    "mask_id": identifier,
                    "trial": trial,
                    "metrics": metrics,
                    "fixed_baseline_edge_TV": fixed_support_tv(
                        tv["edges"], case["tv"]["edges"]
                    ),
                    "acceptance_already_frozen": True,
                }
                budget.json(positive / f"checkpoint-{trial}.json", record)
                case["signal_arms"].append(
                    {**record, "diagnostics": _saved(positive, trial)}
                )
    if actual_solves > MAXIMUM_SOLVES:
        raise RuntimeError("frozen signal-guard solve count exceeded")
    result = _evaluate(cases)
    result["RFI_truth_diagnostics_after_acceptance_freeze"] = _rfi_diagnostics(cases)
    audits = {}
    for case in cases:
        for name, directory, state in (
            ("clean", case["clean_dir"], case["clean"]),
            ("positive", case["positive_dir"], case["positive"]),
        ):
            response._restore_flags(directory, state, budget)
            audit = response._audit_native(
                directory, state, case["manifest"]["model_column"]
            )
            validate_prepared_state(directory, state, case["manifest"])
            if name == "positive":
                from casacore.tables import table

                with table(
                    str(directory / "work.ms"),
                    readonly=True,
                    ack=False,
                    lockoptions="autonoread",
                ) as work:
                    audit["complete_control_column_exact_snapshot"] = np.array_equal(
                        work.getcol(response.CONTROL_COLUMN),
                        influence._npz(directory / "complete-model.npz")["MODEL"],
                    )
            audits[f"seed{case['seed']}/{name}"] = audit
    source_checks = {
        f"seed{c['seed']}/source_unchanged": tree_digest(c["source"]) == c["digest"]
        for c in cases
    }
    source_checks.update(
        {
            f"seed{c['seed']}/raw_unchanged": tree_digest(c["manifest"]["source"])
            == c["manifest"]["source_digest"]
            for c in cases
        }
    )
    source_checks["acceptance_file_unchanged_during_signal_evaluation"] = (
        sha256(acceptance_path.read_bytes()).hexdigest() == acceptance_digest
    )
    runtime_checks = {
        name: sha256(Path(info["path"]).read_bytes()).hexdigest() == info["sha256"]
        for name, info in receipts.items()
    }
    if (
        not all(source_checks.values())
        or not all(runtime_checks.values())
        or not all(all(a.values()) for a in audits.values())
    ):
        raise RuntimeError("signal-guard immutable source/runtime/native audit failed")
    result.update(
        {
            "configuration": config,
            "acceptance": frozen_acceptance,
            "actual_QC_solves": actual_solves,
            "maximum_QC_solves": MAXIMUM_SOLVES,
            "native_flagger_QC_solves": 0,
            "acceptance_file_sha256": acceptance_digest,
            "audit": {
                "sources": source_checks,
                "runtime": runtime_checks,
                "copies": audits,
            },
            "observed_allocated_bytes_before_result": response.allocated_bytes(root),
            "imaging": "not measured in this track; known visibility-template responses only",
            "limitations": [
                "two new seeds on one four-antenna pointing scan, not independent observations",
                "absolute local TRAIN family constraint can refuse every mask; fallback is uncertified",
                "complete truth-sky calibration diagnostic is not deployable policy",
                "shared original noise/RFI and empirical G0 DI corruption, no validated uncertainty or DDE",
                "spectra fixed; no blind flux/slope/image/SOTA or emulated-native-cost claim",
                "checked allocation/reservations, not OS quota",
            ],
        }
    )
    budget.json(root / "signal-guard-audit.json", result["audit"])
    budget.json(root / "result.json", result)
    budget.check()
    print(
        f"Signal guard complete: {actual_solves}QC, TRAIN-only absolute constraint, no TEST/truth selection",
        flush=True,
    )
    return result


def _rfi_diagnostics(cases):
    """Truth is opened only after acceptance freeze and paired QC/evaluation."""
    reports = []
    for case in cases:
        with np.load(case["source"] / "injection.npz", allow_pickle=False) as saved:
            truth = saved["injected"]
        counterfactuals = {
            identifier or "nochange": injection_scores(
                arm["proposal"], truth, case["clean"]["train"]
            )
            for identifier, arm in case["clean_arms"].items()
        }
        accepted = {
            policy: counterfactuals[identifier or "nochange"]
            for policy, identifier in case["acceptance"].items()
        }
        reports.append(
            {
                "seed": case["seed"],
                "counterfactuals": counterfactuals,
                "accepted_policies": accepted,
                "truth_used_to_select": False,
            }
        )
    return reports


def _evaluate(cases):
    """Only called after all acceptance records and paired solves are frozen."""
    row, channel = np.where(cases[0]["clean"]["test"])
    common = np.ones(len(row), bool)
    references, evaluated = {}, []
    for case in cases:
        state, weights = case["clean"], case["clean"]["weights"][row, channel]
        original = state["data"][row, channel]
        refj = response._jones_samples(state, case["baseline"], GRID, row, channel)
        ref = response._correct(case["delta"][row, channel], weights, refj)
        common &= ref[2]
        references[case["seed"]] = (ref, case["templates"][:, row, channel])
        for arm in case["signal_arms"]:
            paired = case["clean_arms"][arm["mask_id"]]
            cleanj = response._jones_samples(
                state, paired["diagnostics"], GRID, row, channel
            )
            jones = response._jones_samples(
                state, arm["diagnostics"], GRID, row, channel
            )
            clean = response._correct(original, weights, cleanj)
            injected = response._correct(
                case["positive"]["data"][row, channel], weights, jones
            )
            direct = response._correct(case["delta"][row, channel], weights, jones)
            original_under = response._correct(original, weights, jones)
            valid = clean[2] & injected[2] & direct[2] & original_under[2]
            common &= valid
            evaluated.append(
                {
                    "record": {k: v for k, v in arm.items() if k != "diagnostics"},
                    "total": injected[0] - clean[0],
                    "direct": direct[0],
                    "adaptation": original_under[0] - clean[0],
                    "valid": valid,
                    "Jones_product_drift": (jones, cleanj),
                }
            )
    if common.sum() < 4:
        raise ValueError("insufficient common TEST; do not change frozen family")
    references_fit = {
        seed: response.linear_response(value[0][0], value[1], 1 / value[0][1], common)
        for seed, value in references.items()
    }
    reports = []
    for arm in evaluated:
        record = arm["record"]
        reference, templates = references[record["seed"]]
        weights = 1 / reference[1]
        fits = {
            name: response.linear_response(arm[name], templates, weights, common)
            for name in ("total", "direct", "adaptation")
        }
        visibility_closure = float(
            np.max(np.abs((arm["total"] - arm["direct"] - arm["adaptation"])[common]))
        )
        fit_closure = (
            float(
                np.max(
                    np.abs(
                        np.asarray(fits["total"]["flux_jy"])
                        - fits["direct"]["flux_jy"]
                        - fits["adaptation"]["flux_jy"]
                    )
                )
            )
            if all(f["available"] for f in fits.values())
            else None
        )
        if visibility_closure > 1e-10 or (
            fit_closure is not None and fit_closure > 1e-10
        ):
            raise RuntimeError("signal-guard evaluation decomposition closure failed")
        denominator = references_fit[record["seed"]]["flux_jy"]
        fractions = [
            v / r if v is not None and r not in (None, 0) else None
            for v, r in zip(fits["total"]["flux_jy"], denominator)
        ]
        reports.append(
            {
                **record,
                "fits": fits,
                "response_fraction_vs_case_fixedG0": fractions,
                "visibility_closure_linf_jy": visibility_closure,
                "coefficient_closure_linf_jy": fit_closure,
                "unsupported_original_TEST": int((~arm["valid"]).sum()),
                "same_mask_Jones_product_relative_drift": response._product_distance(
                    *arm["Jones_product_drift"], weights, common
                ),
            }
        )
    return {
        "status": "measured local TRAIN signal-guard paired calibration diagnostic, not a validated deployable policy",
        "common_TEST_samples": int(common.sum()),
        "original_TEST_samples": len(row),
        "lost_common_TEST_samples": int((~common).sum()),
        "reference_fits": references_fit,
        "methods": reports,
        "TEST_or_truth_used_to_select": False,
    }
