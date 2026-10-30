"""Run one L1-M model arm under L1's frozen campaign (research/l1-model-completeness.md).

Usage: python examples/run_l1m.py outputs/l1m-<date>-01-stored --model stored \
           --precondition outputs/l1m-<date>-00-precondition
       python examples/run_l1m.py outputs/l1m-<date>-03-field --model field \
           --lsm outputs/l1m-<date>-00-fieldmodel/pks1934-638.lsm \
           --precondition outputs/l1m-<date>-00-precondition \
           --compare stored=outputs/l1m-<date>-01-stored \
           --compare point=outputs/l1m-<date>-02-point
       python examples/run_l1m.py outputs/l1m-<date>-00-smoke-field --model field \
           --lsm ... --smoke --stations 0-3

The stored arm needs no lsm. `--compare MODEL=DIR` names earlier runs whose
gains enter the matched cross-model losses. The frozen run needs a
precondition directory and at least 14 GiB of available memory; it exits
with status 3 when the memory is short, so that a wrapper can wait.
"""

import argparse
import json
import sys
from pathlib import Path

from rangtoy import core_campaign_array as array
from rangtoy import core_campaign_fieldmodel as l1m
from rangtoy import core_cli


def stations_arg(text):
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def compare_arg(text):
    model, _, path = text.partition("=")
    if model not in l1m.MODEL_ARMS or not path:
        raise argparse.ArgumentTypeError("--compare MODEL=DIR")
    return model, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--model", required=True, choices=l1m.MODEL_ARMS)
    parser.add_argument("--lsm", default=None)
    parser.add_argument("--precondition", default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--stations", type=stations_arg, default=None)
    parser.add_argument("--compare", type=compare_arg, action="append", default=[])
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    if not str(run_dir).startswith("outputs/l1m-") or run_dir.exists():
        sys.exit("the run directory must be a fresh path beneath outputs/l1m-")
    if args.model != "stored" and args.lsm is None:
        sys.exit("a predicted model arm needs --lsm")
    if not args.smoke:
        if args.stations is not None:
            sys.exit("the frozen run uses every station; --stations is for --smoke")
        if args.precondition is None:
            sys.exit("the frozen run needs --precondition")
        available = array.mem_available_gib()
        print(f"MemAvailable {available:.1f} GiB", flush=True)
        if available is not None and available < l1m.MIN_AVAILABLE_GIB:
            print(f"less than {l1m.MIN_AVAILABLE_GIB} GiB available; not started")
            sys.exit(3)
    result, record = l1m.run(
        run_dir,
        args.model,
        lsm_path=args.lsm,
        stations=args.stations,
        precondition_dir=args.precondition,
        label="labelled smoke (not the campaign)" if args.smoke else "frozen",
        others=dict(args.compare) or None,
    )
    core_cli.environment(run_dir)
    print(
        json.dumps(
            {
                "model": args.model,
                "wall_seconds": result["wall_seconds"],
                "max_rss_mb": result["max_rss_mb"],
                "split_sha256": record["model"]["split_sha256"],
                "checks": record["model"].get("checks"),
                "predict_seconds": record["model"].get("predict_seconds"),
                "arms": {
                    k: {
                        "additions": v["additions"],
                        "losses": v["metrics"]["losses"],
                        "converged": v["metrics"]["solver"]["converged_fraction"],
                        "tv": v["metrics"]["tv"],
                    }
                    for k, v in result["arms"].items()
                    if v is not None
                },
                "hypotheses": result["hypotheses"],
                "matched": record["matched_model_losses"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
