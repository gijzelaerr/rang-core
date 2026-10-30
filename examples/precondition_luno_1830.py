"""Run the L2 precondition (research/luno-1830-campaign.md).

Usage: python examples/precondition_luno_1830.py outputs/l2-1830-<date>-00-precondition

1. K's precondition, unedited, against the K archive; 2. the L2 driver's
replay of K run -01 on MAIN_1 (image hashes exempt by P2, peak and residual
RMS within 1e-9 relative); 3. the four-station survey of MAIN_2 under the
stored model at identity against the archived support survey.
"""

import json
import sys
from pathlib import Path

from rangtoy import core_campaign_1830 as l2


def main():
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/") or out.exists():
        sys.exit("the precondition directory must be a fresh path beneath outputs/")
    result = l2.precondition(out)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "all_passed": result["all_passed"],
                "replay": {
                    k: v
                    for k, v in result["replay"].items()
                    if k not in ("candidates", "image_hashes_reported")
                },
                "survey": {
                    k: v
                    for k, v in result["survey"]["survey"].items()
                    if k != "failures"
                },
                "image_hashes_reported": result["replay"]["image_hashes_reported"],
                "seconds": result["seconds"],
                "max_rss_mb": result["max_rss_mb"],
            },
            indent=1,
        )
    )
    if not result["all_passed"]:
        sys.exit("precondition FAILED")


if __name__ == "__main__":
    main()
