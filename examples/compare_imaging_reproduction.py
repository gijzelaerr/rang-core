"""Compare the archived imaging result with a rerun of the frozen family.

Usage: compare_imaging_reproduction.py ARCHIVE.json RERUN/result.json [OUT.json]

ARCHIVE is ``research/results/gain-tv-next-imaging.json`` (its ``raw_result``
is compared) or any raw ``result.json``. Exit status 1 when any compared field
fails; the report is printed and optionally written.
"""

import json
import sys
from pathlib import Path

from rang.core_sensitivity import compare_reproduction


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    archived = json.loads(Path(argv[1]).read_text())
    archived = archived.get("raw_result", archived)
    rerun = json.loads(Path(argv[2]).read_text())
    rerun = rerun.get("raw_result", rerun)
    report = compare_reproduction(archived, rerun)
    report["archive"] = argv[1]
    report["rerun"] = argv[2]
    text = json.dumps(report, indent=2, sort_keys=True)
    if len(argv) == 4:
        Path(argv[3]).write_text(text + "\n")
    print(text)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
