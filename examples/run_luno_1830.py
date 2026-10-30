"""Run the L2 campaign for one model arm (research/luno-1830-campaign.md).

Usage: python examples/run_luno_1830.py outputs/l2-1830-<date>-NN-<arm> \
           --model {stored,scalar} --fetch outputs/l2-1830-<date>-01-fetch \
           --precondition outputs/l2-1830-<date>-00-precondition
       python examples/run_luno_1830.py outputs/l2-1830-<date>-00-smoke-<arm> \
           --model ... --fetch ... --smoke --stations 0-11

Reads the fetched DATA and UVW and the archived FLAG, WEIGHT_SPECTRUM,
MODEL_DATA, row columns and subtables of MAIN/MAIN_2, runs the arms, images
and the survey under the model arm and writes the run directory. The frozen
run needs a passed precondition and 12 GiB of available memory; `--smoke`
labels a station-subset run that is not part of the campaign.
"""

import argparse
import json
import sys
from pathlib import Path

from rang import core_campaign_1830 as l2
from rang import core_cli


def stations_arg(text):
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--model", choices=l2.MODEL_ARMS, required=True)
    parser.add_argument("--fetch", required=True)
    parser.add_argument("--precondition", default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--gridder", choices=("wstack", "wgrid"), default="wstack")
    parser.add_argument("--stations", type=stations_arg, default=None)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if not str(run_dir).startswith("outputs/") or run_dir.exists():
        sys.exit("the run directory must be a fresh path beneath outputs/")
    available = l2.mem_available_gib()
    print(f"MemAvailable {available:.1f} GiB", flush=True)
    if not args.smoke:
        if args.stations is not None:
            sys.exit("the frozen run uses every station; --stations is for --smoke")
        if args.precondition is None:
            sys.exit("the frozen run needs --precondition")
        pre = json.loads((Path(args.precondition) / "result.json").read_text())
        if not pre["all_passed"]:
            sys.exit("the precondition failed; the campaign does not run")
        if available is not None and available < l2.MIN_AVAILABLE_GIB:
            sys.exit(f"less than {l2.MIN_AVAILABLE_GIB} GiB available; not started")
    result = l2.run(
        run_dir,
        args.model,
        fetch_dir=args.fetch,
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
                "model": result["model_arm"],
                "fit": {
                    k: v
                    for k, v in (result["model"].get("fit") or {}).items()
                    if k != "tiles"
                },
                "wall_seconds": result["wall_seconds"],
                "max_rss_mb": result["max_rss_mb"],
                "cells": result["cells"]["shape"],
                "split": result["split"]["counts"],
                "stages": {
                    k: [round(v["seconds"], 2), round(v["max_rss_mb"])]
                    for k, v in result["stages"].items()
                },
                "arms": {
                    k: {
                        "additions": v["additions"],
                        "converged": v["metrics"]["solver"]["converged_fraction"],
                        "mse_test": v["metrics"]["losses"]["test"],
                        "residual_rms": v["image"]["residual_rms"],
                        "peak": v["image"]["peak_jy_per_beam"],
                    }
                    for k, v in result["arms"].items()
                    if v is not None
                },
                "hypotheses": result["hypotheses"],
                "matched": [
                    [p["candidate"], p["reference"], p["mse_test"]]
                    for p in result["amendment_1"]["pairs"]
                ],
                "survey": result["survey"],
                "cost": result["cost_clause"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
