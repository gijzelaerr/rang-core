"""Build the compact L2 archive (research/results/luno-1830-campaign.json).

Usage: python examples/archive_luno_1830.py OUT.json --stored RUN --scalar RUN \
           --precondition PRE --fetch FETCH --check CHECK \
           [--protocol-commit SHA] [--status TEXT]

Copies numbers, flag fractions, hashes, candidate records, survey counts and
the calls from the run, precondition, fetch and check directories. No
visibilities, weights, UVW, gains or images are copied; nothing under the
run directories is modified. Fails if the archive exceeds 200 KB.
"""

import argparse
import json
from hashlib import sha256
from pathlib import Path

LIMIT = 200_000


def load(path):
    return json.loads(Path(path).read_text())


def compact_arm(arm):
    if arm is None:
        return None
    out = {k: v for k, v in arm.items() if k != "image"}
    image = arm["image"]
    out["image"] = {
        k: v
        for k, v in image.items()
        if k not in ("gridder_groups", "imaging_weight_sums")
    }
    return out


def model_run(run):
    run = Path(run)
    result = load(run / "result.json")
    receipt = load(run / "receipt.json")
    environment = load(run / "environment.json")
    survey = load(run / "survey.json")
    return {
        "run_dir": str(run),
        "result_sha256": sha256((run / "result.json").read_bytes()).hexdigest(),
        "label": result["label"],
        "model": result["model"],
        "cells": result["cells"],
        "integrity": result["integrity"],
        "decode": result["decode"],
        "split": result["split"],
        "tricolour": result["tricolour"],
        "arms": {k: compact_arm(v) for k, v in result["arms"].items()},
        "unavailable": result["unavailable"],
        "boxes": result["boxes"],
        "amendment_1": result["amendment_1"],
        "hypotheses": result["hypotheses"],
        "survey": survey,
        "candidates": load(run / "candidates.json"),
        "cost_clause": result["cost_clause"],
        "stages": result["stages"],
        "wall_seconds": result["wall_seconds"],
        "cores_busy": result["cores_busy"],
        "max_rss_mb": result["max_rss_mb"],
        "memory": result["memory"],
        "receipt": {
            k: receipt[k]
            for k in (
                "code_sha256",
                "library_sha256",
                "backend",
                "strategies",
                "static_masks",
                "seed",
                "python",
                "numpy",
            )
        },
        "environment": {
            k: environment[k]
            for k in (
                "python",
                "rang_core_backend",
                "quartical_distribution_installed",
                "quartical_importable",
                "goquartical_on_path",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--stored", required=True)
    parser.add_argument("--scalar", required=True)
    parser.add_argument("--precondition", required=True)
    parser.add_argument("--fetch", required=True)
    parser.add_argument("--check", required=True)
    parser.add_argument("--protocol-commit", default=None)
    parser.add_argument("--status", default=None)
    args = parser.parse_args()
    stored = load(Path(args.stored) / "integrity.json")
    pre = load(Path(args.precondition) / "result.json")
    fetched = load(Path(args.fetch) / "result.json")
    checked = load(Path(args.check) / "result.json")
    archive = {
        "schema_version": 1,
        "task": "big-plan wave 3 task L2: LUNO PKS 1830-211 campaign on the core",
        "protocol": "research/luno-1830-campaign.md",
        "protocol_commit": args.protocol_commit,
        "status": args.status,
        "visibilities_redistributed": False,
        "fetch": fetched,
        "input_objects": [
            [r["key"], r["bytes"], r["sha256"], r["ok"]] for r in stored["objects"]
        ],
        "precondition": {
            k: pre[k]
            for k in (
                "passed",
                "all_passed",
                "k_precondition",
                "replay",
                "replay_stages",
                "stages",
                "seconds",
                "max_rss_mb",
            )
        }
        | {
            "survey": {
                "matches": pre["survey"]["matches"],
                "counts": {
                    k: v for k, v in pre["survey"]["survey"].items() if k != "failures"
                },
            }
        },
        "check": checked,
        "model_arms": {
            "stored": model_run(args.stored),
            "scalar": model_run(args.scalar),
        },
    }
    text = json.dumps(archive, indent=1) + "\n"
    if len(text.encode()) > LIMIT:
        text = json.dumps(archive, separators=(",", ":")) + "\n"
    if len(text.encode()) > LIMIT:
        raise SystemExit(f"archive is {len(text.encode())} bytes, over {LIMIT}")
    Path(args.out).write_text(text)
    print(f"{args.out}: {len(text.encode())} bytes")


if __name__ == "__main__":
    main()
