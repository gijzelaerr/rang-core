"""The signal-guard track on the Rust core (research/core-phase3c-b.md).

Replays `flagging_signal_guard.run` with `core_workflow.core_solve`. Every
decision and evaluation function is reused unchanged. Prediction, DATA
injection and the complete-sky model, which the original performs through a
Measurement Set, are computed in memory with the same arithmetic and the same
complex64 storage rounding. UVW comes from a frozen export of the case MSs.
"""

import json
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import core
from . import flagging_prospective as prospective
from . import flagging_response as response
from .core_workflow import core_solve
from .flagging import fixed_support_tv
from .flagging_signal import spatial_templates
from .flagging_signal_guard import (
    GRID,
    MAXIMUM_SOLVES,
    MINIMUM_BENEFIT,
    PROBE_JY,
    SEEDS,
    TRANSFER_LIMIT,
    _evaluate,
    _rfi_diagnostics,
    actual_acceptance,
    choose_slots,
    train_signal_guard,
)
from .flagging_workflow import load_state

ARCMIN = np.pi / 10800


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


def predict(state, uvw):
    """`flagging_response._predict` with the core predictor for africanus."""
    sources = response.SOURCES
    freqs = state["frequencies"]
    spatial = spatial_templates(uvw, freqs, sources)
    spectra = np.asarray(
        [(freqs / response.REFERENCE_HZ) ** s["spectral_index"] for s in sources]
    )
    templates = spatial * spectra[:, None]
    reference = np.sum(
        np.asarray([s["flux_jy"] for s in sources])[:, None, None] * templates, axis=0
    )
    predicted = core.predict_components(
        uvw,
        freqs,
        np.asarray([[s["l_arcmin"], s["m_arcmin"]] for s in sources]) * ARCMIN,
        np.asarray([0 if s["fwhm_arcmin"] == 0 else 1 for s in sources]),
        np.asarray([s["flux_jy"] for s in sources]),
        np.asarray([[s["spectral_index"]] for s in sources]),
        np.ones(len(sources), bool),
        np.full(len(sources), response.REFERENCE_HZ),
        np.asarray([[s["fwhm_arcmin"] * ARCMIN] * 2 + [0] for s in sources]),
    )
    np.testing.assert_allclose(predicted, reference, rtol=1e-11, atol=1e-12)
    return templates, predicted, float(np.max(np.abs(predicted - reference)))


def inject(state, sign, predicted, reference_gains):
    """`flagging_response._inject` in memory: DATA stored as complex64."""
    state = dict(state)
    eligible = state["train"] | state["validation"] | state["test"]
    row, channel = np.where(eligible)
    gp, gq, good = response._jones_samples(
        state, reference_gains, response.GRIDS[0], row, channel
    )
    if not good.all():
        raise ValueError(
            "fine reference gains must support every frozen injection cell"
        )
    delta = (
        gp
        @ (sign * predicted[row, channel, None, None] * np.eye(2))
        @ gq.conj().swapaxes(-1, -2)
    ).reshape(len(row), 4)
    original_data = state["data"]
    new_data = original_data.copy()
    new_data[row, channel] = original_data[row, channel] + delta
    actual_delta = np.zeros_like(original_data, dtype=np.complex128)
    actual_delta[row, channel] = new_data[row, channel].astype(
        np.complex128
    ) - original_data[row, channel].astype(np.complex128)
    state["data"] = new_data
    return state, actual_delta


def complete_model(state, scalar, sign):
    """`flagging_response._complete_model` in memory: model stored at its dtype."""
    unrounded = state["model"].astype(np.complex128)
    unrounded[..., 0] += sign * scalar
    unrounded[..., 3] += sign * scalar
    complete = dict(state)
    complete["model"] = unrounded.astype(state["model"].dtype)
    return complete


def _inputs(inputs_dir, uvw_dir):
    inputs = []
    for seed in SEEDS:
        name = f"time-burst-seed{seed}"
        source = Path(inputs_dir) / "cases" / name
        state = load_state(source)
        manifest = json.loads((source / "manifest.json").read_text())
        metadata = json.loads((source / "injection.json").read_text())
        if (
            metadata["seed"] != seed
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
        with np.load(Path(uvw_dir) / name / "arrays.npz") as saved:
            exported = {k: saved[k] for k in saved.files}
        if not (
            np.array_equal(exported["ANTENNA1"], state["antenna1"])
            and np.array_equal(exported["ANTENNA2"], state["antenna2"])
            and np.array_equal(exported["TIME"], state["times"])
        ):
            raise ValueError("exported UVW rows do not match the prepared state")
        inputs.append(
            {
                "seed": seed,
                "source": source,
                "state": state,
                "manifest": manifest,
                "uvw": exported["UVW"],
            }
        )
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
    return inputs


def run(run_dir, inputs_dir, uvw_dir, iterations=50):
    """Two seeds, frozen TRAIN guards and slots, paired injected-sky arms."""
    if iterations != 50:
        raise ValueError("frozen 50-iteration solve required")
    started = time.perf_counter()
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=False)
    inputs = _inputs(inputs_dir, uvw_dir)
    config = {
        "seeds": list(SEEDS),
        "sources": list(response.SOURCES),
        "reference_hz": response.REFERENCE_HZ,
        "probe_jy": PROBE_JY,
        "absolute_transfer_limit": TRANSFER_LIMIT,
        "grid": list(GRID),
        "iterations": iterations,
        "maximum_QC_solves": MAXIMUM_SOLVES,
        "minimum_benefit": MINIMUM_BENEFIT,
        "solver": "rang core port of QuartiCal 0.2.7 complex (research/core-phase2.md)",
        "predictor": "rang core port of africanus wsclean_predict (research/core-phase3c-a.md)",
    }
    cases, actual_solves = [], 0
    for item in inputs:
        state = dict(item["state"])
        zero = np.zeros_like(state["train"])
        metrics, tv, residuals, guidance, baseline = core_solve(
            state, zero, *GRID, iterations, trial="baseline"
        )
        actual_solves += 1
        candidates, _rankings, _stats = prospective.make_shortlist(
            state, baseline, metrics, residuals, guidance
        )
        if len(candidates) > 24 or len({c["mask_id"] for c in candidates}) != len(
            candidates
        ):
            raise ValueError("shared shortlist violates frozen24-unique-mask bound")
        forecast = prospective.forecast_family(state, baseline, metrics, candidates)
        templates, predicted, error = predict(state, item["uvw"])
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
        cases.append(
            {
                **item,
                "clean": state,
                "metrics": metrics,
                "tv": tv,
                "baseline": baseline,
                "forecast": forecast,
                "guards": guards,
                "actions": actions,
                "templates": templates,
                "predicted": predicted,
                "predictor_reference_linf_jy": error,
            }
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
                armmetrics, armtv, _, _, diagnostics = core_solve(
                    case["clean"],
                    proposal,
                    *GRID,
                    iterations,
                    trial=trial,
                    scale=case["metrics"]["scale"],
                )
                actual_solves += 1
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
    acceptance_digest = sha256(
        json.dumps(frozen_acceptance, sort_keys=True, default=_json_default).encode()
    ).hexdigest()
    for case in cases:
        state, delta = inject(case["state"], 1, case["predicted"], case["baseline"])
        case.update({"positive": state, "delta": delta, "signal_arms": []})
        for sky in response.SKIES:
            control_state = state
            if sky == "complete-diagnostic":
                control_state = complete_model(state, case["predicted"], 1)
            for index, identifier in enumerate(case["retained"]):
                trial = f"{sky}-mask{index}"
                metrics, tv, _, _, diagnostics = core_solve(
                    control_state,
                    case["clean_arms"][identifier]["proposal"],
                    *GRID,
                    iterations,
                    trial=trial,
                    scale=case["metrics"]["scale"],
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
                case["signal_arms"].append({**record, "diagnostics": diagnostics})
    if actual_solves > MAXIMUM_SOLVES:
        raise RuntimeError("frozen signal-guard solve count exceeded")
    result = _evaluate(cases)
    result["RFI_truth_diagnostics_after_acceptance_freeze"] = _rfi_diagnostics(cases)
    result.update(
        {
            "configuration": config,
            "acceptance": frozen_acceptance,
            "actual_QC_solves": actual_solves,
            "maximum_QC_solves": MAXIMUM_SOLVES,
            "native_flagger_QC_solves": 0,
            "acceptance_digest_core": acceptance_digest,
            "predictor_reference_linf_jy": {
                c["seed"]: c["predictor_reference_linf_jy"] for c in cases
            },
            "seconds_total": time.perf_counter() - started,
        }
    )
    (root / "result.json").write_text(
        json.dumps(result, indent=1, allow_nan=False, default=_json_default) + "\n"
    )
    return result
