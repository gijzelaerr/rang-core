"""Oracle side of task C6 (research/c6-polterms.md); imports no `rang`.

CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, run with `/opt/casa/bin/python -I`):

    oracle_pol.py edit <ms> <edit.json>
    oracle_pol.py tasks <spec.json> <result.json>
    oracle_pol.py export <ms> <out.npz> <COLUMN> ...

`edit` writes MODEL_DATA (adding it with `clearcal(addmodel=True)` if
absent) from an `.npz` (`rows`, `values` (row, chan, corr)) and ORs FLAG with
an `.npz` (`rows`, `flag`): the one shared step that gives CASA and rang the
same model and flags. `tasks` runs a list of `{"task": name, "args": {...}}`
in order (`gaincal`, `polcal`, `applycal`, `flagdata`, or `copytree` with
`src`, `dst`) and records each call, its wall time and any error. `export`
saves MS columns as (row, chan, corr) arrays.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path


def edit(ms, spec_path):
    import numpy as np
    from casatasks import clearcal
    from casatools import table

    spec = json.loads(Path(spec_path).read_text())
    tb = table()
    tb.open(ms)
    has_model = "MODEL_DATA" in tb.colnames()
    tb.close()
    if spec.get("model") and not has_model:
        clearcal(vis=ms, addmodel=True)
    tb.open(ms, nomodify=False)
    if spec.get("model"):
        z = np.load(spec["model"])
        model = tb.getcol("MODEL_DATA")  # (corr, chan, row)
        model[:, :, z["rows"]] = np.transpose(z["values"], (2, 1, 0))
        tb.putcol("MODEL_DATA", model)
    if spec.get("flag"):
        z = np.load(spec["flag"])
        flag = tb.getcol("FLAG")
        flag[:, :, z["rows"]] |= np.transpose(z["flag"], (2, 1, 0))
        tb.putcol("FLAG", flag)
    tb.close()


def tasks(spec_path, result_path):
    import casatasks

    calls = json.loads(Path(spec_path).read_text())
    results = []
    for entry in calls:
        name, call = entry["task"], entry["args"]
        started = time.perf_counter()
        try:
            if name == "copytree":
                if os.path.isdir(call["dst"]):
                    shutil.rmtree(call["dst"])
                out = shutil.copytree(call["src"], call["dst"])
            else:
                out = getattr(casatasks, name)(**call)
            error = None
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            out, error = None, repr(exc)
        target = call.get("caltable") or call.get("dst") or call.get("vis")
        results.append(
            {
                "task": name,
                "call": call,
                "seconds": time.perf_counter() - started,
                "error": error,
                "written": bool(target) and os.path.isdir(target),
                "return": json.loads(json.dumps(out, default=str)) if out else None,
            }
        )
    Path(result_path).write_text(json.dumps(results, indent=1) + "\n")


def export(ms, out, columns):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(ms)
    values = {}
    for c in columns:
        v = tb.getcol(c)
        if v.ndim == 3:
            v = np.ascontiguousarray(np.transpose(v, (2, 1, 0)))
        values[c] = v
    tb.close()
    np.savez(out, **values)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "edit" and len(argv) == 4:
        edit(argv[2], argv[3])
    elif cmd == "tasks" and len(argv) == 4:
        tasks(argv[2], argv[3])
    elif cmd == "export" and len(argv) >= 5:
        export(argv[2], argv[3], argv[4:])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
