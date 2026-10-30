"""TRAIN-only local signal transfer constraint with frozen paired QC controls.

Verbatim extract of the frozen `rangtoy.flagging_signal_guard` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_signal_guard.py at commit
2da566c (now history/python/flagging_signal_guard.py),
sha256 85b114ecf554edae2ede1fddeeb2309b0cabcfdedce733c84940eabff98aea29.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

import numpy as np

from . import core_influence as influence
from . import core_response as response
from .core_controls import score_control
from .core_injection_model import injection_scores

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
