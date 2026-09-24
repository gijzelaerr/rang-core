"""Five research tracks, isolated Stimela scatter, then label-dependent fitting."""

import importlib
import json
import logging
import os
import shutil
from hashlib import sha256
from pathlib import Path

from .flagging_prepared import reject_nested_paths
from .flagging_workflow import tree_digest, write_json

SEEDS = (101, 103, 105)
PATTERNS = ("time-burst", "antenna-local")
CASES = tuple(f"{pattern}-seed{seed}" for seed in SEEDS for pattern in PATTERNS)
WORKSTREAMS = ("balanced-clean", *CASES, "uncertainty", "signal", "public")
SPLITS = {101: "train", 103: "validation", 105: "test"}
RESERVE_BYTES = 8 * 1024**3
SUITE_ALLOCATION_BYTES = 6 * 1024**3
LOGGER = logging.getLogger(__name__)


def _source_hashes():
    package = Path(__file__).parent
    return {
        name: sha256((package / f"{name}.py").read_bytes()).hexdigest()
        for name in (
            "flagging",
            "flagging_concurrent",
            "flagging_balanced",
            "flagging_structured_proposals",
            "flagging_prepared",
            "flagging_workflow",
            "flagging_uncertainty",
            "flagging_signal",
            "flagging_transfer",
            "flagging_public",
            "flagging_caracal",
            "flagging_comparators",
            "flagging_injections",
        )
    }


def initialize(run_dir, prepared_dir, acquired_dir, iterations=50):
    """Freeze inputs/budgets, then construct six fresh backed-up cases."""
    if type(iterations) is not int or iterations != 50:
        raise ValueError("frozen50 actual QuartiCal iterations required")
    root, prepared = reject_nested_paths(run_dir, prepared_dir)
    _, acquired = reject_nested_paths(root, acquired_dir)
    if root.exists() or Path(run_dir).is_symlink():
        raise ValueError("choose a fresh exclusive concurrent suite")
    for name in ("state.npz", "manifest.json", "original.ms", "work.ms"):
        if not (prepared / name).exists():
            raise ValueError(f"missing prepared input: {name}")
    if not (acquired / "acquisition-complete.json").is_file():
        raise ValueError("complete bounded public acquisition required")
    ancestor = root.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < RESERVE_BYTES + SUITE_ALLOCATION_BYTES:
        raise ValueError("concurrent suite would violate8GiB reserve/6GiB allocation")
    hashes = _source_hashes()
    config = {
        "prepared_dir": str(prepared),
        "prepared_input_digest": tree_digest(prepared),
        "acquired_dir": str(acquired),
        "acquisition_complete_sha256": sha256(
            (acquired / "acquisition-complete.json").read_bytes()
        ).hexdigest(),
        "iterations": iterations,
        "seeds": list(SEEDS),
        "patterns": list(PATTERNS),
        "workstreams": list(WORKSTREAMS),
        "scatter": 3,
        "allocation_bytes": SUITE_ALLOCATION_BYTES,
        "reserve_bytes": RESERVE_BYTES,
        "source_sha256": hashes,
        "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "model_dependency": "Actual balanced labels must finish before transfer fit",
        "independent_observation_transfer": False,
    }
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "concurrent-config.json", config)
    module = importlib.import_module("rangtoy.flagging_balanced")
    cases = []
    for seed in SEEDS:
        for pattern in PATTERNS:
            case_id = f"{pattern}-seed{seed}"
            module.make_case(
                str(root / "inputs" / case_id), str(prepared), pattern, seed=seed
            )
            cases.append(
                {
                    "case_id": case_id,
                    "seed": seed,
                    "split": SPLITS[seed],
                    "group_id": f"seed{seed}",
                    "run_dir": str(root / "experiments" / case_id),
                }
            )
    write_json(root / "transfer-cases.json", {"cases": cases})
    if tree_digest(prepared) != config["prepared_input_digest"]:
        raise RuntimeError("prepared source changed during initialization")
    print(f"Frozen concurrent suite and six fresh cases: {root}", flush=True)
    return config


def run_workstream(run_dir, workstream):
    """Each branch owns copies/cache/status; failures do not erase other tracks."""
    root = Path(run_dir).resolve()
    config = json.loads((root / "concurrent-config.json").read_text())
    if workstream not in WORKSTREAMS or workstream not in config["workstreams"]:
        raise ValueError("unknown/unconfigured concurrent workstream")
    if _source_hashes() != config["source_sha256"]:
        raise ValueError("implementation changed after suite freeze; choose a new run")
    output = root / "experiments" / workstream
    cache = Path(os.environ.get("NUMBA_CACHE_DIR", "/tmp/numba")) / workstream
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    try:
        if workstream == "public":
            module = importlib.import_module("rangtoy.flagging_public")
            result = module.inspect(str(output), config["acquired_dir"])
        elif workstream == "uncertainty":
            module = importlib.import_module("rangtoy.flagging_uncertainty")
            result = module.run(str(output))
        elif workstream == "signal":
            module = importlib.import_module("rangtoy.flagging_signal")
            result = module.run(
                str(output), config["prepared_dir"], iterations=config["iterations"]
            )
        else:
            module = importlib.import_module("rangtoy.flagging_balanced")
            prepared = (
                config["prepared_dir"]
                if workstream == "balanced-clean"
                else str(root / "inputs" / workstream)
            )
            result = module.run(str(output), prepared, iterations=config["iterations"])
        if not (output / "result.json").is_file():
            raise RuntimeError("branch returned without an actual result checkpoint")
        status = {"workstream": workstream, "complete": True, "output": str(output)}
        # Returning huge numerical archives through the cab is unnecessary;
        # actual files are authoritative and gathered only after scatter.
        del result
    except Exception as error:
        LOGGER.exception("Concurrent branch %s failed", workstream)
        status = {
            "workstream": workstream,
            "complete": False,
            "output": str(output),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print(f"{workstream} FAILED: {type(error).__name__}: {error}", flush=True)
    write_json(root / f"status-{workstream}.json", status)
    return status


def fit_transfer(run_dir):
    """Fit only after required labels exist; retain a diagnostic failure status."""
    root = Path(run_dir).resolve()
    if (
        _source_hashes()
        != json.loads((root / "concurrent-config.json").read_text())["source_sha256"]
    ):
        raise ValueError("implementation changed after freeze")
    output = root / "experiments" / "transfer"
    try:
        for case in CASES:
            status_path = root / f"status-{case}.json"
            if (
                not status_path.is_file()
                or not json.loads(status_path.read_text())["complete"]
            ):
                raise ValueError(f"actual counterfactual labels unavailable: {case}")
        module = importlib.import_module("rangtoy.flagging_transfer")
        module.run(str(output), str(root / "transfer-cases.json"))
        if not (output / "result.json").is_file():
            raise RuntimeError("transfer returned without a result checkpoint")
        status = {"workstream": "transfer", "complete": True, "output": str(output)}
    except Exception as error:
        LOGGER.exception("Grouped transfer diagnostic failed")
        status = {
            "workstream": "transfer",
            "complete": False,
            "output": str(output),
            "error_type": type(error).__name__,
            "error": str(error),
        }
    write_json(root / "status-transfer.json", status)
    return status


def gather(run_dir):
    root = Path(run_dir).resolve()
    config = json.loads((root / "concurrent-config.json").read_text())
    branches, failures = {}, []
    for mode in (*WORKSTREAMS, "transfer"):
        status_path = root / f"status-{mode}.json"
        status = (
            json.loads(status_path.read_text())
            if status_path.is_file()
            else {"workstream": mode, "complete": False, "error": "status missing"}
        )
        branch = {"status": status}
        path = root / "experiments" / mode / "result.json"
        if status["complete"] and path.is_file():
            branch["result"] = json.loads(path.read_text())
        else:
            failures.append(mode)
        branches[mode] = branch
    audit = {
        "prepared_source_unchanged": tree_digest(config["prepared_dir"])
        == config["prepared_input_digest"],
        "acquisition_manifest_unchanged": sha256(
            (Path(config["acquired_dir"]) / "acquisition-complete.json").read_bytes()
        ).hexdigest()
        == config["acquisition_complete_sha256"],
        "implementation_unchanged": _source_hashes() == config["source_sha256"],
    }
    result = {
        "configuration": config,
        "branches": branches,
        "audit": audit,
        "all_complete": not failures and all(audit.values()),
        "failures": failures,
        "limitations": "Parallel frozen diagnostic work; same-observation seed/scan controls are not independent-observation transfer, actual images, real gain uncertainty or SOTA superiority.",
    }
    write_json(root / "result.json", result)
    if failures or not all(audit.values()):
        raise RuntimeError(
            f"suite preserved checkpoints but failed: {failures}; audits={audit}"
        )
    return result
