"""Build the compact L1-M archive (research/results/l1-model-completeness.json).

Usage: python examples/archive_l1m.py research/results/l1-model-completeness.json \
           outputs/l1m-<date>-04-check

Numbers, calls and hashes only: no visibilities, weights, UVW, gains or
images. Fails if the archive exceeds 200 KB.
"""

import argparse
import sys
from pathlib import Path

from rangtoy import core_campaign_fieldmodel as l1m

LIMIT = 200_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("check_dir")
    args = parser.parse_args()
    l1m.archive(args.check_dir, args.out)
    size = Path(args.out).stat().st_size
    print(f"{args.out}: {size} bytes")
    if size > LIMIT:
        sys.exit(f"archive is {size} bytes, over {LIMIT}")


if __name__ == "__main__":
    main()
