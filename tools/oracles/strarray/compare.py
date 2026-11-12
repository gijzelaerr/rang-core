"""Compare rang's table reader with python-casacore on the string columns of
real Measurement Sets (research/feed-poltype-read.md).

Two steps, as python-casacore runs in WSL and the reader natively:

    python tools/oracles/strarray/compare.py dump out.json MS...   # WSL, casacore
    python tools/oracles/strarray/compare.py check out.json        # Windows, rang

`dump` writes every cell of every string column (scalar and array) of the
main table and each subtable, as `getcell` returns it (None for an undefined
cell), for at most `ROWS` rows per table. `check` reads the same cells with
`rang.core_ms`, cell by cell and as whole columns where the shapes agree, and
prints one line per table and a total; it exits 1 on any difference.
"""

import json
import sys
from pathlib import Path

ROWS = 2000


def windows_path(path):
    """A WSL path as the native reader opens it."""
    if path.startswith("/mnt/") and len(path) > 6 and path[6] == "/":
        return f"{path[5].upper()}:{path[6:]}"
    return "//wsl.localhost/Ubuntu" + path


def _tables(ms):
    import casacore.tables as pt

    out = [("", ms)]
    with pt.table(ms, ack=False) as t:
        for sub in t.getsubtables():
            out.append((Path(sub).name, sub))
    return out


def dump(out, mss):
    import casacore.tables as pt
    import numpy as np

    result = {"casacore": __import__("casacore").__version__, "tables": []}
    for ms in mss:
        for name, path in _tables(ms):
            with pt.table(path, ack=False) as t:
                entry = {"ms": ms, "table": name, "nrows": t.nrows(), "columns": {}}
                for col in t.colnames():
                    desc = t.getcoldesc(col)
                    if desc["valueType"] != "string":
                        continue
                    cells = []
                    for row in range(min(t.nrows(), ROWS)):
                        if not t.iscelldefined(col, row):
                            cells.append(None)
                            continue
                        value = t.getcell(col, row)
                        if isinstance(value, str):
                            cells.append({"shape": [], "values": [value]})
                        elif isinstance(value, dict):
                            cells.append(
                                {
                                    "shape": list(value["shape"]),
                                    "values": value["array"],
                                }
                            )
                        else:
                            a = np.asarray(value)
                            cells.append(
                                {"shape": list(a.shape), "values": a.ravel().tolist()}
                            )
                    entry["columns"][col] = {
                        "array": "ndim" in desc,
                        "manager": desc["dataManagerType"],
                        "cells": cells,
                    }
                result["tables"].append(entry)
    Path(out).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def check(path):
    import numpy as np
    from rang import core_ms

    result = json.loads(Path(path).read_text(encoding="utf-8"))
    bad = total = 0
    for entry in result["tables"]:
        where = windows_path(entry["ms"]) + (
            "/" + entry["table"] if entry["table"] else ""
        )
        cells_ok = cells_n = 0
        notes = []
        with core_ms.open_table(where) as t:
            for col, info in entry["columns"].items():
                want = info["cells"]
                for row, cell in enumerate(want):
                    if cell is None:
                        try:
                            t.getcol(col, row, 1)
                            notes.append(
                                f"{col}[{row}] undefined in casacore, read by rang"
                            )
                        except OSError:
                            pass
                        continue
                    cells_n += 1
                    try:
                        got = t.getcol(col, row, 1)[0]
                    except OSError as e:
                        notes.append(f"{col}[{row}]: {e}")
                        continue
                    exp = np.asarray(cell["values"], dtype=object).reshape(
                        cell["shape"]
                    )
                    if (
                        np.shape(got) == exp.shape
                        and np.asarray(got).tolist() == exp.tolist()
                    ):
                        cells_ok += 1
                    else:
                        notes.append(f"{col}[{row}]: {got!r} != {exp.tolist()!r}")
                shapes = {None if c is None else tuple(c["shape"]) for c in want}
                if (
                    want
                    and len(want) == entry["nrows"]
                    and len(shapes) == 1
                    and None not in shapes
                ):
                    whole = t.getcol(col)
                    exp = [
                        np.asarray(c["values"], dtype=object)
                        .reshape(c["shape"])
                        .tolist()
                        for c in want
                    ]
                    if whole.tolist() != exp:
                        notes.append(f"{col}: whole-column read differs")
        total += cells_n
        bad += len(notes)
        cols = ",".join(
            f"{c}{'[]' if i['array'] else ''}({i['manager']})"
            for c, i in entry["columns"].items()
        )
        print(f"{'ok ' if not notes else 'BAD'} {cells_ok}/{cells_n} {where} {cols}")
        for n in notes[:5]:
            print("    ", n)
    print(f"total {total} cells, {bad} problems, casacore {result['casacore']}")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(check(sys.argv[2]))
