"""Fetch the PKS 1830-211 DATA and UVW objects (research/luno-1830-campaign.md).

Usage: python examples/fetch_luno_1830.py outputs/l2-1830-<date>-NN-fetch

Whole GETs of the 19 frozen objects (16 DATA tiles of MAIN/MAIN_2 row chunk
0, UVW and the two .zarray) from the anonymous RATT bucket, with a receipt
per object; everything else the campaign reads is archived on disk.
"""

import json
import sys
from pathlib import Path

from rangtoy import core_campaign_1830 as l2


def main():
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/") or out.exists():
        sys.exit("the fetch directory must be a fresh path beneath outputs/")
    result = l2.fetch(out)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "objects"},
            indent=1,
        )
    )
    if not (
        result["keys_complete"]
        and result["all_status_200"]
        and result["sizes_match_probe"]
        and result["hashes_match_files"]
    ):
        sys.exit("the fetch does not match the frozen object list")


if __name__ == "__main__":
    main()
