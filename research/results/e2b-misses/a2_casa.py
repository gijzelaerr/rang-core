"""Arm A2's CASA side (research/e2b-misses.md 9.1); imports no `rang`.

CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, `/opt/casa/bin/python -I`):

    a2_casa.py base SRC_MS OUT_MS OUT.json   deep copy of FIELD_ID 1, 2 rows
    a2_casa.py tasks SPEC.json RESULT.json   the case's calls, in order

`base` keeps FIELD_IDs and subtables (a deep copy of a row selection) and
records the source row of every copied row. `tasks` runs CASA tasks and
three steps of this arm:
- `copytree` (`src`, `dst`);
- `putflags` (`vis`, `version` a flag-version table of the source MS,
  `first` the source row of the copy's row 0, optional `field`): FLAG and
  FLAG_ROW of the copy's rows (of that field only) from the version;
- `weights_ones` (`vis`): `initweights(wtmode='ones', dowtsp=True)`, then
  WEIGHT and WEIGHT_SPECTRUM read back, and an error unless every value is 1;
- `weights_read` (`vis`): the range of WEIGHT_SPECTRUM, recorded.
A step's error stops the case (the remaining calls are not run).
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

B = 4000


def base(src, out, out_json):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(src)
    fid = tb.getcol("FIELD_ID")
    rows = np.flatnonzero(np.isin(fid, [1, 2]))
    sel = tb.query("FIELD_ID IN [1,2]")
    sel.copy(out, deep=True, valuecopy=True, returnobject=False)
    sel.close()
    t_src = tb.getcol("TIME")[rows]
    a_src = tb.getcol("ANTENNA1")[rows], tb.getcol("ANTENNA2")[rows]
    tb.close()
    tb.open(out)
    same = bool(
        tb.nrows() == len(rows)
        and (tb.getcol("TIME") == t_src).all()
        and (tb.getcol("ANTENNA1") == a_src[0]).all()
        and (tb.getcol("ANTENNA2") == a_src[1]).all()
        and set(np.unique(tb.getcol("FIELD_ID")).tolist()) == {1, 2}
    )
    tb.close()
    contiguous = bool((np.diff(rows) == 1).all())
    info = {"rows": len(rows), "first": int(rows[0]), "last": int(rows[-1]),
            "contiguous": contiguous, "rows_match_source": same}  # fmt: skip
    Path(out_json).write_text(json.dumps(info, indent=1) + "\n")
    return 0 if (same and contiguous) else 3


def putflags(vis, version, first, field=None):
    import numpy as np
    from casatools import table

    tb, fv = table(), table()
    tb.open(vis, nomodify=False)
    fv.open(version)
    n = tb.nrows()
    set_cells = written = 0
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        f = fv.getcol("FLAG", first + r0, k)
        fr = fv.getcol("FLAG_ROW", first + r0, k)
        if field is not None:
            pick = tb.getcol("FIELD_ID", r0, k) == int(field)
            if not pick.any():
                continue
            old, oldr = tb.getcol("FLAG", r0, k), tb.getcol("FLAG_ROW", r0, k)
            f = np.where(pick[None, None, :], f, old)
            fr = np.where(pick, fr, oldr)
            written += int(pick.sum())
        else:
            written += k
        tb.putcol("FLAG", f, r0, k)
        tb.putcol("FLAG_ROW", fr, r0, k)
        set_cells += int(f.sum())
    fv.close()
    tb.close()
    return {"rows_written": written, "flagged_cells_in_written_blocks": set_cells}


def weight_range(vis):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis)
    lo, hi, n_not1 = np.inf, -np.inf, 0
    wlo, whi, wn = np.inf, -np.inf, 0
    for r0 in range(0, tb.nrows(), B):
        k = min(B, tb.nrows() - r0)
        w = tb.getcol("WEIGHT_SPECTRUM", r0, k)
        lo, hi = min(lo, float(w.min())), max(hi, float(w.max()))
        n_not1 += int((w != 1).sum())
        w = tb.getcol("WEIGHT", r0, k)
        wlo, whi = min(wlo, float(w.min())), max(whi, float(w.max()))
        wn += int((w != 1).sum())
    tb.close()
    return {"weight_spectrum_min": lo, "weight_spectrum_max": hi,
            "weight_spectrum_not_1": n_not1, "weight_min": wlo, "weight_max": whi,
            "weight_not_1": wn}  # fmt: skip


def tasks(spec_path, result_path):
    import casatasks

    calls = json.loads(Path(spec_path).read_text())
    logfile = calls[0].get("logfile") if calls and "logfile" in calls[0] else None
    if logfile:
        casatasks.casalog.setlogfile(logfile)
        calls = calls[1:]
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
                out = putflags(call["vis"], call["version"], int(call["first"]),
                               call.get("field"))  # fmt: skip
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
        target = call.get("caltable") or call.get("fluxtable") or call.get("dst")
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
    if cmd == "base" and len(argv) == 5:
        return base(*argv[2:5])
    if cmd == "tasks" and len(argv) == 4:
        return tasks(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
