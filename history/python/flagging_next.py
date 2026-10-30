"""Offline five-track Stimela2 campaign with independent branch outputs."""

import importlib
import json
import os
from hashlib import sha256
from pathlib import Path

from .flagging_prepared import reject_nested_paths
from .flagging_prospective import CampaignBudget, prepare_inputs
from .flagging_workflow import tree_digest
from .projector import _native_library

TRACKS = ("trend", "prospective", "signal", "provenance", "imaging")


def source_receipts():
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "python/rangtoy").glob("*.py"))
    paths += list((root / "src").glob("*.rs"))
    paths += list((root / "recipes").glob("tv-flagging*.yaml"))
    paths += [
        p
        for p in (root / "tools/flagging").rglob("*")
        if p.is_file()
        and (p.suffix in (".py", ".sh", ".txt") or p.name == "Dockerfile")
    ]
    paths += [root / name for name in ("Cargo.toml", "Cargo.lock", "pyproject.toml")]
    paths.append(Path(_native_library()._name).resolve())
    return {str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def initialize(
    run_dir, prepared_dir, historical_dir, response_dir, provenance_dir, caracal_dir
):
    """Freeze all local inputs, then create fresh clean/107/109 cases."""
    output, prepared = reject_nested_paths(run_dir, prepared_dir)
    sources = {
        "historical_dir": historical_dir,
        "response_dir": response_dir,
        "provenance_dir": provenance_dir,
        "caracal_dir": caracal_dir,
    }
    resolved = {}
    for name, path in sources.items():
        _, source = reject_nested_paths(output, path)
        if not source.is_dir():
            raise ValueError(f"missing stable source: {name}")
        resolved[name] = {"path": str(source), "digest": tree_digest(source)}
    resolved["prepared_dir"] = {"path": str(prepared), "digest": tree_digest(prepared)}
    budget = CampaignBudget(output, 8 * 1024**3)
    budget.check(7 * 1024**3)
    budget.mkdir(output)
    config = {
        "sources": resolved,
        "runtime_receipts": source_receipts(),
        "tracks": TRACKS,
        "scatter_workers": 3,
        "maximum_concurrent_QC_workers": 2,
        "maximum_concurrent_imagers": 1,
        "image": os.environ.get("RANG_FLAGGING_SUITE_IMAGE"),
        "runtime_network": "none",
        "independent_observation_transfer": False,
        "new_inputs": "clean + time-burst107/109",
        "allocated_campaign_limit_bytes": budget.limit,
        "logical_provenance_limit_bytes": 8 * 1024**2,
    }
    budget.json(output / "config.json", config)
    budget.mkdir(output / "experiments")
    prepare_inputs(output / "inputs", prepared)
    budget.json(
        output / "initialized.json",
        {
            "configuration": config,
            "source_receipts_unchanged": source_receipts()
            == config["runtime_receipts"],
        },
    )
    if source_receipts() != config["runtime_receipts"]:
        raise RuntimeError("campaign implementation changed during initialization")
    return config


def run_track(run_dir, track):
    """One writable branch; provenance is offline, network stages are separate."""
    root = Path(run_dir).resolve()
    config = json.loads((root / "config.json").read_text())
    if track not in TRACKS or source_receipts() != config["runtime_receipts"]:
        raise ValueError("unknown track or changed campaign implementation")
    if not all(
        tree_digest(x["path"]) == x["digest"] for x in config["sources"].values()
    ):
        raise ValueError("campaign source changed before branch launch")
    output = root / "experiments" / track
    if output.exists() or output.is_symlink():
        raise ValueError("track requires a fresh exclusive output")
    cache = Path(os.environ.get("NUMBA_CACHE_DIR", "/tmp/numba")) / track
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    modules = {
        "trend": "flagging_trend",
        "prospective": "flagging_prospective",
        "signal": "flagging_signal_guard",
        "provenance": "flagging_provenance",
        "imaging": "flagging_imaging",
    }
    module = importlib.import_module(f"rangtoy.{modules[track]}")
    sources = config["sources"]
    if track == "trend":
        result = module.run(output, sources["historical_dir"]["path"])
    elif track == "prospective":
        result = module.run(output, root / "inputs")
    elif track == "signal":
        result = module.run(
            output, [root / "inputs/cases" / f"time-burst-seed{s}" for s in (107, 109)]
        )
    elif track == "provenance":
        result = module.run(output, sources["provenance_dir"]["path"])
    else:
        result = module.run(
            output, sources["response_dir"]["path"], sources["caracal_dir"]["path"]
        )
    CampaignBudget(root, config["allocated_campaign_limit_bytes"]).check()
    return result


def gather(run_dir):
    root = Path(run_dir).resolve()
    config = json.loads((root / "config.json").read_text())
    records = {
        track: json.loads((root / "experiments" / track / "result.json").read_text())
        for track in TRACKS
    }
    audit = {
        "runtime_unchanged": source_receipts() == config["runtime_receipts"],
        "all_sources_unchanged": all(
            tree_digest(x["path"]) == x["digest"] for x in config["sources"].values()
        ),
    }
    if not all(audit.values()):
        raise RuntimeError("five-track immutable boundary failure")
    budget = CampaignBudget(root, config["allocated_campaign_limit_bytes"])
    result = {
        "configuration": config,
        "tracks": records,
        "audit": audit,
        "allocated_bytes": budget.check(),
        "status": "executed bounded five-track prototype, not a validated science flagger or SOTA result",
    }
    budget.json(root / "result.json", result)
    return result
