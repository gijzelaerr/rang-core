"""Build the compact task K archive (research/results/core-k-luno-campaign.json).

Usage: python examples/archive_luno_campaign.py OUT.json RUN PRECONDITION CHECK
           [--protocol-commit SHA] [--status TEXT] [--wall SECONDS --rss-mb MB]

Copies numbers, flag fractions, hashes, the candidate records and the
hypothesis calls from the run, precondition and check directories. No
visibilities, weights, UVW or images are copied; the run directory is not
modified.
"""

import argparse
import json
from hashlib import sha256
from pathlib import Path


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
    candidates = load(run / "candidates.json")
    pre = load(Path(args.precondition) / "result.json")
    checked = load(check / "result.json")
    archive = {
        "schema_version": 1,
        "task": "core-parallel-plan wave 2 task K: LUNO 1934-638 campaign on the core",
        "protocol": "research/core-k-luno-campaign.md",
        "protocol_commit": args.protocol_commit,
        "status": args.status,
        "provisional": result["provisional"],
        "licence": {
            "observer_permission": "Ben Hugo, WhatsApp 2026-10-29 15:36 SAST: 'you can use it. Just cite the Sarao data usage acknowledgement'",
            "sarao_written_confirmation": "pending",
            "visibilities_redistributed": False,
        },
        "cells": result["cells"],
        "settings": result["settings"],
        "split": result["split"],
        "fetch": {**result["fetch"], "extra": result["fetch_extra"]},
        "decode": result["decode"],
        "section6_reference": result["section6_reference"],
        "precondition": {
            "passed": pre["passed"],
            "all_passed": pre["all_passed"],
            "chi2": pre["checks"]["chi2"],
            "max_baseline_product_difference": pre["checks"][
                "max_baseline_product_difference"
            ],
            "seconds": pre["seconds"],
        },
        "tricolour": result["tricolour"],
        "arms": result["arms"],
        "candidates": candidates,
        "hypotheses": result["hypotheses"],
        "cost_clause": result["cost_clause"],
        "stages": result["stages"],
        "wall_seconds": result["wall_seconds"],
        "max_rss_mb": result["max_rss_mb"],
        "process_time": {"wall_seconds": args.wall, "max_rss_mb": args.rss_mb},
        "check": {
            "all_pass": checked["all_pass"],
            "criteria": {
                k: {kk: vv for kk, vv in v.items() if kk != "calls"}
                for k, v in checked["criteria"].items()
            },
        },
        "receipt": {
            k: receipt[k]
            for k in (
                "fetched_object_sha256",
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
    Path(args.out).write_text(json.dumps(archive, indent=1) + "\n")
    print(args.out, len(json.dumps(archive)), "bytes")


if __name__ == "__main__":
    main()
