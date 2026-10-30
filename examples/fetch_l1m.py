"""Fetch CARACal's PKS 1934-638 field model at the pinned commit (L1-M).

Usage: python examples/fetch_l1m.py outputs/l1m-<date>-00-fieldmodel

The file is GPL-2.0 (CARACal) and is not committed to Rang; it is downloaded
into the outputs directory and accepted only if its SHA256 equals the pinned
value. Prints the record and the parsed summary.
"""

import argparse
import json

from rang import core_campaign_fieldmodel as l1m
from rang import lsm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    args = parser.parse_args()
    path, record = l1m.fetch_lsm(args.out_dir)
    print(
        json.dumps(
            {**record, "path": str(path), **lsm.summary(lsm.load(path))}, indent=1
        )
    )


if __name__ == "__main__":
    main()
