"""Run the task K campaign as frozen (research/core-k-luno-campaign.md).

Usage: python examples/run_luno_campaign.py outputs/core-k-<date>-NN
           [--precondition outputs/core-k-<date>-00-precondition] [--workers 8]

Fetches the LUNO four-station slice from the RATT bucket with range
requests, decodes it with the core, runs the arms and the images, and
writes result.json, receipt.json, candidates.json, environment.json and
side-effects.json into the fresh run directory. Nothing under the archived
inputs is written. Check the run afterwards with
examples/check_luno_campaign.py.
"""

import argparse
import json
import sys
from pathlib import Path

from rang import core_campaign, core_cli


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--precondition", default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--bucket", default=core_campaign.BUCKET, help="store root URL (tests only)"
    )
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if not str(run_dir).startswith("outputs/") or run_dir.exists():
        sys.exit("the run directory must be a fresh path beneath outputs/")
    if args.precondition is not None:
        pre = json.loads((Path(args.precondition) / "result.json").read_text())
        if not pre["all_passed"]:
            sys.exit("the comparator precondition failed; the campaign does not run")
    result = core_campaign.run(
        run_dir,
        bucket=args.bucket,
        workers=args.workers,
        precondition_dir=args.precondition,
    )
    core_cli.environment(run_dir)
    headline = result["hypotheses"][0]
    print(
        json.dumps(
            {
                "wall_seconds": result["wall_seconds"],
                "max_rss_mb": result["max_rss_mb"],
                "fetch_seconds": result["fetch"]["seconds"],
                "fetch_bytes": result["fetch"]["bytes"],
                "arms": {
                    k: {
                        "additions": v["additions"],
                        "mse_test": v["metrics"]["losses"]["test"],
                        "residual_rms": v["image"]["residual_rms"],
                    }
                    for k, v in result["arms"].items()
                    if v is not None
                },
                "headline": headline,
                "cost": result["cost_clause"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
