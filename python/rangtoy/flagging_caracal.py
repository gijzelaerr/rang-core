"""Run unmodified CARACAL Tricolour strategies on protected diagnostic copies.

Operational controls see all available DATA; their later held-out loss is not an
unseen-data metric. Holdout-masked controls deliberately introduce artificial
holes; polynomial resets mean even these are not guaranteed unseen-data tests.
Neither kind selects a deployed policy. This is not a full CARACAL pipeline.
"""

import json
import os
import shutil
import subprocess
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

from . import flagging_prepared
from .flagging import fixed_support_tv, protected_flags, snapshot_flags
from .flagging_workflow import load_state, set_flags, solve, tree_digest, write_json

CARACAL_REVISION = "8f7bb363876f5f0daecbf2167c36bb597c7e5160"
STRATEGY_HASHES = {
    "mk_rfi_flagging_calibrator_fields_firstpass.yaml": "ce9ac66aba75c62e778eabbc951e8f9760447f7824f8fd37b26b91974ec71774",
    "calibrator_mild_flagging.yaml": "835207c30eb4efdf2f65ae61c140699f7c2e01dbbca476c8434ae2776f5bde82",
    "calibrator_soft_flagging.yaml": "de63ee8ed452040cb58d6d18931daab935ae2de217e2cb1d8b4c3d7a2edd689c",
}
MODES = ("operational", "holdout_masked")


def validate_strategy_steps(steps):
    """Reject active resets and missing final original-flag union."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("nonempty strategy task list required")
    if any(step.get("task") == "unflag" for step in steps):
        raise ValueError("active unflag task is forbidden")
    if steps[-1].get("task") != "combine_with_input_flags":
        raise ValueError("strategy must end with combine_with_input_flags")


def strategy_provenance(path):
    path = Path(path).resolve()
    digest = sha256(path.read_bytes()).hexdigest()
    if STRATEGY_HASHES.get(path.name) != digest:
        raise ValueError("unrecognized or altered pinned CARACAL strategy")
    import yaml

    steps = yaml.safe_load(path.read_text())["strategies"]
    validate_strategy_steps(steps)
    return {"path": str(path), "sha256": digest, "tasks": [s["task"] for s in steps]}


def native_command(interpreter, measurement_set, strategy):
    """Mirror the inspected CARACAL flag-worker's polarisation-mode cab."""
    return [
        str(Path(interpreter).with_name("tricolour")),
        str(measurement_set),
        "--config",
        str(strategy),
        "--flagging-strategy",
        "polarisation",
        "--data-column",
        "DATA",
        "--window-backend",
        "numpy",
        "--nworkers",
        "1",
        "--disable-post-mortem",
    ]


def training_proposal(state, native_flags):
    """Couple correlations, importing additions only on eligible train samples."""
    native_flags = np.asarray(native_flags)
    if native_flags.dtype != np.bool_ or native_flags.shape != state["data"].shape:
        raise ValueError("native flags require the actual bool correlation shape")
    return state["train"] & native_flags.any(axis=-1)


def score_control(metrics, fixed_tv, baseline):
    """Diagnostic objective only; test losses never influence admissibility."""
    val, val0 = metrics["losses"]["validation"], baseline["losses"]["validation"]
    reasons = []
    if fixed_tv is None:
        reasons.append("fixed TV support lost")
    if metrics["added_fraction"] > 0.02:
        reasons.append("2% training flag budget exceeded")
    if val is None or val0 is None or val > 1.01 * val0:
        reasons.append("validation unavailable or exceeds 1% degradation")
    objective = (
        fixed_tv / max(baseline["tv"], 1e-30)
        + 2 * metrics["added_fraction"]
        + 0.25 * val / max(val0, 1e-30)
        if fixed_tv is not None and val is not None and val0 is not None
        else None
    )
    return {"objective": objective, "guard_reasons": reasons, "guard_pass": not reasons}


def _engine_provenance(interpreter, directory):
    script = """
import json
from hashlib import sha256
from pathlib import Path
import tricolour
from tricolour.mask import collect_masks
root = Path(tricolour.__file__).parent
print(json.dumps({
    'version': tricolour.__version__,
    'static_masks': [
        {'path': p, 'sha256': sha256(Path(p).read_bytes()).hexdigest()}
        for p in collect_masks()
    ],
    'sources': {name: sha256((root/name).read_bytes()).hexdigest() for name in
        ['apps/tricolour/app.py', 'apps/tricolour/strat_executor.py',
         'dask_wrappers.py', 'mask.py', 'stokes.py', 'flagging.py']},
}))
"""
    completed = subprocess.run(
        [str(interpreter), "-c", script],
        cwd=directory,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    result["requirements"] = subprocess.run(
        [str(interpreter), "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return result


def _native_run(run_dir, state, mode, strategy, interpreter, label):
    from casacore.tables import table

    directory = run_dir / "native" / label
    directory.mkdir(parents=True, exist_ok=False)
    ms = directory / "diagnostic.ms"
    shutil.copytree(run_dir / "work.ms", ms)
    original, rows = protected_flags(
        state["original_flags"],
        state["original_rows"],
        np.zeros_like(state["original_flags"]),
    )
    if mode == "holdout_masked":
        original |= ~state["train"][..., None]
        rows |= original.all(axis=(1, 2))
    with table(str(ms), readonly=False, ack=False) as copied:
        snapshot_flags(
            directory / "before-input-mask.npz",
            copied.getcol("FLAG"),
            copied.getcol("FLAG_ROW"),
        )
        copied.putcol("FLAG", original)
        copied.putcol("FLAG_ROW", rows)
        copied.flush()
    snapshot_flags(directory / "before-native.npz", original, rows)
    command = native_command(interpreter, ms, strategy)
    write_json(directory / "command.json", command)
    environment = dict(os.environ)
    environment["TRICOLOUR_LOGPATH"] = str(directory)
    environment["NUMBA_CACHE_DIR"] = environment.get(
        "RANG_TRICOLOUR_CACHE_DIR", "/tmp/caracal-tricolour"
    )
    started = time.perf_counter()
    with (directory / "native.log").open("x") as log:
        completed = subprocess.run(
            command,
            cwd=directory,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as copied:
        flags, final_rows = copied.getcol("FLAG"), copied.getcol("FLAG_ROW")
        data_match = bool(
            np.array_equal(copied.getcol("DATA"), state["data"], equal_nan=True)
        )
        weights = (
            copied.getcol("WEIGHT_SPECTRUM")
            if "WEIGHT_SPECTRUM" in copied.colnames()
            else np.broadcast_to(
                copied.getcol("WEIGHT")[:, None], state["weights"].shape
            )
        )
        weights_match = bool(np.array_equal(weights, state["weights"], equal_nan=True))
    snapshot_flags(directory / "after-native.npz", flags, final_rows)
    protected = not (
        np.any(state["original_flags"] & ~flags)
        or np.any(state["original_rows"] & ~final_rows)
    )
    if not protected:
        # Retain raw failure evidence, then recover original lower bounds on this
        # diagnostic copy. Do not calibrate or present it as a passing strategy.
        with table(str(ms), readonly=False, ack=False) as copied:
            repaired, repaired_rows = protected_flags(
                state["original_flags"], state["original_rows"], flags
            )
            copied.putcol("FLAG", repaired)
            copied.putcol("FLAG_ROW", repaired_rows)
            copied.flush()
        snapshot_flags(
            directory / "recovered-original-bounds.npz", repaired, repaired_rows
        )
    audit = {
        "original_flags_and_rows_preserved": bool(protected),
        "data_unchanged": data_match,
        "native_weights_unchanged": weights_match,
        "all_flagged_rows_without_flag_row": int(
            np.count_nonzero(flags.all(axis=(1, 2)) & ~final_rows)
        ),
    }
    result = {
        "label": label,
        "mode": mode,
        "returncode": completed.returncode,
        "seconds": elapsed,
        "audit": audit,
    }
    write_json(directory / "native-result.json", result)
    if not (data_match and weights_match and protected):
        raise RuntimeError(f"native preservation failure: {directory}")
    if completed.returncode:
        return result, None
    return result, training_proposal(state, flags)


def run(
    run_dir,
    prepared_dir,
    strategy_dir,
    strategies=(
        "mk_rfi_flagging_calibrator_fields_firstpass.yaml",
        "calibrator_mild_flagging.yaml",
    ),
    modes=MODES,
    iterations=50,
):
    """Verification-only native full-strategy controls and frozen gain re-solves."""
    run_dir, prepared_dir = flagging_prepared.reject_nested_paths(run_dir, prepared_dir)
    _, strategy_dir = flagging_prepared.reject_nested_paths(run_dir, strategy_dir)
    strategies, modes = list(strategies), list(modes)
    if (
        not strategies
        or len(set(strategies)) != len(strategies)
        or any(name not in STRATEGY_HASHES for name in strategies)
        or not modes
        or len(set(modes)) != len(modes)
        or any(mode not in MODES for mode in modes)
        or iterations < 1
    ):
        raise ValueError(
            "unique strategies/modes and positive iteration settings required"
        )
    provenance = {name: strategy_provenance(strategy_dir / name) for name in strategies}
    interpreter = Path(
        os.environ.get("RANG_TRICOLOUR_PYTHON", "/opt/tricolour/bin/python")
    )
    if not interpreter.is_file() or not interpreter.with_name("tricolour").is_file():
        raise ValueError("use the isolated pinned Tricolour environment")
    source_digest, strategies_digest = (
        tree_digest(prepared_dir),
        tree_digest(strategy_dir),
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    for name in ("state.npz", "manifest.json"):
        shutil.copy2(prepared_dir / name, run_dir / name)
    for name in ("original.ms", "work.ms"):
        shutil.copytree(prepared_dir / name, run_dir / name)
    state = load_state(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    boundary = flagging_prepared.validate_prepared_state(run_dir, state, manifest)
    engine = _engine_provenance(interpreter, run_dir)
    write_json(
        run_dir / "caracal-config.json",
        {
            "caracal_revision": CARACAL_REVISION,
            "strategies": provenance,
            "modes": modes,
            "iterations": iterations,
            "prepared_input": str(prepared_dir),
            "prepared_input_digest": source_digest,
            "prepared_boundary": boundary,
            "engine": engine,
            "boundary_module_sha256": sha256(
                Path(flagging_prepared.__file__).read_bytes()
            ).hexdigest(),
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "semantics": "Genuine full Tricolour CLI, CARACAL polarisation mode and unmodified pinned strategy; one selected field present. Not a full CARACAL pipeline.",
        },
    )
    zero = np.zeros_like(state["train"])
    ti, fi = manifest["split_gain_intervals"]
    baseline, base_tv, _, _ = solve(
        run_dir, state, manifest, zero, "baseline", ti, fi, iterations
    )
    if (
        fixed_support_tv(base_tv["edges"], base_tv["edges"]) is None
        or baseline["losses"]["validation"] is None
    ):
        raise ValueError(
            "baseline requires TV support and valid validation predictions"
        )
    records = []
    for index, name in enumerate(strategies):
        for mode in modes:
            label = f"strategy-{index:02d}-{mode}"
            native, proposal = _native_run(
                run_dir, state, mode, strategy_dir / name, interpreter, label
            )
            record = {
                "strategy": name,
                "native": native,
                "unseen_holdout_feature_evaluation": False,
                "artificial_holdout_input_flags": mode == "holdout_masked",
                "internal_starting_masks_may_reset": True,
                "selects_policy": False,
            }
            if proposal is not None:
                np.savez_compressed(
                    run_dir / "native" / label / "frozen-proposal.npz", added=proposal
                )
                try:
                    metrics, tv, _, _ = solve(
                        run_dir,
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
                    record["calibration_error"] = str(error)
            records.append(record)
            write_json(run_dir / f"checkpoint-{label}.json", record)
    set_flags(run_dir, state, zero, "final-original", holdout=False)
    final_boundary = flagging_prepared.validate_prepared_state(run_dir, state, manifest)
    audit = {
        "prepared_source_unchanged": tree_digest(prepared_dir) == source_digest,
        "strategy_inputs_unchanged": tree_digest(strategy_dir) == strategies_digest,
        "original_source_unchanged": tree_digest(manifest["source"])
        == manifest["source_digest"],
        "main_work_boundary_validated": final_boundary["validated"],
        "no_deployed_policy_selected": True,
    }
    if not all(audit.values()):
        raise RuntimeError("verification source preservation failed")
    write_json(
        run_dir / "result.json",
        {
            "baseline": baseline,
            "controls": records,
            "audit": audit,
            "limitations": "Verification-only full Tricolour strategies on a four-antenna pointing scan. Operational features see all available DATA. Artificial holdout input flags may be discarded by internal polynomial mask resets. Neither control is claimed as unseen-holdout policy evaluation. Original FLAG/FLAG_ROW always remain lower bounds on actual QuartiCal calibration. No policy/imaging/transfer/SOTA advantage claimed; timing is amd64 emulation.",
        },
    )
