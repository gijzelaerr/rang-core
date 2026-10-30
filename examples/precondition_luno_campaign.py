"""The task K comparator precondition (research/core-k-luno-campaign.md).

Usage: python examples/precondition_luno_campaign.py outputs/core-k-<date>-00-precondition

Runs the unedited section 6 pass on the archived local LUNO tiles and
compares it with QuartiCal's archived gains and flags, the section 6
archive and results/meerkat-luno-solved.json. The campaign may run only if
every check passes.
"""

import json
import sys
from pathlib import Path

from rang import core_campaign


def main():
    out = Path(sys.argv[1])
    if not str(out).startswith("outputs/") or out.exists():
        sys.exit("the precondition directory must be a fresh path beneath outputs/")
    result = core_campaign.precondition(out)
    print(
        json.dumps(
            {
                "all_passed": result["all_passed"],
                **result["passed"],
                "chi2": result["checks"]["chi2"],
                "seconds": result["seconds"],
                "max_rss_mb": result["max_rss_mb"],
            }
        )
    )
    if not result["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
