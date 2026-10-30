"""Run the L1 whole-array campaign as frozen (research/luno-array-campaign.md).

Usage: python examples/run_luno_array.py outputs/luno-array-campaign-<date>-NN \
           --precondition outputs/luno-array-campaign-<date>-00-precondition
       python examples/run_luno_array.py outputs/luno-array-campaign-<date>-00-smoke \
           --smoke --stations 0-11

Reads the archived whole tiles of LUNO row chunk 0 (nothing is fetched),
runs the arms and the images and writes result.json, receipt.json,
candidates.json, integrity.json, environment.json and side-effects.json into
the fresh run directory. The frozen run requires a passed precondition and
at least 20 GiB of available memory; `--smoke` labels a run on a station
subset that is not part of the campaign.
"""

import argparse
import json
import sys
from pathlib import Path

from rang import core_campaign_array as array
from rang import core_cli


def stations_arg(text):
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--precondition", default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--gridder", choices=("wstack", "wgrid"), default="wstack")
    parser.add_argument("--stations", type=stations_arg, default=None)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if not str(run_dir).startswith("outputs/") or run_dir.exists():
        sys.exit("the run directory must be a fresh path beneath outputs/")
    if not args.smoke:
        if args.stations is not None:
            sys.exit("the frozen run uses every station; --stations is for --smoke")
        if args.precondition is None:
            sys.exit("the frozen run needs --precondition")
        pre = json.loads((Path(args.precondition) / "result.json").read_text())
        if not pre["all_passed"]:
            sys.exit("the precondition failed; the campaign does not run")
        available = array.mem_available_gib()
        print(f"MemAvailable {available:.1f} GiB", flush=True)
        if available is not None and available < array.MIN_AVAILABLE_GIB:
            sys.exit(f"less than {array.MIN_AVAILABLE_GIB} GiB available; not started")
    result = array.run(
        run_dir,
        stations=args.stations,
        precondition_dir=args.precondition,
        label="labelled smoke (not the campaign)" if args.smoke else "frozen",
        gridder=args.gridder,
    )
    core_cli.environment(run_dir)
    print(
        json.dumps(
            {
                "label": result["label"],
                "wall_seconds": result["wall_seconds"],
                "max_rss_mb": result["max_rss_mb"],
                "cells": result["cells"]["shape"],
                "stages": {
                    k: [round(v["seconds"], 2), round(v["max_rss_mb"])]
                    for k, v in result["stages"].items()
                },
                "arms": {
                    k: {
                        "additions": v["additions"],
                        "mse_test": v["metrics"]["losses"]["test"],
                        "residual_rms": v["image"]["residual_rms"],
                        "peak": v["image"]["peak_jy_per_beam"],
                    }
                    for k, v in result["arms"].items()
                    if v is not None
                },
                "hypotheses": result["hypotheses"],
                "cost": result["cost_clause"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
