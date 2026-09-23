"""Matched real-MeerKAT flagger comparisons with immutable input lower bounds.

QuartiCal MAD runs on a dedicated copy, then its proposals are frozen before
calibration. Tricolour's genuine SumThreshold kernel runs in an isolated legacy
Numba environment on training-only windows; it never opens a Measurement Set.
"""

import argparse
import json
import os
import shutil
import subprocess
import time
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .flagging import (
    assert_preserved,
    fixed_support_tv,
    policy_mask,
    protected_flags,
    residual_features,
    snapshot_flags,
)
from .flagging_prepared import reject_nested_paths, validate_prepared_state
from .flagging_workflow import (
    load_state,
    prepare,
    set_flags,
    solve,
    tree_digest,
    write_json,
)

TRICOLOUR_WHEEL_SHA256 = (
    "7dd8dfcf8058bdc7351540d4d6248664169bab1debf8791234e9fa8846f1c63b"
)
SOURCES = {
    "quartical_options": "https://quartical.readthedocs.io/en/latest/options.html",
    "tricolour_source": "https://github.com/ratt-ru/tricolour",
    "tricolour_paper": "https://arxiv.org/abs/2206.09179",
}


def import_proposals(state, flags, rows=None):
    """Only eligible training row/channels may acquire comparison flags."""
    flags = np.asarray(flags, bool)
    if flags.shape != state["original_flags"].shape:
        raise ValueError("flagger output shape differs from original FLAG")
    if rows is not None:
        rows = np.asarray(rows, bool)
        if rows.shape != state["original_rows"].shape:
            raise ValueError("flagger output FLAG_ROW shape differs from original")
        flags = flags | rows[:, None, None]
    return flags.any(axis=-1) & state["train"]


def pack_training_windows(state):
    """Pack absolute Stokes-I proxy into baseline,correlation,time,frequency.

    Random holdouts retain their coordinates but are flagged and numerically
    zeroed. Missing baseline/time cells are masked. Duplicates are rejected
    rather than averaged, so the calibration problem stays unchanged.
    """
    times, inverse = np.unique(state["times"], return_inverse=True)
    p, q = state["antenna1"], state["antenna2"]
    baselines = sorted(set(zip(p[p != q].tolist(), q[p != q].tolist())))
    index = {baseline: i for i, baseline in enumerate(baselines)}
    windows = np.zeros((len(baselines), 1, len(times), state["train"].shape[1]))
    flags = np.ones(windows.shape, bool)
    row_map = np.full((len(baselines), len(times)), -1, dtype=np.int64)
    intensity = np.abs((state["data"][..., 0] + state["data"][..., 3]) / 2)
    for row, baseline in enumerate(zip(p.tolist(), q.tolist())):
        if baseline not in index:
            continue
        b, t = index[baseline], inverse[row]
        if row_map[b, t] >= 0:
            raise ValueError("duplicate baseline/time cells are unsupported")
        row_map[b, t] = row
        flags[b, 0, t] = ~state["train"][row]
        windows[b, 0, t] = np.where(state["train"][row], intensity[row], 0)
    return windows, flags, row_map


def unpack_proposals(flags, row_map, train):
    flags = np.asarray(flags, bool)
    if flags.shape != (*row_map.shape[:1], 1, row_map.shape[1], train.shape[1]):
        raise ValueError("unexpected Tricolour flag-window shape")
    added = np.zeros_like(train)
    for b, t in zip(*np.where(row_map >= 0)):
        row = row_map[b, t]
        added[row] = flags[b, 0, t] & train[row]
    return added


def injection_recovery(added, injected, train):
    """Known-addition recall, not pre-existing-RFI ground truth."""
    added, injected, train = (
        np.asarray(value, bool) for value in (added, injected, train)
    )
    if added.shape != train.shape or injected.shape != train.shape:
        raise ValueError("injection, proposal and training masks must match")
    known = injected & train
    recovered = added & known
    outside = added & train & ~known
    return {
        "known_injected_training_samples": int(known.sum()),
        "recovered_injected_samples": int(recovered.sum()),
        "injected_recall": float(recovered.sum() / known.sum())
        if known.any()
        else None,
        "additional_flags_outside_injections": int(outside.sum()),
        "outside_injections_fraction": float(
            outside.sum() / np.count_nonzero(train & ~known)
        )
        if (train & ~known).any()
        else None,
        "outside_injections_are_not_labelled_false_positives": True,
    }


def tricolour_worker(
    input_path, output_path, metadata_path, threshold, morphology="holdout-safe"
):
    """Executed only with the independently pinned Tricolour interpreter."""
    from tricolour.flagging import sum_threshold_flagger

    with np.load(input_path, allow_pickle=False) as saved:
        windows, flags = saved["windows"], saved["flags"]
    # Published package's background pass followed by its narrow final pass.
    # No static mask or UV polynomial subtraction: not the full default pipeline.
    settings = {
        "outlier_nsigma": float(threshold),
        "windows_time": [1, 2, 4, 8],
        "windows_freq": [1, 2, 4, 8],
        "background_reject": 2.0,
        "background_iterations": 5,
        "spike_width_time": 12.5,
        "spike_width_freq": 10.0,
        "time_extend": 3,
        "freq_extend": 3,
        "freq_chunks": 10,
        "average_freq": 1,
        "flag_all_time_frac": 0.6,
        "flag_all_freq_frac": 0.8,
        "rho": 1.3,
        "num_major_iterations": 5,
    }
    if morphology == "holdout-safe":
        # Package dilation otherwise expands masked holdouts as though they were
        # detected interference. Retain background/SumThreshold without expanding
        # missing training support into additional flags.
        settings.update(
            time_extend=1, freq_extend=1, flag_all_time_frac=1.0, flag_all_freq_frac=1.0
        )
    elif morphology != "package":
        raise ValueError("unknown Tricolour morphology mode")
    started = time.perf_counter()
    result = flags | sum_threshold_flagger(windows, flags, **settings)
    narrow = {**settings, "spike_width_time": 2.0, "num_major_iterations": 1}
    result |= sum_threshold_flagger(windows, result, **narrow)
    elapsed = time.perf_counter() - started
    with Path(output_path).open("xb") as stream:
        np.savez_compressed(stream, flags=result)
    write_json(
        metadata_path,
        {
            "kind": "Tricolour SumThreshold background+narrow subset",
            "morphology": morphology,
            "settings": [settings, narrow],
            "seconds": elapsed,
            "versions": {
                name: version(name)
                for name in ("tricolour", "numpy", "numba", "llvmlite", "scipy")
            },
            "wheel_sha256": TRICOLOUR_WHEEL_SHA256,
        },
    )


def audit_ms(path, state):
    from casacore.tables import table

    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as ms:
        flags, rows = ms.getcol("FLAG"), ms.getcol("FLAG_ROW")
        assert_preserved(state["original_flags"], state["original_rows"], flags, rows)
        data_preserved = np.array_equal(
            ms.getcol("DATA"), state["data"], equal_nan=True
        )
        weights = (
            ms.getcol("WEIGHT_SPECTRUM")
            if "WEIGHT_SPECTRUM" in ms.colnames()
            else np.broadcast_to(ms.getcol("WEIGHT")[:, None], state["weights"].shape)
        )
        weights_preserved = np.array_equal(weights, state["weights"], equal_nan=True)
    if not data_preserved or not weights_preserved:
        raise RuntimeError("flagger changed original DATA or weights")
    return {
        "original_flags_preserved": True,
        "original_rows_preserved": True,
        "data_preserved": data_preserved,
        "weights_preserved": weights_preserved,
    }


def mad_proposal(run_dir, state, threshold_bl, threshold_global, whitening):
    from casacore.tables import table

    name = f"mad-{whitening}-bl{threshold_bl:g}-global{threshold_global:g}"
    directory = run_dir / "flaggers" / name
    directory.mkdir(parents=True, exist_ok=False)
    # Never allow native flag writing into our evaluation MS or immutable input.
    copy = directory / "work.ms"
    shutil.copytree(run_dir / "work.ms", copy)
    snapshot_flags(
        directory / "flags-before.npz",
        state["original_flags"],
        state["original_rows"],
    )
    baseline_command = json.loads(
        (run_dir / "trials/baseline/command.json").read_text()
    )
    replacements = {
        "input_ms.path": str(copy),
        "mad_flags.enable": "true",
        "output.flags": "true",
        "output.gain_directory": str(directory / "gains.qc"),
        "output.log_directory": str(directory / "logs.qc"),
    }
    command = [
        f"{part.split('=', 1)[0]}={replacements[part.split('=', 1)[0]]}"
        if "=" in part and part.split("=", 1)[0] in replacements
        else part
        for part in baseline_command
    ]
    command += [
        f"mad_flags.threshold_bl={threshold_bl}",
        f"mad_flags.threshold_global={threshold_global}",
        f"mad_flags.whitening={whitening}",
        "mad_flags.max_deviation=0",
        "mad_flags.use_off_diagonals=false",
        # Disable solver-raised propagation to isolate MAD proposals.
        "solver.propagate_flags=false",
    ]
    with table(str(copy), readonly=True, ack=False, lockoptions="autonoread") as ms:
        before_flags, before_rows = ms.getcol("FLAG"), ms.getcol("FLAG_ROW")
    snapshot_flags(directory / "training-flags-before.npz", before_flags, before_rows)
    write_json(directory / "command.json", command)
    started = time.perf_counter()
    with (directory / "quartical.log").open("x") as log:
        completed = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    seconds = time.perf_counter() - started
    if completed.returncode:
        raise RuntimeError(f"native MAD failed; inspect {directory / 'quartical.log'}")
    audit = audit_ms(copy, state)
    with table(str(copy), readonly=True, ack=False, lockoptions="autonoread") as ms:
        flags, rows = ms.getcol("FLAG"), ms.getcol("FLAG_ROW")
    snapshot_flags(directory / "flags-after.npz", flags, rows)
    added = import_proposals(state, flags, rows)
    metadata = {
        "kind": "QuartiCal native residual MAD",
        "threshold_bl": float(threshold_bl),
        "threshold_global": float(threshold_global),
        "whitening": whitening,
        "use_off_diagonals": False,
        "solver_propagate_flags": False,
        "seconds": seconds,
        "includes_proposal_calibration": True,
        "audit": audit,
    }
    write_json(directory / "proposal.json", metadata)
    return name, added, metadata


def run(
    run_dir,
    archive=None,
    prepared_dir=None,
    seed=7,
    time_interval=2,
    freq_interval=32,
    iterations=50,
    max_fraction=0.02,
    mad_thresholds=(5.0, 8.0, 12.0),
    tricolour_thresholds=(10.0, 15.0, 20.0),
):
    """Run genuine flaggers, freeze proposals, compare fixed calibration settings."""
    run_dir = Path(run_dir).resolve()
    if bool(archive) == bool(prepared_dir):
        raise ValueError("supply exactly one of archive or prepared_dir")
    if not 0 <= max_fraction < 1 or min(time_interval, freq_interval, iterations) < 1:
        raise ValueError("invalid matched solve settings or flag budget")
    thresholds = [*mad_thresholds, *tricolour_thresholds]
    if not np.isfinite(thresholds).all() or any(value <= 0 for value in thresholds):
        raise ValueError("positive finite thresholds required")
    if archive:
        prepare(
            run_dir,
            archive=archive,
            seed=seed,
            time_interval=time_interval,
            freq_interval=freq_interval,
        )
    else:
        run_dir, prepared_dir = reject_nested_paths(run_dir, prepared_dir)
        run_dir.mkdir(parents=True, exist_ok=False)
        for name in ("state.npz", "manifest.json"):
            shutil.copy2(prepared_dir / name, run_dir / name)
        for name in ("original.ms", "work.ms"):
            shutil.copytree(prepared_dir / name, run_dir / name)
        if (prepared_dir / "injection.npz").exists():
            shutil.copy2(prepared_dir / "injection.npz", run_dir / "injection.npz")
    state, manifest = (
        load_state(run_dir),
        json.loads((run_dir / "manifest.json").read_text()),
    )
    # Actual immutable MS flags/weights and working data, not saved state alone,
    # define the authoritative preservation and visibility-split boundaries.
    boundary_audit = validate_prepared_state(run_dir, state, manifest)
    if manifest["split_gain_intervals"] != [time_interval, freq_interval]:
        raise ValueError("prepared split and calibration intervals must match")
    zero = np.zeros_like(state["train"])
    injected = None
    if (run_dir / "injection.npz").exists():
        with np.load(run_dir / "injection.npz", allow_pickle=False) as saved:
            injected = saved["injected"]
    config = {
        "time_interval": time_interval,
        "freq_interval": freq_interval,
        "iterations": iterations,
        "seed": manifest["seed"],
        "max_fraction": max_fraction,
        "mad_thresholds": list(mad_thresholds),
        "tricolour_thresholds": list(tricolour_thresholds),
        "proposal_scope": "eligible training only; four-correlation flag unions",
        "selection": "TV/TV0 + 2*added_fraction + 0.25*validation_MSE/MSEval0; max2% and max1% validation increase; test excluded",
        "sources": SOURCES,
        "prepared_dir": str(prepared_dir) if prepared_dir else None,
        "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "prepared_validation": boundary_audit,
        "prepared_helper_sha256": sha256(
            (Path(__file__).parent / "flagging_prepared.py").read_bytes()
        ).hexdigest(),
    }
    write_json(run_dir / "comparison-config.json", config)
    baseline, base_tv, residuals, guidance = solve(
        run_dir,
        state,
        manifest,
        zero,
        "baseline",
        time_interval,
        freq_interval,
        iterations,
    )
    if baseline["losses"]["validation"] is None:
        raise ValueError("baseline has unsupported validation predictions")
    base_tv_value = max(baseline["tv"], 1e-30)
    base_val = max(baseline["losses"]["validation"], 1e-30)
    baseline.update(
        fixed_support_tv=baseline["tv"],
        objective=baseline["tv"] / base_tv_value + 0.25,
        admissible=True,
    )
    entries = [{"method": "no-change", "metrics": baseline}]
    best, best_mask, best_method = baseline, zero, "no-change"
    proposals = []
    # All proposal generators see exactly the baseline training flags/data.
    set_flags(run_dir, state, zero, "native-mad-input")
    for threshold in mad_thresholds:
        proposals.append(
            mad_proposal(run_dir, state, threshold, 2 * threshold, "native")
        )
    proposals.append(mad_proposal(run_dir, state, 5.0, 10.0, "disabled"))
    windows, window_flags, row_map = pack_training_windows(state)
    tricolour_dir = run_dir / "flaggers/tricolour"
    tricolour_dir.mkdir(parents=True)
    np.savez_compressed(
        tricolour_dir / "input.npz", windows=windows, flags=window_flags
    )
    interpreter = os.environ.get("RANG_TRICOLOUR_PYTHON")
    if not interpreter:
        raise RuntimeError(
            "isolated Tricolour interpreter missing; use comparator image"
        )
    tricolour_settings = [
        (threshold, "holdout-safe") for threshold in tricolour_thresholds
    ]
    tricolour_settings.append((10.0, "package"))
    for threshold, morphology in tricolour_settings:
        name = f"tricolour-st-{morphology}-z{threshold:g}"
        output, metadata_path = (
            tricolour_dir / f"{name}.npz",
            tricolour_dir / f"{name}.json",
        )
        command = [
            interpreter,
            "-m",
            "rangtoy.flagging_comparators",
            "tricolour-worker",
            str(tricolour_dir / "input.npz"),
            str(output),
            str(metadata_path),
            str(threshold),
            "--morphology",
            morphology,
        ]
        write_json(tricolour_dir / f"{name}-command.json", command)
        with (tricolour_dir / f"{name}.log").open("x") as log:
            completed = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                env={
                    **os.environ,
                    "NUMBA_CACHE_DIR": os.environ.get(
                        "RANG_TRICOLOUR_CACHE", "/tmp/tricolour-cache"
                    ),
                },
            )
        if completed.returncode:
            raise RuntimeError(
                f"Tricolour failed; inspect {tricolour_dir / f'{name}.log'}"
            )
        with np.load(output, allow_pickle=False) as saved:
            added = unpack_proposals(saved["flags"], row_map, state["train"])
        proposals.append((name, added, json.loads(metadata_path.read_text())))
    outliers = residual_features(
        residuals * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    for weight in (0.0, 1.0, 3.0):
        for threshold in (8.0, 5.0, 3.0):
            name = f"tv-policy-w{weight:g}-z{threshold:g}"
            added = policy_mask(
                outliers,
                guidance,
                state["train"],
                threshold=threshold,
                tv_weight=weight,
                max_fraction=max_fraction,
            )
            proposals.append(
                (
                    name,
                    added,
                    {
                        "kind": "existing TV-guided policy",
                        "tv_weight": weight,
                        "threshold": threshold,
                    },
                )
            )
    seen = {sha256(zero.tobytes()).hexdigest(): baseline}
    for name, added, metadata in proposals:
        if np.any(added & ~state["train"]):
            raise RuntimeError("proposal modified holdouts or ineligible samples")
        proposal_dir = run_dir / "proposals"
        proposal_dir.mkdir(exist_ok=True)
        np.savez_compressed(proposal_dir / f"{name}.npz", added=added)
        fingerprint = sha256(added.tobytes()).hexdigest()
        if fingerprint in seen:
            metrics = dict(seen[fingerprint])
            duplicate = metrics["trial"]
        else:
            duplicate = None
            try:
                metrics, tv, _, _ = solve(
                    run_dir,
                    state,
                    manifest,
                    added,
                    name,
                    time_interval,
                    freq_interval,
                    iterations,
                    scale=baseline["scale"],
                )
                score = fixed_support_tv(tv["edges"], base_tv["edges"])
                val = metrics["losses"]["validation"]
                admissible = (
                    score is not None
                    and val is not None
                    and metrics["added_fraction"] <= max_fraction
                    and val <= 1.01 * base_val
                )
                objective = (
                    score / base_tv_value
                    + 2 * metrics["added_fraction"]
                    + 0.25 * val / base_val
                    if score is not None and val is not None
                    else None
                )
                metrics.update(
                    fixed_support_tv=score, objective=objective, admissible=admissible
                )
                seen[fingerprint] = metrics
            except (ValueError, RuntimeError) as error:
                entries.append(
                    {"method": name, "proposal": metadata, "failure": str(error)}
                )
                continue
        entry = {
            "method": name,
            "proposal": metadata,
            "metrics": metrics,
            "duplicate_of": duplicate,
        }
        if injected is not None:
            entry["injection_recovery"] = injection_recovery(
                added, injected, state["train"]
            )
        entries.append(entry)
        if metrics["admissible"] and metrics["objective"] < best["objective"]:
            best, best_mask, best_method = metrics, added, name
    set_flags(run_dir, state, best_mask, "selected-final", holdout=False)
    shutil.copytree(run_dir / "work.ms", run_dir / "selected.ms")
    audit = audit_ms(run_dir / "selected.ms", state)
    from casacore.tables import table

    with table(
        str(run_dir / "selected.ms"), readonly=True, ack=False, lockoptions="autonoread"
    ) as final:
        expected, expected_rows = protected_flags(
            state["original_flags"],
            state["original_rows"],
            np.broadcast_to(best_mask[..., None], state["original_flags"].shape),
        )
        audit["final_mask_exact"] = bool(
            np.array_equal(final.getcol("FLAG"), expected)
            and np.array_equal(final.getcol("FLAG_ROW"), expected_rows)
        )
    audit["original_copy_digest_preserved"] = (
        tree_digest(run_dir / "original.ms") == manifest["source_digest"]
    )
    audit["source_digest_preserved"] = (
        tree_digest(Path(manifest["source"])) == manifest["source_digest"]
    )
    if not all(audit.values()):
        raise RuntimeError("final comparator preservation audit failed")
    write_json(run_dir / "flag-audit.json", audit)
    result = {
        "configuration": config,
        "baseline": baseline,
        "selected": best,
        "selected_method": best_method,
        "trials": entries,
        "audit": audit,
        "limitations": "14 times, four antennas, approximate phase-centre scalar sky, input residual contamination unknown; Tricolour is focused SumThreshold subset, not full default strategy; timings include amd64 emulation and cache effects; no imaging or state-of-art novelty claim",
    }
    write_json(run_dir / "comparison.json", result)
    write_json(run_dir / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["tricolour-worker"])
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("metadata")
    parser.add_argument("threshold", type=float)
    parser.add_argument(
        "--morphology", choices=["holdout-safe", "package"], default="holdout-safe"
    )
    arguments = parser.parse_args()
    tricolour_worker(
        arguments.input,
        arguments.output,
        arguments.metadata,
        arguments.threshold,
        arguments.morphology,
    )
