"""The injection campaign on the Rust core (research/core-phase3.md).

Replays `flagging_injections.run` with `core_workflow.core_solve`: the same
clean reference, six injected cases, oracle controls and TV-guided policy grid,
with the selection logic of `_train_policy` kept verbatim. It starts from an
already prepared clean state instead of unpacking and copying a Measurement
Set, regenerates every injection from its seed and checks it against the
saved one, and writes one result.json. Truth is used only for diagnostics.
"""

import json
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .core_workflow import core_solve
from .flagging import fixed_support_tv, policy_mask, residual_features
from .flagging_injections import (
    PATTERNS,
    injection_scores,
    make_injection,
    reference_distance,
)
from .flagging_workflow import load_state


def _json_default(value):
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def _train_policy(state, baseline, base_tv, residuals, guidance, settings, log):
    """`flagging_injections._train_policy` with core solves; truth is absent."""
    zero = np.zeros_like(state["train"])
    tv0 = max(baseline["tv"], 1e-30)
    val0 = baseline["losses"]["validation"]
    if val0 is None or fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None:
        raise ValueError("contaminated baseline has insufficient support")
    val0 = max(val0, 1e-30)
    best_objective = baseline["tv"] / tv0 + 0.25
    best = (baseline, base_tv, residuals, guidance, zero, log["contaminated"])
    candidates = [{**baseline, "objective": best_objective, "policy": None}]
    margins = []
    seen = {sha256(zero.tobytes()).hexdigest()}
    outliers = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    for weight in (0.0, 1.0, 3.0):
        for threshold in (8.0, 5.0, 3.0):
            added = policy_mask(
                outliers,
                guidance,
                state["train"],
                threshold=threshold,
                tv_weight=weight,
                max_fraction=0.02,
            )
            fingerprint = sha256(added.tobytes()).hexdigest()
            policy = {"threshold": threshold, "tv_weight": weight}
            if fingerprint in seen:
                candidates.append(
                    {"policy": policy, "duplicate_mask_sha256": fingerprint}
                )
                continue
            seen.add(fingerprint)
            trial = f"policy-w{weight:g}-z{threshold:g}"
            metrics, tv, candidate_residuals, candidate_guidance, diagnostics = (
                core_solve(
                    state, added, *settings, trial=trial, scale=baseline["scale"]
                )
            )
            log[trial] = diagnostics
            tv_score = fixed_support_tv(tv["edges"], base_tv["edges"])
            val = metrics["losses"]["validation"]
            admissible = tv_score is not None and val is not None and val <= 1.01 * val0
            objective = (
                tv_score / tv0 + 2 * metrics["added_fraction"] + 0.25 * val / val0
                if admissible
                else None
            )
            accepted = bool(admissible and objective < best_objective)
            margins.append(
                {
                    "trial": trial,
                    "objective_minus_best_before": objective - best_objective
                    if objective is not None
                    else None,
                    "validation_ratio": val / val0 if val is not None else None,
                }
            )
            record = {
                **metrics,
                "fixed_contaminated_support_tv": tv_score,
                "objective": objective,
                "policy": policy,
                "accepted": accepted,
            }
            if accepted:
                best_objective = objective
                best = (
                    metrics,
                    tv,
                    candidate_residuals,
                    candidate_guidance,
                    added,
                    diagnostics,
                )
            candidates.append(record)
    return best, candidates, margins


def run(
    run_dir,
    prepared_dir,
    seed=19,
    strengths=(3.0, 10.0),
    patterns=PATTERNS,
    iterations=50,
):
    """Core-native injection campaign from a prepared clean state."""
    start = time.perf_counter()
    run_dir, prepared = Path(run_dir), Path(prepared_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    clean_state = load_state(prepared)
    manifest = json.loads((prepared / "manifest.json").read_text())
    if manifest["split_gain_intervals"] != [2, 32] or manifest["seed"] != 7:
        raise ValueError("prepared input must use the frozen seed-7 2x32 setup")
    settings = (2, 32, iterations)
    zero = np.zeros_like(clean_state["train"])
    clean, clean_tv, _, _, clean_diagnostics = core_solve(
        clean_state, zero, *settings, trial="clean-reference"
    )
    if clean["losses"]["validation"] is None:
        raise ValueError("clean reference predictions unsupported")
    results, recovery, margins, injection_checks = [], [], {}, {}
    for index, pattern in enumerate(patterns):
        for strength in strengths:
            case = f"{pattern}-s{strength:g}"
            mask, delta, metadata = make_injection(
                clean_state, pattern, strength, seed + index
            )
            state = {**clean_state, "data": clean_state["data"] + delta}
            saved_dir = prepared / "cases" / case
            with np.load(saved_dir / "injection.npz") as saved:
                saved_mask, saved_delta = saved["injected"], saved["delta"]
            saved_data = load_state(saved_dir)["data"]
            injection_checks[case] = {
                "mask_equal": bool(np.array_equal(mask, saved_mask)),
                "delta_equal": bool(np.array_equal(delta[mask], saved_delta)),
                "data_equal": bool(np.array_equal(state["data"], saved_data)),
                "metadata_equal": metadata
                == json.loads((saved_dir / "injection.json").read_text()),
            }
            log = {}
            contaminated, contaminated_tv, residuals, guidance, diag_c = core_solve(
                state, zero, *settings, trial="contaminated", scale=clean["scale"]
            )
            log["contaminated"] = diag_c
            oracle, oracle_tv, oracle_residuals, _, diag_o = core_solve(
                state,
                mask,
                *settings,
                trial="injected-mask-oracle",
                scale=clean["scale"],
            )
            best, candidates, margins[case] = _train_policy(
                state, contaminated, contaminated_tv, residuals, guidance, settings, log
            )
            # Archive-only summaries (post-hoc, research/core-phase3.md): the
            # no-change objective and the selection objective of the injected
            # oracle, which never takes part in selection.
            oracle_support_tv = fixed_support_tv(
                oracle_tv["edges"], contaminated_tv["edges"]
            )
            oracle_val = oracle["losses"]["validation"]
            val0 = max(contaminated["losses"]["validation"], 1e-30)
            oracle_objective = (
                oracle_support_tv / max(contaminated["tv"], 1e-30)
                + 2 * oracle["added_fraction"]
                + 0.25 * oracle_val / val0
                if oracle_support_tv is not None and oracle_val is not None
                else None
            )
            selected, selected_tv, selected_residuals, _, selected_mask, diag_s = best
            controls = {}
            for label, metrics, tv, res, added, diagnostic in (
                (
                    "contaminated",
                    contaminated,
                    contaminated_tv,
                    residuals,
                    zero,
                    diag_c,
                ),
                (
                    "injected_mask_oracle",
                    oracle,
                    oracle_tv,
                    oracle_residuals,
                    mask,
                    diag_o,
                ),
                (
                    "selected_policy",
                    selected,
                    selected_tv,
                    selected_residuals,
                    selected_mask,
                    diag_s,
                ),
            ):
                score = fixed_support_tv(tv["edges"], clean_tv["edges"])
                controls[label] = {
                    **metrics,
                    "fixed_clean_support_tv": score,
                    "fixed_clean_support_tv_ratio": score / clean["tv"]
                    if score is not None
                    else None,
                    **injection_scores(added, mask, state["train"]),
                    **reference_distance(
                        state, res, diagnostic, clean_state, clean_diagnostics
                    ),
                }
            results.append(
                {
                    "case": case,
                    "injection": metadata,
                    "controls": controls,
                    "policy_candidates": candidates,
                    "no_change_objective": candidates[0]["objective"],
                    "diagnostic_oracle_objective": oracle_objective,
                    "oracle_was_used_for_selection": False,
                    "selected_additions_sha256": sha256(
                        selected_mask.tobytes()
                    ).hexdigest(),
                }
            )
            recovery.append(
                {
                    "case": case,
                    "candidates": [
                        {
                            "trial": c["trial"],
                            "policy": c.get("policy"),
                            "objective": c.get("objective"),
                            **injection_scores(
                                log[c["trial"]]["added"], mask, state["train"]
                            ),
                        }
                        for c in candidates
                        if "trial" in c
                    ],
                }
            )
    result = {
        "experiment": "Real MeerKAT L-band training-only synthetic RFI controls, Rust core",
        "prepared_dir": str(prepared),
        "configuration": {
            "seed": seed,
            "strengths_inverse_weight_units": list(strengths),
            "patterns": list(patterns),
            "time_interval": 2,
            "freq_interval": 32,
            "iterations": iterations,
            "clean_split_seed": 7,
            "solver": "rang core port of QuartiCal 0.2.7 complex (research/core-phase2.md)",
        },
        "clean_reference": clean,
        "cases": results,
        "post_selection_candidate_recovery": {
            "post_selection_only": True,
            "cases": recovery,
        },
        "injection_checks": injection_checks,
        "objective_margins": margins,
        "seconds_total": time.perf_counter() - start,
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=1, allow_nan=False, default=_json_default) + "\n"
    )
    return result


if __name__ == "__main__":
    import sys

    run(sys.argv[1], sys.argv[2])
