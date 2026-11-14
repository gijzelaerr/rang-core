# SPDX-License-Identifier: GPL-3.0-or-later
"""Archive CASA's flags on V8b's synthetic fixed-mode cases for CI
(research/v8b-flagdata.md): per case the SHA-256 of `np.packbits` of FLAG
(row, chan, corr order) and of FLAG_ROW, and CASA's summary returns, so that
`tests/test_v8b_flagdata.py` checks rang against CASA without CASA.

Usage: archive_flagdata.py CASA_DIR OUT.json
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

CASES = ("syn-edges", "syn-edges-uvwneg", "syn-edges-nom001")


def main(argv):
    casa, out = Path(argv[0]), Path(argv[1])
    entries = {}
    for npz in sorted(casa.glob("*.npz")):
        name = npz.stem
        case, arm = name.split(".", 1)
        if case not in CASES or not arm.startswith("M"):
            continue
        z = np.load(npz)
        log = json.loads((casa / f"{name}.json").read_text(encoding="utf-8"))
        if any(c["error"] for c in log["calls"]):
            continue  # a refused selection: nothing to hash
        entry = {
            "gate": "exact",
            "sha256": [
                hashlib.sha256(z["flag"].tobytes()).hexdigest(),
                hashlib.sha256(
                    np.packbits(z["flag_row"].astype(bool)).tobytes()
                ).hexdigest(),
            ],
        }
        summaries = {
            str(k): c["return"]
            for k, c in enumerate(log["calls"])
            if c["params"].get("mode") == "summary"
        }
        if summaries:
            entry["summaries"] = summaries
        entries[name] = entry
    meta = json.loads((casa / "plan.json").read_text(encoding="utf-8"))
    record = {
        "oracle": "CASA 6.7.6.14 flagdata, image rang-o-casa:6.7.6.14",
        "image": (casa / "image.txt").read_text(encoding="utf-8").strip(),
        "run": casa.name,
        "plan_cases": len(meta),
        "cases": entries,
    }
    out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(len(entries), "cases archived")


if __name__ == "__main__":
    main(sys.argv[1:])
