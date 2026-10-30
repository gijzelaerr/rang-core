"""The L1 precondition (research/luno-array-campaign.md).

Usage: python examples/precondition_luno_array.py outputs/luno-array-campaign-<date>-00-precondition

1. Task K's precondition, unedited, and its archived numbers.
2. The L1 driver on K's four stations with K's image settings reproduces
   K's frozen run -01 exactly.
3. The channel-group gridder sum agrees with one call within 1e-4.
The array campaign may run only if all three pass.
"""

import json
import sys
from pathlib import Path

from rangtoy import core_campaign_array as array


def main():
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/") or out.exists():
        sys.exit("the precondition directory must be a fresh path beneath outputs/")
    result = array.precondition(out)
    print(
        json.dumps(
            {
                "all_passed": result["all_passed"],
                **result["passed"],
                "groups": result["groups"],
                "seconds": result["seconds"],
                "max_rss_mb": result["max_rss_mb"],
            },
            indent=1,
        )
    )
    if not result["all_passed"]:
        print(json.dumps(result["replay"], indent=1))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
