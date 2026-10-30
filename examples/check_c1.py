"""Check the C1 run (research/c1-closure-arm.md).

Usage: python examples/check_c1.py outputs/c1-<date>-02-check \
           --run outputs/c1-<date>-01 \
           --precondition outputs/c1-<date>-00-precondition

Writes result.json with the criteria and Q1-Q3, and L1's own checker of the
run (`l1-check/`), into the fresh check directory.
"""

import argparse
import json

from rangtoy import core_campaign_closure as c1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("check_dir")
    parser.add_argument("--run", required=True)
    parser.add_argument("--precondition", required=True)
    parser.add_argument("--l1-run", default=str(c1.L1_RUN))
    args = parser.parse_args()
    out = c1.check(args.run, args.precondition, args.check_dir, args.l1_run)
    print(
        json.dumps(
            {
                "all_pass": out["all_pass"],
                "criteria": {k: v["pass"] for k, v in out["criteria"].items()},
                "questions": out["questions"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
