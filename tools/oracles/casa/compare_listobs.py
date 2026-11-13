# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare rang's listobs with CASA's on the V8a MSs (research/v8a-listobs.md).

Usage: compare_listobs.py CASA_DIR OUT.json NAME=MS [NAME=MS ...]

CASA_DIR is a `listobs.sh` run directory (NAME.json, NAME.msmd.json,
NAME.txt per MS). For each NAME=MS it runs `rang.listobs.summary(MS)`
(timed), compares with `rang.oracles.casa_listobs.compare` and writes one
verdict file: per MS the differences, the number of values compared and
rang's wall time. Exit 0 when no MS has a difference, 1 otherwise.
"""

import json
import sys
import time
from pathlib import Path

from rang import listobs
from rang.oracles import casa_listobs


def main(argv):
    casa_dir, out = Path(argv[0]), Path(argv[1])
    if out.exists():
        raise SystemExit(f"{out} exists; choose a fresh file")
    verdict = {"casa_dir": str(casa_dir), "runs": {}}
    for spec in argv[2:]:
        name, ms = spec.split("=", 1)
        start = time.perf_counter()
        record = listobs.summary(ms)
        wall = time.perf_counter() - start
        casa = json.loads((casa_dir / f"{name}.json").read_text(encoding="utf-8"))
        msmd = json.loads((casa_dir / f"{name}.msmd.json").read_text(encoding="utf-8"))
        text = (casa_dir / f"{name}.txt").read_text(encoding="utf-8", errors="replace")
        result = casa_listobs.compare(record, casa, msmd, text)
        result["rang_wall_s"] = round(wall, 3)
        result["ms"] = ms
        verdict["runs"][name] = result
        print(
            f"{name}: {len(result['differences'])} differences in "
            f"{result['compared']} values ({wall:.2f} s)"
        )
    verdict["passed"] = all(not r["differences"] for r in verdict["runs"].values())
    out.write_text(json.dumps(verdict, indent=1, default=str), encoding="utf-8")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
