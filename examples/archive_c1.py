"""Build the compact C1 archive (research/results/c1-closure-arm.json).

Usage: python examples/archive_c1.py research/results/c1-closure-arm.json \
           outputs/c1-<date>-02-check

Numbers, calls and hashes only: no visibilities, weights, UVW, gains, maps or
images. Fails if the archive exceeds 250 KB.
"""

import argparse
import sys
from pathlib import Path

from rangtoy import core_campaign_closure as c1

LIMIT = 250_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("check_dir")
    args = parser.parse_args()
    c1.archive(args.check_dir, args.out)
    size = Path(args.out).stat().st_size
    print(f"{args.out}: {size} bytes")
    if size > LIMIT:
        sys.exit(f"archive is {size} bytes, over {LIMIT}")


if __name__ == "__main__":
    main()
