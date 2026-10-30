"""Check a task K campaign run against its protocol (research/core-k-luno-campaign.md).

Usage: python examples/check_luno_campaign.py outputs/core-k-<date>-NN \
           outputs/core-k-<date>-00-precondition outputs/core-k-check-<date>-NN

Criteria 1-7: fetch integrity against the archived tiles and objects, flag
preservation and side effects, the section 6 reference on the fetched
bytes, every arm's solve, the Tricolour arms' form, the pre-registered
hypothesis calls and the output set. Writes result.json into the fresh
check directory.
"""

import json
import sys
from pathlib import Path

from rangtoy import core_campaign


def main():
    run_dir, precondition_dir, check_dir = (Path(a) for a in sys.argv[1:4])
    if not str(check_dir).startswith("outputs/") or check_dir.exists():
        sys.exit("the check directory must be a fresh path beneath outputs/")
    summary = core_campaign.check(run_dir, precondition_dir, check_dir)
    for name, criterion in summary["criteria"].items():
        print(f"{name}: {'PASS' if criterion['pass'] else 'FAIL'}")
    print(json.dumps(summary["criteria"]["6_hypotheses"]["headline"], indent=1))
    print("all pass" if summary["all_pass"] else "FAILED")
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
