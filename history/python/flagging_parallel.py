"""Independent flagging diagnostics dispatched by Stimela2's native scatter.

Each worker owns its Measurement Sets, checkpoints and compilation cache. The
suite collects failures only after all branches finish, so one failing experiment
does not erase or silently prevent the other diagnostic results.
"""

import importlib
import json
import logging
import os
import platform
from hashlib import sha256
from pathlib import Path

import numpy as np

from .flagging_workflow import FIXTURE_SHA256, write_json

WORKSTREAMS = ("injections", "sky", "comparators", "actions")
SKY_SHA256 = "b277bc6d4095bb22798cc70547d9563a56460eb6e450474854b93117534b1fb9"
LOGGER = logging.getLogger(__name__)


def initialize(
    run_dir,
    archive,
    sky_model=None,
    workstreams=WORKSTREAMS,
    iterations=50,
    action_count=16,
    strengths=(3.0, 10.0),
):
    """Validate inputs before exclusively creating a suite output directory."""
    workstreams = list(workstreams)
    if (
        not workstreams
        or len(set(workstreams)) != len(workstreams)
        or any(mode not in WORKSTREAMS for mode in workstreams)
    ):
        raise ValueError("choose unique known workstreams")
    if (
        iterations < 1
        or action_count < 6
        or not strengths
        or not (np.isfinite(strengths).all() and min(strengths) > 0)
    ):
        raise ValueError(
            "positive solve/injection settings and at least six actions required"
        )
    archive = Path(archive).resolve()
    if sha256(archive.read_bytes()).hexdigest() != FIXTURE_SHA256:
        raise ValueError("unexpected public MeerKAT fixture checksum")
    if "sky" in workstreams:
        if sky_model is None:
            raise ValueError("sky branch requires the pinned SARAO L-band model")
        sky_model = Path(sky_model).resolve()
        if sha256(sky_model.read_bytes()).hexdigest() != SKY_SHA256:
            raise ValueError("unexpected SARAO L-band model checksum")
        predictor = Path(
            os.environ.get("RANG_SKY_PREDICTOR", "/opt/sky/bin/crystalball")
        )
        if not predictor.is_file():
            raise ValueError(
                "isolated Crystalball predictor missing; use the suite image"
            )
    if "comparators" in workstreams:
        tricolour = Path(
            os.environ.get("RANG_TRICOLOUR_PYTHON", "/opt/tricolour/bin/python")
        )
        if not tricolour.is_file():
            raise ValueError(
                "isolated Tricolour interpreter missing; use the suite image"
            )
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        run_dir / "parallel-config.json",
        {
            "workstreams": workstreams,
            "archive": str(archive),
            "archive_sha256": FIXTURE_SHA256,
            "sky_model": str(sky_model) if sky_model is not None else None,
            "sky_sha256": SKY_SHA256 if "sky" in workstreams else None,
            "iterations": iterations,
            "action_count": action_count,
            "strengths": list(strengths),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "module_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "suite_image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
            "scientific_dependency": "The learned-policy assessment depends on injection/oracle controls, despite parallel implementation.",
            "preservation": "Only branch-specific copied MS are writable; all input flags remain immutable lower bounds.",
        },
    )


def run_workstream(run_dir, workstream):
    root = Path(run_dir).resolve()
    config = json.loads((root / "parallel-config.json").read_text())
    if workstream not in config["workstreams"] or workstream not in WORKSTREAMS:
        raise ValueError("workstream not authorized by initialized suite")
    output = root / workstream
    cache = Path(os.environ.get("NUMBA_CACHE_DIR", "/tmp/numba")) / workstream
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    arguments = {
        "run_dir": str(output),
        "archive": config["archive"],
        "iterations": config["iterations"],
    }
    callable_name = "run"
    if workstream == "sky":
        callable_name = "compare"
        arguments["sky_model"] = config["sky_model"]
    elif workstream == "injections":
        arguments["strengths"] = config["strengths"]
    elif workstream == "actions":
        arguments["action_count"] = config["action_count"]
    try:
        module = importlib.import_module(f"rangtoy.flagging_{workstream}")
        getattr(module, callable_name)(**arguments)
        if not (output / "result.json").is_file():
            raise RuntimeError("branch returned without its result.json checkpoint")
        status = {"workstream": workstream, "complete": True, "output": str(output)}
    except Exception as error:
        LOGGER.exception("Flagging workstream %s failed", workstream)
        status = {
            "workstream": workstream,
            "complete": False,
            "output": str(output),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print(f"{workstream} FAILED: {type(error).__name__}: {error}", flush=True)
    write_json(root / f"{workstream}-status.json", status)


def gather(run_dir):
    """Archive all statuses before reporting a failed or incomplete branch."""
    root = Path(run_dir).resolve()
    config = json.loads((root / "parallel-config.json").read_text())
    branches = {}
    failures = []
    for mode in config["workstreams"]:
        status_path = root / f"{mode}-status.json"
        status = (
            json.loads(status_path.read_text())
            if status_path.is_file()
            else {
                "workstream": mode,
                "complete": False,
                "error": "worker status missing",
            }
        )
        branch = {"status": status}
        result_path = root / mode / "result.json"
        if status["complete"] and result_path.is_file():
            branch["result"] = json.loads(result_path.read_text())
        else:
            failures.append(mode)
        branches[mode] = branch
    write_json(
        root / "result.json",
        {
            "configuration": config,
            "branches": branches,
            "all_complete": not failures,
            "failures": failures,
            "limitations": "Parallel diagnostic pilots are not an independent-scan or imaging benchmark and do not by themselves establish novelty.",
        },
    )
    if failures:
        raise RuntimeError(
            f"suite retained checkpoints but branches failed: {', '.join(failures)}"
        )
