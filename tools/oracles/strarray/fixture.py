# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the string-array fixture table and its python-casacore oracle.

Run with a python that has python-casacore (in WSL on the owner's host):

    python tools/oracles/strarray/fixture.py tests/data/strarray

It writes `<out>/table` (a casacore table, a few kB) and `<out>/oracle.json`
(every cell as python-casacore's `getcell` returns it: shape in numpy order
and the values in C order). research/feed-poltype-read.md has the reasons.

The StandardStMan columns cover every way it stores strings: scalars (short,
inline in the slot, and long, in the string buckets), direct fixed-shape
arrays, and non-direct arrays (casacore's SSMIndStringColumn), variable and
fixed shape, one and two dimensions, empty strings, non-ASCII text and
strings longer than a bucket, so the string-bucket chain is followed. A
small bucket size spreads the rows over several buckets. INCR is an
IncrementalStMan string array, which the reader refuses.
"""

import json
import sys
from pathlib import Path

import casacore.tables as pt
import numpy as np

NROWS = 12


def poltype(row):
    return ["X", "Y"] if row % 3 else ["R", "L"]


def var_cell(row):
    """Variable shapes: [2], [3], [2, 3] (numpy order) and [0]."""
    kind = row % 4
    if kind == 0:
        return np.array([f"v{row}a", f"v{row}b"])
    if kind == 1:
        return np.array(["", f"row {row}", "ä€"])
    if kind == 2:
        return np.array([[f"r{row}c{c}x{x}" for c in range(3)] for x in range(2)])
    return np.array([], dtype=str)


def long_cell(row):
    return np.array([("abcdefghij" * (30 + 7 * row))[: 300 + 37 * row], f"t{row}"])


def scalar(row):
    return "s" if row % 2 else f"a longer scalar string, row {row}"


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "table"
    desc = pt.maketabdesc(
        [
            pt.makearrcoldesc("POLARIZATION_TYPE", "", ndim=1, valuetype="string"),
            pt.makearrcoldesc("VAR", "", valuetype="string"),
            pt.makearrcoldesc("FIXED", "", shape=[2], valuetype="string"),
            pt.makearrcoldesc("DIRECT", "", shape=[2], valuetype="string", options=1),
            pt.makearrcoldesc("LONG", "", ndim=1, valuetype="string"),
            pt.makescacoldesc("NAME", ""),
            pt.makearrcoldesc("INCR", "", ndim=1, valuetype="string"),
        ]
    )
    dminfo = {
        "*1": {
            "TYPE": "StandardStMan",
            "NAME": "ssm",
            "SPEC": {"BUCKETSIZE": 512},
            "COLUMNS": [
                "POLARIZATION_TYPE",
                "VAR",
                "FIXED",
                "DIRECT",
                "LONG",
                "NAME",
            ],
        },
        "*2": {
            "TYPE": "IncrementalStMan",
            "NAME": "ism",
            "SPEC": {"BUCKETSIZE": 1024},
            "COLUMNS": ["INCR"],
        },
    }
    t = pt.table(str(path), desc, nrow=NROWS, dminfo=dminfo, ack=False)
    for row in range(NROWS):
        t.putcell("POLARIZATION_TYPE", row, np.array(poltype(row)))
        t.putcell("VAR", row, var_cell(row))
        t.putcell("FIXED", row, np.array([f"f{row}", "" if row % 2 else "g"]))
        t.putcell("DIRECT", row, np.array([f"d{row}", "e"]))
        t.putcell("LONG", row, long_cell(row))
        t.putcell("NAME", row, scalar(row))
        t.putcell("INCR", row, np.array(["X", "Y"]))
    t.close()

    t = pt.table(str(path), ack=False)
    oracle = {"nrows": t.nrows(), "columns": {}}
    for name in ("POLARIZATION_TYPE", "VAR", "FIXED", "DIRECT", "LONG", "NAME"):
        cells = []
        for row in range(t.nrows()):
            value = t.getcell(name, row)
            if isinstance(value, str):
                cells.append({"shape": [], "values": [value]})
                continue
            if isinstance(value, dict):  # python-casacore's string arrays
                shape = [int(s) for s in value["shape"]]
                values = list(value["array"])
            else:
                array = np.asarray(value)
                shape, values = list(array.shape), array.ravel().tolist()
            cells.append({"shape": shape, "values": values})
        oracle["columns"][name] = cells
    oracle["dminfo"] = {
        k: {"TYPE": v["TYPE"], "COLUMNS": list(v["COLUMNS"])}
        for k, v in t.getdminfo().items()
    }
    t.close()
    (out / "oracle.json").write_text(
        json.dumps(oracle, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1])
