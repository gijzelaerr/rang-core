"""What python-casacore does with W1's tiled dminfo requests (reference for
research/casacure-evaluation.md, criterion W1; post hoc, reported).

Run in `rang-ms-reader:local`:
    python /examples/eval_casacure_tiled_reference.py <out-dir>

Creates `default_ms` twice with python-casacore: (b) DATA, FLAG and
WEIGHT_SPECTRUM in TiledColumnStMan with FLAG left as the required
variable-shape column, (c) the same with FLAG redeclared fixed-shape in the
table description. Records whether creation succeeds, the resulting FLAG
description and data managers.
"""

import json
import sys
from pathlib import Path

import numpy as np
from casacore.tables import default_ms, makearrcoldesc, maketabdesc

TILED = {"DATA": [4, 4096, 8], "FLAG": [4, 4096, 64], "WEIGHT_SPECTRUM": [4, 4096, 16]}
VALUE = {"WEIGHT_SPECTRUM": (0.0, "float"), "FLAG": (False, "boolean")}


def make(path, fixed_flag):
    names = ("DATA", "MODEL_DATA", "WEIGHT_SPECTRUM") + (
        ("FLAG",) if fixed_flag else ()
    )
    desc = maketabdesc(
        [
            makearrcoldesc(
                n,
                VALUE.get(n, (0j, "complex"))[0],
                ndim=2,
                shape=[4096, 4],
                valuetype=VALUE.get(n, (0j, "complex"))[1],
                datamanagertype="TiledColumnStMan" if n in TILED else "",
                datamanagergroup=f"Tiled{n}" if n in TILED else "",
            )
            for n in names
        ]
    )
    dminfo = {
        f"*{i + 1}": {
            "TYPE": "TiledColumnStMan",
            "NAME": f"Tiled{n}",
            "SPEC": {"DEFAULTTILESHAPE": s},
            "COLUMNS": [n],
        }
        for i, (n, s) in enumerate(TILED.items())
    }
    try:
        t = default_ms(str(path), desc, dminfo)
        t.addrows(3)
        t.putcol("FLAG", np.zeros((3, 4096, 4), bool))
        entry = {
            "created": True,
            "flag_desc": {
                k: v for k, v in t.getcoldesc("FLAG").items() if k != "keywords"
            },
            "managers": {
                v["NAME"]: [v["TYPE"], list(v["COLUMNS"])]
                for v in t.getdminfo().values()
            },
        }
        t.close()
    except Exception as error:  # noqa: BLE001 - this is the measurement
        entry = {"created": False, "error": f"{type(error).__name__}: {error}"}
    return entry


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=False)
    result = {
        "b-tiled": make(out / "ref-b.ms", False),
        "c-tiled-fixed-flag": make(out / "ref-c.ms", True),
    }
    (out / "tiled-reference.json").write_text(
        json.dumps(result, indent=1, default=str) + "\n"
    )
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
