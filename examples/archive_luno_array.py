"""Build the compact L1 archive (research/results/luno-array-campaign.json).

Usage: python examples/archive_luno_array.py OUT.json RUN PRECONDITION CHECK
           [--protocol-commit SHA] [--status TEXT] [--wall SECONDS --rss-mb MB]

Copies numbers, flag fractions, hashes, the candidate records and the
hypothesis calls from the run, precondition and check directories. No
visibilities, weights, UVW, gains or images are copied; nothing under the
run directory is modified. Fails if the archive exceeds 200 KB.
"""

import argparse
import json
from hashlib import sha256
from pathlib import Path

LIMIT = 200_000


def load(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("run")
    parser.add_argument("precondition")
    parser.add_argument("check")
    parser.add_argument("--protocol-commit", default=None)
    parser.add_argument("--status", default=None)
    parser.add_argument("--wall", type=float, default=None)
    parser.add_argument("--rss-mb", type=float, default=None)
    args = parser.parse_args()
    run, check = Path(args.run), Path(args.check)
    result = load(run / "result.json")
    receipt = load(run / "receipt.json")
    environment = load(run / "environment.json")
    integrity = load(run / "integrity.json")
    pre = load(Path(args.precondition) / "result.json")
    checked = load(check / "result.json")
    archive = {
        "schema_version": 1,
        "task": "big-plan wave 1 task L1: whole-array LUNO 1934-638 campaign on the core",
        "protocol": "research/luno-array-campaign.md",
        "protocol_commit": args.protocol_commit,
        "status": args.status,
        "caveats": result["caveats"],
        "visibilities_redistributed": False,
        "cells": result["cells"],
        "settings": result["settings"],
        "integrity": {
            **result["integrity"],
            "objects": [
                [r["key"], r["bytes"], r["sha256"], r["ok"]]
                for r in integrity["objects"]
            ],
        },
        "decode": result["decode"],
        "split": result["split"],
        "tricolour": result["tricolour"],
        "arms": result["arms"],
        "boxes": result["boxes"],
        "candidates": load(run / "candidates.json"),
        "hypotheses": result["hypotheses"],
        "cost_clause": result["cost_clause"],
        "stages": result["stages"],
        "wall_seconds": result["wall_seconds"],
        "cores_busy": result["cores_busy"],
        "max_rss_mb": result["max_rss_mb"],
        "memory": result["memory"],
        "process_time": {"wall_seconds": args.wall, "max_rss_mb": args.rss_mb},
        "precondition": {
            "passed": pre["passed"],
            "all_passed": pre["all_passed"],
            "k_precondition": pre["k_precondition"],
            "replay": pre["replay"],
            "groups": pre["groups"],
            "stages": pre["stages"],
            "replay_stages": pre["replay_stages"],
            "seconds": pre["seconds"],
            "max_rss_mb": pre["max_rss_mb"],
        },
        "check": {
            "all_pass": checked["all_pass"],
            "criteria": {
                k: {"pass": v["pass"]}
                | {
                    key: val
                    for key, val in v.items()
                    if key
                    in (
                        "bytes_hashed",
                        "objects",
                        "converged",
                        "headline",
                        "input_files_checked",
                    )
                }
                for k, v in checked["criteria"].items()
            },
        },
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
        "run_dir": str(run),
        "check_dir": str(check),
        "result_sha256": sha256((run / "result.json").read_bytes()).hexdigest(),
    }
    text = json.dumps(archive, indent=1) + "\n"
    if len(text.encode()) > LIMIT:
        raise SystemExit(f"archive is {len(text.encode())} bytes, over {LIMIT}")
    Path(args.out).write_text(text)
    print(f"{args.out}: {len(text.encode())} bytes")


if __name__ == "__main__":
    main()
