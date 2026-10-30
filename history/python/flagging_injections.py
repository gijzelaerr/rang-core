"""Controlled, recoverable RFI injections on real MeerKAT L-band data.

Injection truth is used only for diagnostics and the oracle control. Policy
features and selection cannot access it. Every solve uses QuartiCal complex 2x2.
"""

import json
import shutil
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging import (
    assert_preserved,
    fixed_support_tv,
    policy_mask,
    residual_features,
)
from .flagging_workflow import (
    load_state,
    prepare,
    set_flags,
    solve,
    tree_digest,
    write_json,
)

PATTERNS = ("narrowband", "time-burst", "antenna-local")


def make_injection(state, pattern, strength, seed, occupancy=0.005):
    """Make a reproducible small time/frequency/station patch on train only.

    Strength is complex visibility amplitude in original inverse-weight units,
    not a claim of measured thermal-noise sigma. All four correlations receive
    the same normalized additive phasor, with native per-correlation weights.
    These simple morphological controls are not a physical RFI simulator.
    """
    if pattern not in PATTERNS:
        raise ValueError("unknown injection pattern")
    if not np.isfinite(strength) or strength <= 0 or not 0 < occupancy < 0.1:
        raise ValueError("positive strength and small occupancy required")
    train = np.asarray(state["train"], dtype=bool)
    flags = state["original_flags"]
    if train.shape != flags.shape[:2]:
        raise ValueError("train mask and original flags have different shapes")
    protected = flags.any(axis=-1) | state["original_rows"][:, None]
    if np.any(train & protected):
        raise ValueError("training mask includes original protected samples")
    if np.any(train & (state["validation"] | state["test"])):
        raise ValueError("training and holdout masks overlap")
    p, q = state["antenna1"], state["antenna2"]
    if np.any(train & (p == q)[:, None]):
        raise ValueError("training contains autocorrelations")
    rng = np.random.default_rng(seed)
    channels = np.flatnonzero(state["window"])
    times = np.unique(state["times"])
    if not len(channels) or not len(times) or not train.any():
        raise ValueError("nonempty eligible data required")
    row_support = p != q
    selected_time = None
    selected_antenna = None
    if pattern == "time-burst":
        available_times = np.unique(state["times"][train.any(axis=1)])
        selected_time = float(rng.choice(available_times))
        row_support &= state["times"] == selected_time
    elif pattern == "antenna-local":
        antennas = np.unique(np.r_[p[train.any(axis=1)], q[train.any(axis=1)]])
        selected_antenna = int(rng.choice(antennas))
        row_support &= (p == selected_antenna) | (q == selected_antenna)
    target = max(1, int(occupancy * train.sum()))
    eligible_per_channel = train[row_support].sum(axis=0)
    width = max(1, int(np.ceil(target / max(eligible_per_channel[channels].mean(), 1))))
    width = min(width, len(channels))
    # Pick a contiguous, sufficiently populated patch, avoiding a fully flagged
    # band island. The choice does not inspect DATA, gains or held-out residuals.
    candidates = np.array(
        [
            i
            for i in range(len(channels) - width + 1)
            if np.all(np.diff(channels[i : i + width]) == 1)
            and eligible_per_channel[channels[i : i + width]].sum() >= target / 2
        ]
    )
    if not len(candidates):
        raise ValueError("no populated contiguous injection patch")
    first = int(rng.choice(candidates))
    selected_channels = channels[first : first + width]
    channel_support = np.zeros(train.shape[1], bool)
    channel_support[selected_channels] = True
    mask = train & row_support[:, None] & channel_support[None]
    if np.any(mask & protected) or np.any(mask & ~train) or not mask.any():
        raise ValueError("injection violated protected/training support")
    weights = state["weights"][mask]
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("finite positive native weights required")
    # A largely coherent patch, with small sample-to-sample phase jitter.
    phase = rng.uniform(-np.pi, np.pi) + rng.normal(0, 0.15, mask.sum())
    phasor = np.exp(1j * phase)
    if selected_antenna is not None:
        rows = np.nonzero(mask)[0]
        phasor = np.where(p[rows] == selected_antenna, phasor, phasor.conj())
    delta = np.zeros_like(state["data"])
    delta[mask] = strength * phasor[:, None] / np.sqrt(weights)
    metadata = {
        "pattern": pattern,
        "seed": int(seed),
        "strength_inverse_weight_units": float(strength),
        "target_train_occupancy": float(occupancy),
        "actual_train_occupancy": float(mask.sum() / train.sum()),
        "injected_row_channel_count": int(mask.sum()),
        "channels": [int(selected_channels[0]), int(selected_channels[-1] + 1)],
        "time": selected_time,
        "antenna": selected_antenna,
        "delta_abs_jy_quantiles": np.quantile(
            np.abs(delta[mask]), [0, 0.5, 1]
        ).tolist(),
        "mask_sha256": sha256(mask.tobytes()).hexdigest(),
        "truth_used_by_policy": False,
    }
    return mask, delta, metadata


def injection_scores(added, truth, train):
    """Do not mislabel extra flags on an unlabeled real observation as false RFI."""
    added, truth, train = [np.asarray(x, bool) for x in (added, truth, train)]
    if not (added.shape == truth.shape == train.shape):
        raise ValueError("score masks have different shapes")
    if np.any((added | truth) & ~train):
        raise ValueError("score masks extend outside training")
    recovered = int(np.count_nonzero(added & truth))
    outside = int(np.count_nonzero(added & ~truth))
    return {
        "injection_recall": recovered / int(truth.sum()) if truth.any() else None,
        "recovered_injected_samples": recovered,
        "additions_outside_injections": outside,
        "outside_injection_train_fraction": outside / int(train.sum()),
        "added_fraction": float(added.sum() / train.sum()),
        "outside_additions_are_not_proven_false_positives": True,
    }


def _diagnostics(directory):
    with np.load(Path(directory) / "diagnostics.npz", allow_pickle=False) as saved:
        return {key: saved[key] for key in saved.files}


def score_archived_candidates(run_dir):
    """Post-selection truth diagnostics; never called by policy selection."""
    run_dir = Path(run_dir)
    result = json.loads((run_dir / "result.json").read_text())
    reports = []
    for case in result["cases"]:
        directory = run_dir / "cases" / case["case"]
        state = load_state(directory)
        with np.load(directory / "injection.npz", allow_pickle=False) as saved:
            truth = saved["injected"]
        candidates = []
        for candidate in case["policy_candidates"]:
            if "trial" not in candidate:
                continue
            diagnostics = _diagnostics(directory / "trials" / candidate["trial"])
            candidates.append(
                {
                    "trial": candidate["trial"],
                    "policy": candidate.get("policy"),
                    "objective": candidate.get("objective"),
                    **injection_scores(diagnostics["added"], truth, state["train"]),
                }
            )
        report = {"case": case["case"], "candidates": candidates}
        write_json(directory / "candidate-recovery.json", report)
        reports.append(report)
    write_json(
        run_dir / "candidate-recovery.json",
        {"post_selection_only": True, "cases": reports},
    )
    return reports


def reference_distance(state, residuals, diagnostics, clean_state, clean_diagnostics):
    """Compare fixed clean prediction/gain support; never drop unsupported bins."""
    prediction = state["data"] - residuals
    clean_prediction = clean_state["data"] - clean_diagnostics["residuals"]
    clean_valid = clean_diagnostics["tv_valid"]
    valid = diagnostics["tv_valid"]
    unsupported = int(np.count_nonzero(clean_valid & ~valid))
    gain_distance = (
        float(
            np.mean(
                np.abs(
                    diagnostics["gauge_gains"][clean_valid]
                    - clean_diagnostics["gauge_gains"][clean_valid]
                )
                ** 2
            )
        )
        if not unsupported
        else None
    )
    prediction_mse = np.mean(
        np.abs(prediction - clean_prediction) ** 2 * clean_state["weights"], axis=-1
    )
    return {
        "unsupported_clean_gain_bins": unsupported,
        "polar_gauge_gain_mse_to_clean": gain_distance,
        "weighted_prediction_mse_to_clean": {
            split: float(np.mean(prediction_mse[clean_state[split]]))
            if np.isfinite(prediction_mse[clean_state[split]]).all() and not unsupported
            else None
            for split in ("validation", "test")
        },
    }


def _write_data(run_dir, data, label):
    """Exclusive full-column backup before every DATA write, then exact check."""
    from casacore.tables import table

    run_dir = Path(run_dir)
    backup = run_dir / "backups" / f"{label}-data-before.npz"
    with table(str(run_dir / "work.ms"), readonly=False, ack=False) as work:
        before = work.getcol("DATA")
        with backup.open("xb") as stream:
            np.savez_compressed(stream, DATA=before)
        work.putcol("DATA", data)
        work.flush()
        np.testing.assert_array_equal(work.getcol("DATA"), data)
    return sha256(backup.read_bytes()).hexdigest()


def _train_policy(
    run_dir, state, manifest, baseline, base_tv, residuals, guidance, settings
):
    """Existing interpretable TV policy; injection truth is absent from this API."""
    zero = np.zeros_like(state["train"])
    tv0 = max(baseline["tv"], 1e-30)
    val0 = baseline["losses"]["validation"]
    if val0 is None or fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None:
        raise ValueError("contaminated baseline has insufficient support")
    val0 = max(val0, 1e-30)
    best_objective = baseline["tv"] / tv0 + 0.25
    best = (baseline, base_tv, residuals, guidance, zero)
    candidates = [{**baseline, "objective": best_objective, "policy": None}]
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
            metrics, tv, candidate_residuals, candidate_guidance = solve(
                run_dir,
                state,
                manifest,
                added,
                trial,
                *settings,
                scale=baseline["scale"],
            )
            tv_score = fixed_support_tv(tv["edges"], base_tv["edges"])
            val = metrics["losses"]["validation"]
            admissible = tv_score is not None and val is not None and val <= 1.01 * val0
            objective = (
                tv_score / tv0 + 2 * metrics["added_fraction"] + 0.25 * val / val0
                if admissible
                else None
            )
            accepted = bool(admissible and objective < best_objective)
            record = {
                **metrics,
                "fixed_contaminated_support_tv": tv_score,
                "objective": objective,
                "policy": policy,
                "accepted": accepted,
            }
            if accepted:
                best_objective = objective
                best = (metrics, tv, candidate_residuals, candidate_guidance, added)
            candidates.append(record)
            write_json(Path(run_dir) / "trials" / trial / "selection.json", record)
    write_json(
        Path(run_dir) / "policy-selection.json",
        {
            "selected_trial": best[0]["trial"],
            "objective": best_objective,
            "candidates": candidates,
        },
    )
    return best, candidates


def run(
    run_dir,
    archive,
    seed=19,
    strengths=(3.0, 10.0),
    patterns=PATTERNS,
    iterations=50,
):
    """Stimela2 callable: clean, contaminated, injection-oracle and policy controls."""
    from casacore.tables import table

    start = time.perf_counter()
    run_dir = Path(run_dir).resolve()
    if not patterns or any(pattern not in PATTERNS for pattern in patterns):
        raise ValueError("at least one supported pattern required")
    if not strengths or any(not np.isfinite(x) or x <= 0 for x in strengths):
        raise ValueError("positive finite injection strengths required")
    # Keep the established seed=7 train/validation/test split for comparability.
    prepare(run_dir, archive=archive, seed=7)
    clean_state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    settings = (2, 32, iterations)
    zero = np.zeros_like(clean_state["train"])
    clean, clean_tv, _, _ = solve(
        run_dir, clean_state, manifest, zero, "clean-reference", *settings
    )
    if clean["losses"]["validation"] is None:
        raise ValueError("clean reference predictions unsupported")
    clean_diagnostics = _diagnostics(run_dir / "trials/clean-reference")
    set_flags(run_dir, clean_state, zero, "clean-reference-final", holdout=False)
    config = {
        "seed": seed,
        "strengths_inverse_weight_units": list(strengths),
        "patterns": list(patterns),
        "time_interval": 2,
        "freq_interval": 32,
        "iterations": iterations,
        "clean_split_seed": 7,
        "policy_max_fraction": 0.02,
        "policy_thresholds": [8, 5, 3],
        "policy_tv_weights": [0, 1, 3],
        "policy_objective": "fixed_contaminated_support_TV/TV0 + 2*f + 0.25*clean_validation_MSE/MSEval0",
        "diagnostic_tv_reference": "fixed clean gain-edge support and normalization scale",
        "injection_truth_for_selection": False,
        "test_for_selection": False,
        "timings": "Linux amd64 under emulation; not native performance evidence",
    }
    write_json(run_dir / "injection-config.json", config)
    results = []
    for index, pattern in enumerate(patterns):
        for strength in strengths:
            case = f"{pattern}-s{strength:g}"
            directory = run_dir / "cases" / case
            directory.mkdir(parents=True, exist_ok=False)
            (directory / "backups").mkdir()
            shutil.copytree(run_dir / "work.ms", directory / "work.ms")
            shutil.copytree(run_dir / "original.ms", directory / "original.ms")
            mask, delta, metadata = make_injection(
                clean_state, pattern, strength, seed + index
            )
            state = {**clean_state, "data": clean_state["data"] + delta}
            with (directory / "state.npz").open("xb") as stream:
                np.savez_compressed(stream, **state)
            write_json(directory / "manifest.json", manifest)
            with (directory / "injection.npz").open("xb") as stream:
                np.savez_compressed(stream, injected=mask, delta=delta[mask])
            write_json(directory / "injection.json", metadata)
            backup_hash = _write_data(directory, state["data"], "injection")
            contaminated, contaminated_tv, residuals, guidance = solve(
                directory,
                state,
                manifest,
                zero,
                "contaminated",
                *settings,
                scale=clean["scale"],
            )
            oracle, oracle_tv, oracle_residuals, _ = solve(
                directory,
                state,
                manifest,
                mask,
                "injected-mask-oracle",
                *settings,
                scale=clean["scale"],
            )
            best, candidates = _train_policy(
                directory,
                state,
                manifest,
                contaminated,
                contaminated_tv,
                residuals,
                guidance,
                settings,
            )
            selected, selected_tv, selected_residuals, _, selected_mask = best
            controls = {}
            for label, metrics, tv, res, added in (
                ("contaminated", contaminated, contaminated_tv, residuals, zero),
                ("injected_mask_oracle", oracle, oracle_tv, oracle_residuals, mask),
                (
                    "selected_policy",
                    selected,
                    selected_tv,
                    selected_residuals,
                    selected_mask,
                ),
            ):
                diagnostic = _diagnostics(directory / "trials" / metrics["trial"])
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
            set_flags(
                directory, state, selected_mask, "selected-policy-final", holdout=False
            )
            with (directory / "selected-additions.npz").open("xb") as stream:
                np.savez_compressed(stream, added=selected_mask)
            with table(str(directory / "work.ms"), readonly=True, ack=False) as work:
                final_data = work.getcol("DATA")
                np.testing.assert_array_equal(
                    final_data[~mask], clean_state["data"][~mask]
                )
                np.testing.assert_array_equal(final_data, state["data"])
                assert_preserved(
                    clean_state["original_flags"],
                    clean_state["original_rows"],
                    work.getcol("FLAG"),
                    work.getcol("FLAG_ROW"),
                )
            record = {
                "case": case,
                "injection": metadata,
                "controls": controls,
                "data_backup_sha256": backup_hash,
                "policy_candidates": candidates,
                "audit": {
                    "original_flags_preserved": True,
                    "heldout_data_unchanged": True,
                    "protected_data_unchanged": True,
                    "injection_training_only": True,
                    "final_work_ms_is_synthetic_contaminated_copy": True,
                },
            }
            write_json(directory / "result.json", record)
            results.append(record)
            write_json(run_dir / f"checkpoint-{len(results):02}.json", record)
            print(f"Completed {case}: selected {selected['trial']}", flush=True)
    source_preserved = tree_digest(manifest["source"]) == manifest["source_digest"]
    original_preserved = (
        tree_digest(run_dir / "original.ms") == manifest["original_copy_digest"]
    )
    if not source_preserved or not original_preserved:
        raise RuntimeError("immutable source or original MS was modified")
    result = {
        "experiment": "Real MeerKAT L-band training-only synthetic RFI controls",
        "manifest": manifest,
        "configuration": config,
        "clean_reference": clean,
        "cases": results,
        "seconds_total": time.perf_counter() - start,
        "audit": {
            "source_unchanged": source_preserved,
            "original_copy_unchanged": original_preserved,
        },
        "limitations": [
            "Four antennas and a short reference pointing scan; not an imaging benchmark.",
            "Injected morphology is synthetic; unmodified real data contain unlabeled contamination.",
            "Approximate scalar calibrator model retained; model adequacy tested separately.",
            "One injection seed per morphology; no statistical significance claim.",
        ],
    }
    write_json(run_dir / "result.json", result)
    score_archived_candidates(run_dir)
    print(
        f"Injection experiment complete; immutable originals verified: {run_dir}",
        flush=True,
    )
