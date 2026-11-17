"""D1 of research/e2a-3b-diag.md, CASA side; imports no `rang`. CASA 6.7.6.14
(`rang-o-casa:6.7.6.14`, `/opt/casa/bin/python -I`), after
`results/e2b-misses/a2_casa.py`:

    d1_casa.py base SRC_MS OUT_MS OUT.json ANTS   deep copy of FIELD_ID 0 rows of antennas ANTS
    d1_casa.py tasks SPEC.json RESULT.json        calls in order

`base` opens SRC_MS read-only, keeps subtables and records the source row
of every copied row (OUT.json). `tasks` runs CASA tasks and these steps:
- `copytree` (`src`, `dst`);
- `putflags` (`vis`, `version` a flag-version table of the source MS, `rows`
  the base's OUT.json): FLAG and FLAG_ROW of every row from the version's
  source row;
- `copyflags` (`src`, `vis`): FLAG and FLAG_ROW from another copy of the same
  rows (TIME, ANTENNA1, ANTENNA2 checked equal);
- `weights_ones` (`vis`): initweights ones (dowtsp), read back as 1;
- `weights_read` (`vis`);
- `flaghash` (`vis`): sha256 of FLAG and FLAG_ROW.
A step's error stops the run.
"""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

B = 2000


def base(src, out, out_json, ants):
    import numpy as np
    from casatools import table

    ants = [int(a) for a in ants.split(",")]
    tb = table()
    tb.open(src)  # read-only
    lst = "[" + ",".join(map(str, ants)) + "]"
    sel = tb.query(f"FIELD_ID==0 AND ANTENNA1 IN {lst} AND ANTENNA2 IN {lst}")
    rows = np.asarray(sel.rownumbers(), np.int64)
    sel.copy(out, deep=True, valuecopy=True, returnobject=False)
    sel.close()
    t_src = np.array([tb.getcell("TIME", int(r)) for r in rows])
    a1 = np.array([tb.getcell("ANTENNA1", int(r)) for r in rows])
    a2 = np.array([tb.getcell("ANTENNA2", int(r)) for r in rows])
    tb.close()
    tb.open(out)
    same = bool(
        tb.nrows() == len(rows)
        and (tb.getcol("TIME") == t_src).all()
        and (tb.getcol("ANTENNA1") == a1).all()
        and (tb.getcol("ANTENNA2") == a2).all()
        and set(np.unique(tb.getcol("FIELD_ID")).tolist()) == {0}
    )
    scans = sorted(set(tb.getcol("SCAN_NUMBER").tolist()))
    tb.close()
    info = {"rows": len(rows), "antennas": ants, "scans": scans, "rows_match_source": same,
            "source_rows": rows.tolist()}  # fmt: skip
    Path(out_json).write_text(json.dumps(info) + "\n")
    return 0 if same else 3


def _runs(rows):
    """Contiguous runs (start index into rows, source start, length)."""
    out, i = [], 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[j] + 1 and j + 1 - i < B:
            j += 1
        out.append((i, int(rows[i]), j - i + 1))
        i = j + 1
    return out


def putflags(vis, version, rows_json):
    from casatools import table

    rows = json.loads(Path(rows_json).read_text())["source_rows"]
    tb, fv = table(), table()
    tb.open(vis, nomodify=False)
    fv.open(version)
    if tb.nrows() != len(rows):
        raise ValueError("row count differs from the base's record")
    flagged = 0
    for i, s, k in _runs(rows):
        f = fv.getcol("FLAG", s, k)
        tb.putcol("FLAG", f, i, k)
        tb.putcol("FLAG_ROW", fv.getcol("FLAG_ROW", s, k), i, k)
        flagged += int(f.sum())
    fv.close()
    tb.close()
    return {"rows_written": len(rows), "flagged_cells": flagged}


def copyflags(src, vis):
    from casatools import table

    a, b = table(), table()
    a.open(src)
    b.open(vis, nomodify=False)
    n = a.nrows()
    if n != b.nrows():
        raise ValueError("row counts differ")
    for c in ("TIME", "ANTENNA1", "ANTENNA2"):
        if not (a.getcol(c) == b.getcol(c)).all():
            raise ValueError(f"{c} differs")
    flagged = 0
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        f = a.getcol("FLAG", r0, k)
        b.putcol("FLAG", f, r0, k)
        b.putcol("FLAG_ROW", a.getcol("FLAG_ROW", r0, k), r0, k)
        flagged += int(f.sum())
    a.close()
    b.close()
    return {"rows": n, "flagged_cells": flagged}


def flaghash(vis):
    import numpy as np  # noqa: F401 (used below)
    from casatools import table

    tb = table()
    tb.open(vis)
    hf, hr = hashlib.sha256(), hashlib.sha256()
    n, flagged = tb.nrows(), 0
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        # casatools returns (corr, chan, row): transpose to the row-major order
        f = np.ascontiguousarray(np.transpose(tb.getcol("FLAG", r0, k), (2, 1, 0)))
        hf.update(f.tobytes())
        hr.update(np.ascontiguousarray(tb.getcol("FLAG_ROW", r0, k)).tobytes())
        flagged += int(f.sum())
    tb.close()
    return {"flag": hf.hexdigest(), "flag_row": hr.hexdigest(), "flagged_cells": flagged}


def weight_range(vis):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis)
    lo, hi, n_not1, wn = np.inf, -np.inf, 0, 0
    for r0 in range(0, tb.nrows(), B):
        k = min(B, tb.nrows() - r0)
        w = tb.getcol("WEIGHT_SPECTRUM", r0, k)
        lo, hi = min(lo, float(w.min())), max(hi, float(w.max()))
        n_not1 += int((w != 1).sum())
        wn += int((tb.getcol("WEIGHT", r0, k) != 1).sum())
    tb.close()
    return {"weight_spectrum_min": lo, "weight_spectrum_max": hi,
            "weight_spectrum_not_1": n_not1, "weight_not_1": wn}  # fmt: skip


def tasks(spec_path, result_path):
    import casatasks

    calls = json.loads(Path(spec_path).read_text())
    results = []
    for entry in calls:
        name, call = entry["task"], entry["args"]
        started = time.perf_counter()
        out, error = None, None
        try:
            if name == "copytree":
                if os.path.isdir(call["dst"]):
                    shutil.rmtree(call["dst"])
                shutil.copytree(call["src"], call["dst"])
            elif name == "putflags":
                out = putflags(call["vis"], call["version"], call["rows"])
            elif name == "copyflags":
                out = copyflags(call["src"], call["vis"])
            elif name == "flaghash":
                out = flaghash(call["vis"])
            elif name == "weights_ones":
                casatasks.initweights(vis=call["vis"], wtmode="ones", dowtsp=True)
                out = weight_range(call["vis"])
                if out["weight_spectrum_not_1"] or out["weight_not_1"]:
                    error = "weights not all 1 after initweights"
            elif name == "weights_read":
                out = weight_range(call["vis"])
            else:
                out = getattr(casatasks, name)(**call)
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            error = repr(exc)
        target = call.get("caltable") or call.get("dst")
        results.append({
            "task": name, "call": call, "seconds": time.perf_counter() - started,
            "error": error, "written": bool(target) and os.path.isdir(str(target)),
            "return": json.loads(json.dumps(out, default=str)) if out else None,
        })  # fmt: skip
        Path(result_path).write_text(json.dumps(results, indent=1) + "\n")
        if error:
            break
    return 3 if any(r["error"] for r in results) else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "base" and len(argv) == 6:
        return base(*argv[2:6])
    if cmd == "tasks" and len(argv) == 4:
        return tasks(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
