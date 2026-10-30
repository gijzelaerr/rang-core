"""Run L1's frozen campaign with the C1 closure arms (research/c1-closure-arm.md).

Usage: python examples/run_c1.py outputs/c1-<date>-01 \
           --precondition outputs/c1-<date>-00-precondition
       python examples/run_c1.py outputs/c1-<date>-00-smoke-4 --smoke --stations 0-3

The frozen run uses every station, needs a precondition directory and at
least 16 GiB of available memory; it exits with status 3 when the memory is
short, so that a wrapper can wait.
"""

import argparse
import json
import sys
from pathlib import Path

from rang import core_campaign_array as array
from rang import core_campaign_closure as c1
from rang import core_cli


def stations_arg(text):
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--precondition", default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--stations", type=stations_arg, default=None)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if not str(run_dir).startswith("outputs/c1-") or run_dir.exists():
        sys.exit("the run directory must be a fresh path beneath outputs/c1-")
    if not args.smoke:
        if args.stations is not None:
            sys.exit("the frozen run uses every station; --stations is for --smoke")
        if args.precondition is None:
            sys.exit("the frozen run needs --precondition")
        available = array.mem_available_gib()
        print(f"MemAvailable {available:.1f} GiB", flush=True)
        if available is not None and available < c1.MIN_AVAILABLE_GIB:
            print(f"less than {c1.MIN_AVAILABLE_GIB} GiB available; not started")
            sys.exit(3)
    result, record = c1.run(
        run_dir,
        stations=args.stations,
        precondition_dir=args.precondition,
        label="labelled smoke (not the campaign)" if args.smoke else "frozen",
    )
    core_cli.environment(run_dir)
    questions = c1.questions(record)
    print(
        json.dumps(
            {
                "wall_seconds": result["wall_seconds"],
                "process_seconds": record["process_seconds"],
                "max_rss_mb": max(result["max_rss_mb"], record["max_rss_mb"]),
                "gates": record["gates"],
                "kernel_gates": {
                    f: v["kernel_gate"] for f, v in record["families"].items()
                },
                "questions": questions,
                "cost": record["cost"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
