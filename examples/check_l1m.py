"""Check the three L1-M runs and compare the models (research/l1-model-completeness.md).

Usage: python examples/check_l1m.py outputs/l1m-<date>-04-check \
           --precondition outputs/l1m-<date>-00-precondition \
           --lsm outputs/l1m-<date>-00-fieldmodel/pks1934-638.lsm \
           --run stored=outputs/l1m-<date>-01-stored \
           --run point=outputs/l1m-<date>-02-point \
           --run field=outputs/l1m-<date>-03-field

Writes result.json with the criteria, Q1-Q3 and L1's own checker per run
(`l1-check-<model>/`) into the fresh check directory.
"""

import argparse
import json

from rang import core_campaign_fieldmodel as l1m


def run_arg(text):
    model, _, path = text.partition("=")
    if model not in l1m.MODEL_ARMS or not path:
        raise argparse.ArgumentTypeError("--run MODEL=DIR")
    return model, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("check_dir")
    parser.add_argument("--precondition", required=True)
    parser.add_argument("--lsm", required=True)
    parser.add_argument("--run", type=run_arg, action="append", required=True)
    parser.add_argument("--l1-run", default=str(l1m.L1_RUN))
    args = parser.parse_args()
    runs = dict(args.run)
    if set(runs) != set(l1m.MODEL_ARMS):
        parser.error(f"one --run per model arm: {l1m.MODEL_ARMS}")
    out = l1m.check(runs, args.precondition, args.check_dir, args.lsm, args.l1_run)
    print(
        json.dumps(
            {
                "all_pass": out["all_pass"],
                "criteria": {k: v["pass"] for k, v in out["criteria"].items()},
                "q1": out["comparison"]["q1"],
                "q2": out["comparison"]["q2"],
                "q3": out["comparison"]["q3"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
