"""The signal-guard track on the Rust core (research/core-phase3c-b.md).

Replays `flagging_signal_guard.run` with `core_workflow.core_solve`. Every
decision and evaluation function is reused unchanged. Prediction, DATA
injection and the complete-sky model, which the original performs through a
Measurement Set, are computed in memory with the same arithmetic and the same
complex64 storage rounding. UVW comes from a frozen export of the case MSs.

With RANG_P6=1 (task P6, research/p6-python-hotspots.md) the guard and the
corrected-intensity algebra run as ported copies that call `numpy.linalg` once
per gain instead of once per cell; results are bit-identical.
"""

import json
import os
import time
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import core, core_trend
from . import core_forecast as prospective
from . import core_influence as influence
from . import core_response as response
from .core_guard import (
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
    fit_transfer,
    train_signal_guard,
)
from .core_policy import fixed_support_tv
from .core_state import load_state
from .core_templates import INVERSE_CONDITION_LIMIT, spatial_templates
from .core_workflow import core_solve

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


def run(run_dir, inputs_dir, uvw_dir, iterations=50, ported=None):
    """Two seeds, frozen TRAIN guards and slots, paired injected-sky arms.

    `ported=True` (or `RANG_P6=1` when `ported` is None) runs the task P6
    ports below; the results are bit-identical apart from wall times.
    """
    if not (enabled() if ported is None else ported):
        return _run(run_dir, inputs_dir, uvw_dir, iterations, train_signal_guard)
    with ported_signal():
        return _run(run_dir, inputs_dir, uvw_dir, iterations, train_signal_guard_p6)


def _run(run_dir, inputs_dir, uvw_dir, iterations, train_signal_guard):
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


# --- Task P6 (research/p6-python-hotspots.md): `cond`/`inv` once per gain ---
#
# Opt-in with RANG_P6=1; unset, `run` makes exactly the frozen calls. The three
# functions below are verbatim copies of the frozen ones in which only the
# `np.linalg.cond`/`np.linalg.inv` calls go through `_per_run`: the cells come
# in row-major (row, channel) order and the solution grid is 2 x 32, so runs
# of consecutive cells carry bit-identical gain matrices. `numpy.linalg` is
# called once per run on the same matrix and its result repeated, which is
# elementwise the same LAPACK call, so the outputs are bit-identical. No
# matrix the frozen code would not have passed to `numpy.linalg` is passed.


def _per_run(function, matrices):
    """`function(matrices)` computed once per run of bit-identical matrices."""
    matrices = np.asarray(matrices)
    flat = np.ascontiguousarray(matrices.reshape(-1, *matrices.shape[-2:]))
    if len(flat) < 2 or (flat.itemsize * flat[0].size) % 8:
        return function(matrices)
    bits = flat.view(np.int64).reshape(len(flat), -1)
    start = np.empty(len(flat), bool)
    start[0] = True
    np.any(bits[1:] != bits[:-1], axis=1, out=start[1:])
    run = np.cumsum(start) - 1
    values = function(flat[start])[run]
    return values.reshape(*matrices.shape[:-2], *values.shape[1:])


def _cond(matrices):
    return _per_run(np.linalg.cond, matrices)


def _inv(matrices):
    return _per_run(np.linalg.inv, matrices)


def corrected_intensity(data, gp, gq, gain_valid, native_weights):
    """`flagging_signal.corrected_intensity` with `cond`/`inv` per gain run."""
    data, native_weights = np.asarray(data), np.asarray(native_weights, float)
    gp, gq = np.asarray(gp), np.asarray(gq)
    valid = np.asarray(gain_valid, bool).copy()
    if (
        data.shape[-1] != 4
        or data.shape != native_weights.shape
        or gp.shape != (*data.shape[:2], 2, 2)
        or gq.shape != gp.shape
        or valid.shape != data.shape[:2]
    ):
        raise ValueError(
            "four correlations and matched per-sample Jones/weights required"
        )
    valid &= (
        np.isfinite(data).all(axis=-1)
        & np.isfinite(native_weights).all(axis=-1)
        & (native_weights > 0).all(axis=-1)
    )
    valid &= np.isfinite(gp).all(axis=(-1, -2)) & np.isfinite(gq).all(axis=(-1, -2))
    # Invalid matrices are never inverted or silently included in a fit.
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    valid &= (_cond(safe_p) <= INVERSE_CONDITION_LIMIT) & (
        _cond(safe_q) <= INVERSE_CONDITION_LIMIT
    )
    safe_p = np.where(valid[..., None, None], gp, np.eye(2))
    safe_q = np.where(valid[..., None, None], gq, np.eye(2))
    inverse_p, inverse_q = _inv(safe_p), _inv(safe_q)
    coefficients = 0.5 * (inverse_q.conj().swapaxes(-1, -2) @ inverse_p).swapaxes(
        -1, -2
    ).reshape(data.shape)
    intensity = np.sum(coefficients * data, axis=-1)
    variance = np.sum(
        np.abs(coefficients) ** 2 / np.where(native_weights > 0, native_weights, 1),
        axis=-1,
    )
    valid &= np.isfinite(intensity) & np.isfinite(variance) & (variance > 0)
    return np.where(valid, intensity, np.nan), np.where(valid, variance, np.nan), valid


def inverse_tangent(data, injected, gp, gq, dp, dq, weights):
    """`flagging_signal_guard.inverse_tangent` with `cond`/`inv` per gain run."""
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
    if (_cond(gp) > 1e8).any() or (_cond(gq) > 1e8).any():
        raise ValueError("TRAIN Jones inverse condition exceeds1e8")
    ip, iq = _inv(gp), _inv(gq)
    iqh = iq.conj().swapaxes(-1, -2)
    corrected = ip @ data.reshape(n, 2, 2) @ iqh
    direct = ip @ injected.reshape(n, 2, 2) @ iqh
    adaptation = -ip @ dp @ corrected - corrected @ (iq @ dq).conj().swapaxes(-1, -2)

    def trace(x):
        return 0.5 * np.trace(x, axis1=-2, axis2=-1)

    return trace(direct + adaptation), trace(direct), trace(adaptation)


def train_signal_guard_p6(state, baseline, predicted_gains, indices, templates):
    """`flagging_signal_guard.train_signal_guard` with `cond`/`inv` per gain run.

    Call inside `ported_signal()` so that `response._correct` also runs the
    ported `corrected_intensity`.
    """
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
        or (_cond(gp) > 1e8).any()
        or (_cond(gq) > 1e8).any()
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


def enabled():
    """True when RANG_P6=1 selects the ported functions (task P6)."""
    return os.environ.get("RANG_P6", "") == "1"


@contextmanager
def ported_signal():
    """Install the ported functions where the frozen modules look them up.

    `corrected_intensity` for `response._correct`, and the prefix-sum
    `core_trend.generate_candidates` for `prospective.make_shortlist`.
    """
    frozen = response.corrected_intensity
    response.corrected_intensity = corrected_intensity
    try:
        with core_trend.ported_candidates(prospective):
            yield
    finally:
        response.corrected_intensity = frozen
