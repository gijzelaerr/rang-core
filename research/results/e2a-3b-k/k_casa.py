"""research/e2a-3b-k.md, CASA side (CASA 6.7.6.14, `rang-o-casa_6.7.6.14.sif`,
`/opt/casa/bin/python -I`); imports no `rang`. e2a-3b-diag's `d1_casa.py`
(bound at /s2) with two more steps:

- `npzflags` (`vis`, `npz`): FLAG and FLAG_ROW from a packed export
  (`export_flags.py`; TIME, ANTENNA1, ANTENNA2 checked equal);
- `copycol` (`src`, `vis`, `column`): one column copied row by row from
  another copy of the same rows (TIME, ANTENNA1, ANTENNA2 checked equal);
- `editsol` (post hoc, section 7): one solution of a caltable copy flagged
  or unflagged, its value optionally from another table.

    k_casa.py base SRC_MS OUT_MS OUT.json ANTS
    k_casa.py tasks SPEC.json RESULT.json
"""

import json
import os
import sys

sys.path.insert(0, "/s2")

import d1_casa as D

B = D.B


def npzflags(vis, npz):
    import numpy as np
    from casatools import table

    z = np.load(npz)
    shape = tuple(int(x) for x in z["shape"])
    flag = np.unpackbits(z["flag"])[: np.prod(shape)].reshape(shape).astype(bool)
    tb = table()
    tb.open(vis, nomodify=False)
    if tb.nrows() != shape[0]:
        raise ValueError("row count differs from the export")
    for c in ("TIME", "ANTENNA1", "ANTENNA2"):
        if not (tb.getcol(c) == z[c]).all():
            raise ValueError(f"{c} differs from the export")
    for r0 in range(0, shape[0], B):
        k = min(B, shape[0] - r0)
        tb.putcol("FLAG", np.transpose(flag[r0 : r0 + k], (2, 1, 0)), r0, k)
        tb.putcol("FLAG_ROW", z["FLAG_ROW"][r0 : r0 + k], r0, k)
    tb.close()
    return {"rows": shape[0], "flagged_cells": int(flag.sum())}


def copycol(src, vis, column):
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
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        b.putcol(column, a.getcol(column, r0, k), r0, k)
    a.close()
    b.close()
    return {"rows": n, "column": column}


def editsol(src, dst, ant, rank, corr, flag, value_from=None):
    """A copy of caltable `src` at `dst` with the solution of antenna `ant`
    at the `rank`-th unique TIME, correlation `corr`, flagged (`flag`) and,
    with `value_from` (another caltable), CPARAM taken from its row of the
    same antenna and rank."""
    import shutil

    import numpy as np
    from casatools import table

    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    def row_of(tb):
        t = np.round(tb.getcol("TIME"), 3)
        times = np.unique(t)
        rows = np.flatnonzero((tb.getcol("ANTENNA1") == ant) & (t == times[rank]))
        if len(rows) != 1:
            raise ValueError(f"{len(rows)} rows for antenna {ant} rank {rank}")
        return int(rows[0])

    tb = table()
    tb.open(dst, nomodify=False)
    r = row_of(tb)
    f = tb.getcell("FLAG", r)
    before = {
        "flag": f.tolist(),
        "cparam": [str(x) for x in tb.getcell("CPARAM", r).ravel()],
    }
    f[corr] = bool(flag)
    tb.putcell("FLAG", r, f)
    if value_from:
        other = table()
        other.open(value_from)
        c = tb.getcell("CPARAM", r)
        c[corr] = other.getcell("CPARAM", row_of(other))[corr]
        other.close()
        tb.putcell("CPARAM", r, c)
    after = {"flag": tb.getcell("FLAG", r).tolist(),
             "cparam": [str(x) for x in tb.getcell("CPARAM", r).ravel()]}  # fmt: skip
    tb.close()
    return {"row": r, "before": before, "after": after}


_tasks = D.tasks


def tasks(spec_path, result_path):
    import casatasks

    extra = {"npzflags": npzflags, "copycol": copycol, "editsol": editsol}
    with open(spec_path) as fh:
        calls = json.load(fh)
    if not any(c["task"] in extra for c in calls):
        return _tasks(spec_path, result_path)
    # run the extra steps in place, the rest through d1_casa's runner, in order
    import time

    results = []
    for entry in calls:
        name, call = entry["task"], entry["args"]
        t0 = time.perf_counter()
        out, error = None, None
        try:
            if name in extra:
                out = extra[name](**call)
            else:
                tmp = result_path + ".one.json"
                with open(tmp + ".spec", "w") as fh:
                    json.dump([entry], fh)
                rc = _tasks(tmp + ".spec", tmp)
                with open(tmp) as fh:
                    one = json.load(fh)[0]
                out, error = one["return"], one["error"]
                os.remove(tmp)
                os.remove(tmp + ".spec")
                if rc and not error:
                    error = f"rc {rc}"
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            error = repr(exc)
        target = call.get("caltable") or call.get("dst")
        results.append({"task": name, "call": call, "seconds": time.perf_counter() - t0,
                        "error": error, "written": bool(target) and os.path.isdir(str(target)),
                        "return": json.loads(json.dumps(out, default=str)) if out else None})  # fmt: skip
        with open(result_path, "w") as fh:
            fh.write(json.dumps(results, indent=1) + "\n")
        if error:
            break
    del casatasks
    return 3 if any(r["error"] for r in results) else 0


if __name__ == "__main__":
    argv = sys.argv
    if len(argv) > 1 and argv[1] == "tasks" and len(argv) == 4:
        sys.exit(tasks(argv[2], argv[3]))
    if len(argv) > 1 and argv[1] == "base" and len(argv) == 6:
        sys.exit(D.base(*argv[2:6]))
    sys.exit(__doc__)
