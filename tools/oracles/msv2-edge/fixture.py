# SPDX-License-Identifier: GPL-3.0-or-later
"""Copy three cases of the MSv2 edge-case set into `tests/data/msv2-edge`
with arcae's cells as `oracle.json` (research/msv2-edge-cases.md, R1 to R3).

The cases (t05 TiledCellStMan, t06 IncrementalStMan scalars, a string and
an indirect array, t07 an IncrementalStMan string array next to
StandardStMan ones) were written by python-casacore 3.8.1 and read by
arcae 0.5.9 with `research/results/msv2-edge-cases/edge_cases.py` (`make`,
then `dump-arcae`). This script needs only NumPy and the dumps:

    python tools/oracles/msv2-edge/fixture.py D:/rang/outputs/msv2-edge-cases/20261113

Booleans are kept as arcae returns them (uint8 0 and 1).
"""

import json
import pickle
import shutil
import sys
from pathlib import Path

import numpy as np

CASES = ["t05-tcellsm", "t06-ism", "t07-strings"]
OUT = Path(__file__).resolve().parents[3] / "tests" / "data" / "msv2-edge"


def cell(value):
    a = np.asarray(value)
    if a.dtype == object or a.dtype.kind in "US":
        return {"dtype": "str", "shape": list(a.shape), "values": a.ravel().tolist()}
    return {"dtype": str(a.dtype), "shape": list(a.shape), "values": a.ravel().tolist()}


def main(root):
    root = Path(root)
    with open(root / "dumps" / "arcae.pkl", "rb") as f:
        dump = pickle.load(f)
    oracle = {"versions": dump["versions"], "tables": {}}
    for case in CASES:
        entry = dump["data"][(case, "")]
        shutil.copytree(root / "tables" / case, OUT / case, dirs_exist_ok=True)
        oracle["tables"][case] = {
            "nrows": entry["nrows"],
            "columns": {
                name: [None if c is None else cell(c) for c in col["cells"]]
                for name, col in entry["columns"].items()
            },
        }
    (OUT / "oracle.json").write_text(
        json.dumps(oracle, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{OUT}: {', '.join(CASES)}")


if __name__ == "__main__":
    main(sys.argv[1])
