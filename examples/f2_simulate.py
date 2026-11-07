"""F2 Stage 1: build F-SIM observations (research/f2-flagger.md, section 4).

Usage: python examples/f2_simulate.py OUT_ROOT NAME [NAME ...] [--variant line|step]

OUT_ROOT `RUN` means $RUN_DIR. Each observation goes to OUT_ROOT/NAME (OUT_ROOT/NAME-VARIANT with a variant).
"""

import argparse
import json
import os
import time
from pathlib import Path

from rang import f2flag_sim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("names", nargs="+", choices=sorted(f2flag_sim.OBSERVATIONS))
    parser.add_argument("--variant", choices=("line", "step"))
    args = parser.parse_args()
    if str(args.root) == "RUN":  # the run wrapper's directory
        args.root = Path(os.environ["RUN_DIR"])
    for name in args.names:
        started = time.perf_counter()
        label = f"{name}-{args.variant}" if args.variant else name
        summary = f2flag_sim.build(name, args.root / label, variant=args.variant)
        print(
            json.dumps(
                {
                    "observation": label,
                    "seconds": time.perf_counter() - started,
                    "scans": len(summary["scans"]),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
