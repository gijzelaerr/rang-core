"""Check the L2 runs against the frozen criteria (research/luno-1830-campaign.md).

Usage: python examples/check_luno_1830.py CHECK_DIR --stored RUN --scalar RUN \
           --precondition PRE --fetch FETCH
"""

import argparse
import json
import sys
from pathlib import Path

from rangtoy import core_campaign_1830 as l2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("check_dir")
    parser.add_argument("--stored", required=True)
    parser.add_argument("--scalar", required=True)
    parser.add_argument("--precondition", required=True)
    parser.add_argument("--fetch", required=True)
    args = parser.parse_args()
    check_dir = Path(args.check_dir)
    if not str(check_dir).startswith("outputs/") or check_dir.exists():
        sys.exit("the check directory must be a fresh path beneath outputs/")
    summary = l2.check(
        {"stored": args.stored, "scalar": args.scalar},
        args.precondition,
        args.fetch,
        check_dir,
    )
    print(
        json.dumps(
            {
                "all_pass": summary["all_pass"],
                "per_model_arm": {
                    arm: {k: v["pass"] for k, v in crit.items()}
                    for arm, crit in summary["per_model_arm"].items()
                },
                "across_model_arms": {
                    k: v["pass"] for k, v in summary["across_model_arms"].items()
                },
                "verdict": summary["verdict"],
                "headlines": summary["headlines"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
