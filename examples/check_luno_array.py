"""Check an L1 run against its protocol (research/luno-array-campaign.md).

Usage: python examples/check_luno_array.py outputs/luno-array-campaign-<date>-NN \
           outputs/luno-array-campaign-<date>-00-precondition \
           outputs/luno-array-campaign-check-<date>-NN

Criteria 1-7: local input integrity (re-hashed), flag preservation and side
effects, the precondition, every arm's solve, the Tricolour arms' form, the
pre-registered hypothesis calls and the output set.
"""

import json
import sys
from pathlib import Path

from rang import core_campaign_array as array


def main():
    run_dir, precondition_dir, check_dir = (Path(a) for a in sys.argv[1:4])
    if not str(check_dir).startswith("outputs/") or check_dir.exists():
        sys.exit("the check directory must be a fresh path beneath outputs/")
    summary = array.check(run_dir, precondition_dir, check_dir)
    for name, criterion in summary["criteria"].items():
        print(f"{name}: {'PASS' if criterion['pass'] else 'FAIL'}")
    print(json.dumps(summary["criteria"]["6_hypotheses"]["headline"], indent=1))
    print("all pass" if summary["all_pass"] else "FAILED")
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
