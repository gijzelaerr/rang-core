"""Read-only grid-matched phase controls for full-Jones TV specificity.

No new calibration, Measurement Set, flag write or truth decoding. Replays actual
saved counterfactual gains, preserving original action sets and native weights.
"""

import json
import os
import platform
import shutil
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging import (
    fixed_support_tv,
    gain_tv,
    polar_gauge,
    require_meerkat_lband,
    residual_features,
)
from .flagging_balanced import balanced_rank
from .flagging_caracal import score_control
from .flagging_prepared import reject_nested_paths
from .flagging_structured import choose_action
from .flagging_structured_proposals import generate_candidates
from .flagging_workflow import load_state, write_json
from .projector import _native_library

REFERENCE_HZ = 1283791015.625
PATTERNS = {
    "identity": ([0, 0, 0, 0], [0, 0, 0, 0]),
    "smooth-frequency": ([0, 3, 6, 9], [0, 0, 0, 0]),
    "smooth-time": ([0, 0, 0, 0], [0, 0.2, -0.2, 0.4]),
    "both": ([0, 3, 6, 9], [0, 0.2, -0.2, 0.4]),
}
CASES = (
    "balanced-clean",
    "time-burst-seed101",
    "antenna-local-seed101",
    "time-burst-seed103",
    "antenna-local-seed103",
    "time-burst-seed105",
    "antenna-local-seed105",
)
RESERVE_BYTES = 8 * 1024**3
ALLOCATION_BYTES = 256 * 1024**2
FROZEN_MODULES = (
    "flagging.py",
    "flagging_balanced.py",
    "flagging_caracal.py",
    "flagging_equivariance.py",
    "flagging_prepared.py",
    "flagging_structured.py",
    "flagging_structured_proposals.py",
    "flagging_workflow.py",
    "projector.py",
)


def checkpoint(output, filename, value):
    """Checked derived-output allocation, not an OS-enforced quota."""
    payload = json.dumps(value, allow_nan=False)
    allocated = sum(p.stat().st_blocks * 512 for p in output.rglob("*"))
    reservation = len(payload.encode()) * 2 + 65536
    if allocated + reservation > ALLOCATION_BYTES:
        raise ValueError("equivariance256MiB checked output budget exceeded")
    if shutil.disk_usage(output).free < RESERVE_BYTES + reservation:
        raise ValueError("equivariance8GiB disk reserve would be violated")
    if (output / filename).exists():
        raise ValueError("checkpoint target must be fresh")
    write_json(output / filename, value)


def phase_factors(times, frequencies, pattern):
    """Frozen scalar station phase, smooth on the existing solved grid."""
    if pattern not in PATTERNS:
        raise ValueError("unknown frozen phase control")
    times, frequencies = np.asarray(times, float), np.asarray(frequencies, float)
    for coordinates in (times, frequencies):
        if (
            coordinates.ndim != 1
            or not coordinates.size
            or not np.isfinite(coordinates).all()
            or np.any(np.diff(coordinates) <= 0)
        ):
            raise ValueError("finite increasing nonempty gain coordinates required")
    delay, drift = (np.asarray(x, float) for x in PATTERNS[pattern])
    span = float(np.ptp(times))
    normalized_time = (times - times[0]) / span if span else np.zeros_like(times)
    phase = (
        2 * np.pi * (frequencies[None, :, None] - REFERENCE_HZ) * delay * 1e-9
        + normalized_time[:, None, None] * drift
    )
    if not np.isfinite(phase).all():
        raise ValueError("phase coordinate overflow")
    return np.exp(1j * phase)


def gain_prediction(state, gains, intervals=(2, 32)):
    """Bounded full-matrix reference calculation on the fixture's native cells."""
    ti, fi = intervals
    inverse = np.unique(state["times"], return_inverse=True)[1]
    tmap, fmap = inverse // ti, np.arange(state["data"].shape[1]) // fi
    if gains.shape != (tmap.max() + 1, fmap.max() + 1, 4, 2, 2):
        raise ValueError("gain grid differs from frozen native maps")
    gp = gains[tmap[:, None], fmap[None], state["antenna1"][:, None]]
    gq = gains[tmap[:, None], fmap[None], state["antenna2"][:, None]]
    model = state["model"].reshape(*state["data"].shape[:2], 2, 2)
    return (gp @ model @ gq.conj().swapaxes(-1, -2)).reshape(state["data"].shape)


def cell_phases(state, factors, intervals=(2, 32)):
    ti, fi = intervals
    tmap = np.unique(state["times"], return_inverse=True)[1] // ti
    fmap = np.arange(state["data"].shape[1]) // fi
    dp = factors[tmap[:, None], fmap[None], state["antenna1"][:, None]]
    dq = factors[tmap[:, None], fmap[None], state["antenna2"][:, None]]
    return dp * dq.conj()


def phase_replay(state, gains, valid, times, frequencies, scale, pattern):
    """Full-Jones norms plus exact observed/predicted residual invariance audit."""
    factors = phase_factors(times, frequencies, pattern)
    rotated = gains * factors[..., None, None]
    aligned, tv_valid = polar_gauge(rotated, valid)
    tv = gain_tv(aligned, tv_valid, times, frequencies, scale=scale)
    raw = gain_tv(rotated, valid, times, frequencies, scale=scale)
    prediction = gain_prediction(state, gains)
    rotated_prediction = gain_prediction(state, rotated)
    phases = cell_phases(state, factors)
    residual = state["data"] - prediction
    rotated_residual = state["data"] * phases[..., None] - rotated_prediction
    eligible = state["train"] | state["validation"] | state["test"]
    old_mse = np.mean(np.abs(residual) ** 2 * state["weights"], axis=-1)
    new_mse = np.mean(np.abs(rotated_residual) ** 2 * state["weights"], axis=-1)
    if not np.isfinite(new_mse[eligible]).all():
        raise ValueError("phase replay lost originally eligible prediction support")
    error = float(np.max(np.abs(new_mse[eligible] - old_mse[eligible])))
    prediction_error = float(
        np.max(
            np.abs(
                rotated_prediction[eligible]
                - prediction[eligible] * phases[eligible, None]
            )
        )
    )
    if not np.allclose(new_mse[eligible], old_mse[eligible], rtol=1e-11, atol=1e-10):
        raise ValueError("weighted residual phase invariance failed")
    return (
        {
            "tv": tv["total"],
            "raw_tv": raw["total"],
            "time_tv": tv["time"],
            "frequency_tv": tv["frequency"],
            "scale": scale,
            "losses": {
                k: float(np.mean(new_mse[state[k]]))
                for k in ("train", "validation", "test")
            },
            "maximum_cell_weighted_MSE_invariance_error": error,
            "maximum_visibility_prediction_equivariance_error_jy": prediction_error,
        },
        tv,
        residual,
    )


def _digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _source_receipts(source):
    files = [source / "concurrent-config.json", source / "result.json"]
    for name in CASES:
        directory = source / "experiments" / name
        files.extend(
            directory / f
            for f in (
                "state.npz",
                "manifest.json",
                "result.json",
                "balanced-config.json",
                "frozen-rankings.json",
            )
        )
        files.extend(sorted(directory.glob("trials/*/diagnostics.npz")))
    return {str(p.relative_to(source)): _digest(p) for p in files}


def run(run_dir, source_dir):
    """All four frozen controls; original labels are retrospective development."""
    output, source = reject_nested_paths(run_dir, source_dir)
    if output.exists() or Path(run_dir).is_symlink():
        raise ValueError("choose a fresh exclusive equivariance output")
    if not json.loads((source / "result.json").read_text())["all_complete"]:
        raise ValueError("completed source suite required")
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < RESERVE_BYTES + ALLOCATION_BYTES:
        raise ValueError("keep8GiB reserve plus256MiB bounded derived output")
    receipts = _source_receipts(source)
    native_path = Path(_native_library()._name)
    module_dir = Path(__file__).parent
    module_hashes = {name: _digest(module_dir / name) for name in FROZEN_MODULES}
    config = {
        "patterns": PATTERNS,
        "reference_frequency_hz": REFERENCE_HZ,
        "source_dir": str(source),
        "source_sha256": receipts,
        "module_sha256": _digest(__file__),
        "implementation_sha256": module_hashes,
        "native_library_sha256": _digest(native_path),
        "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "old_counterfactual_action_sets_fixed": True,
        "grid_matched_not_continuous_hardware_simulation": True,
        "no_MS_flags_DATA_or_native_weight_writes": True,
        "numeric_DATA_model_weights_decoded": True,
        "injection_truth_not_decoded_or_used": True,
        "execution_environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "new_QC_solves": 0,
    }
    output.mkdir(parents=True, exist_ok=False)
    checkpoint(output, "config.json", config)
    cases = []
    for name in CASES:
        directory = source / "experiments" / name
        state = load_state(directory)
        manifest = json.loads((directory / "manifest.json").read_text())
        require_meerkat_lband(manifest["scope"]["telescope"], state["frequencies"])
        if state["data"].shape != (140, 4096, 4) or manifest[
            "split_gain_intervals"
        ] != [2, 32]:
            raise ValueError("frozen four-antenna fixture shape/grid required")
        model = state["model"]
        if not (
            np.array_equal(model[..., 0], model[..., 3])
            and np.all(model[..., 1:3] == 0)
        ):
            raise ValueError("polar-gauge replay requires scalar-unpolarized model")
        measured = json.loads((directory / "result.json").read_text())
        base = measured["baseline"]["metrics"]
        patterns = {}
        for pattern in PATTERNS:
            with np.load(
                directory / "trials/baseline/diagnostics.npz", allow_pickle=False
            ) as saved:
                baseline, baseline_tv, residuals = phase_replay(
                    state,
                    saved["gains"],
                    saved["gain_valid"],
                    saved["gain_times"],
                    saved["gain_frequencies"],
                    base["scale"],
                    pattern,
                )
            baseline.update(added_count=0, added_fraction=0.0)
            z = residual_features(
                residuals * np.sqrt(state["weights"]),
                state["train"],
                state["antenna1"],
                state["antenna2"],
            )
            tmap = np.unique(state["times"], return_inverse=True)[1] // 2
            fmap = np.arange(4096) // 32
            maps = baseline_tv["map"]
            guidance = np.maximum(
                maps[tmap[:, None], fmap[None], state["antenna1"][:, None]],
                maps[tmap[:, None], fmap[None], state["antenna2"][:, None]],
            )
            family = generate_candidates(state, z, guidance)
            reranked = {
                mode: [c["mask_id"] for c in balanced_rank(family, mode)]
                for mode in ("residual", "tv", "random")
            }
            del family
            actions = []
            for action in measured["actions"]:
                original = action["metrics"]
                with np.load(
                    directory / "trials" / original["trial"] / "diagnostics.npz",
                    allow_pickle=False,
                ) as saved:
                    metrics, tv, _ = phase_replay(
                        state,
                        saved["gains"],
                        saved["gain_valid"],
                        saved["gain_times"],
                        saved["gain_frequencies"],
                        base["scale"],
                        pattern,
                    )
                metrics.update(
                    added_count=original["added_count"],
                    added_fraction=original["added_fraction"],
                )
                fixed_tv = fixed_support_tv(tv["edges"], baseline_tv["edges"])
                record = {
                    "mask_id": action["mask_id"],
                    "metrics": metrics,
                    "fixed_support_tv": fixed_tv,
                    **score_control(metrics, fixed_tv, baseline),
                }
                if pattern == "identity" and not np.isclose(
                    record["objective"], action["objective"], rtol=0, atol=1e-12
                ):
                    raise ValueError(
                        "identity action does not reproduce measured objective"
                    )
                actions.append(record)
            ranking_ids = {
                mode: [
                    a["mask_id"] for a in measured["candidate_family"]["rankings"][mode]
                ]
                for mode in reranked
            }
            selected = {
                mode: choose_action(actions, ids, 1.25)
                for mode, ids in ranking_ids.items()
            }
            old_selected = {
                mode: item["mask_id"] for mode, item in measured["selected"].items()
            }
            if pattern == "identity" and (
                selected != old_selected or reranked != ranking_ids
            ):
                raise ValueError(
                    "identity selection/ranking failed exact archive replay"
                )
            available = {a["mask_id"] for a in actions}
            patterns[pattern] = {
                "baseline": baseline,
                "actions": actions,
                "selected_on_old_fixed_sets": selected,
                "original_selected": old_selected,
                "recomputed_TRAIN_rankings": reranked,
                "unknown_reranked_action_ids": {
                    mode: [i for i in ids if i not in available]
                    for mode, ids in reranked.items()
                },
                "reranked_actions_not_selected": True,
            }
            checkpoint(output, f"checkpoint-{name}-{pattern}.json", patterns[pattern])
        cases.append({"case_id": name, "patterns": patterns})
    audit = {
        "all_read_source_receipts_unchanged": _source_receipts(source) == receipts,
        "native_library_unchanged": _digest(native_path)
        == config["native_library_sha256"],
        "module_unchanged": _digest(__file__) == config["module_sha256"],
        "all_implementation_modules_unchanged": all(
            _digest(module_dir / name) == digest
            for name, digest in module_hashes.items()
        ),
        "no_truth_decoded_or_used": True,
        "new_QC_solves": 0,
        "no_MS_or_flag_write": True,
        "TEST_invariance_only_never_selects": True,
    }
    if not all(
        audit[k]
        for k in (
            "all_read_source_receipts_unchanged",
            "native_library_unchanged",
            "module_unchanged",
            "all_implementation_modules_unchanged",
        )
    ):
        raise RuntimeError("source or implementation changed during read-only replay")
    result = {
        "configuration": config,
        "cases": cases,
        "audit": audit,
        "limits": "Retrospective grid-matched smoothphase controls on one four-antenna observation; no deployment, unknown reranked outcomes, continuous hardware/noise uncertainty, independent transfer, imaging or SOTA advantage.",
    }
    checkpoint(output, "result.json", result)
    return str(output / "result.json")
