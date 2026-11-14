"""Arm A1's CASA side (research/e2b-misses.md 9.2); imports no `rang`.

CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, `/opt/casa/bin/python -I`):

    a1_casa.py mini SRC_MS VERSION CELLS.json OUT_MS OUT.json
    a1_casa.py run MINI_MS SPEC.json WORK_DIR OUT_DIR

`mini`: a deep copy of the cells' distinct rows (all channels, subtables
kept), FLAG and FLAG_ROW from the flag version `VERSION` (the input of 2b's
applycal), each row's antennas, field and scan checked against the cells.

`run`: for each entry of SPEC (`name`, `field`, `gaintable`, `interp`,
`gainfield`, `parang`, `unit`) a fresh copy of the mini MS, DATA set to
1 + 0j in all four correlations and FLAG false when `unit`, then one CASA
`applycal` (calflag, calwt False) of that field, and CORRECTED_DATA and
FLAG of every row saved to OUT_DIR/<name>.npz as (row, chan, corr).
"""

import json
import shutil
import sys
import time
from pathlib import Path


def mini(src, version, cells_path, out, out_json):
    import numpy as np
    from casatools import table

    cells = json.loads(Path(cells_path).read_text())
    rows = sorted({int(c["row"]) for c in cells})
    tb = table()
    tb.open(src)
    sel = tb.selectrows(rows)
    sel.copy(out, deep=True, valuecopy=True, returnobject=False)
    sel.close()
    tb.close()
    fv = table()
    fv.open(version)
    f = np.stack([fv.getcol("FLAG", r, 1)[..., 0] for r in rows], axis=-1)
    fr = np.array([fv.getcol("FLAG_ROW", r, 1)[0] for r in rows])
    fv.close()
    tb.open(out, nomodify=False)
    tb.putcol("FLAG", f)
    tb.putcol("FLAG_ROW", fr)
    got = {c: tb.getcol(c) for c in ("ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER")}
    cols = tb.colnames()
    tb.close()
    ok = []
    for c in cells:
        i = rows.index(int(c["row"]))
        ok.append(
            [int(got["ANTENNA1"][i]), int(got["ANTENNA2"][i])] == list(c["ant"])
            and int(got["FIELD_ID"][i]) == int(c["field"])
            and int(got["SCAN_NUMBER"][i]) == int(c["scan"])
        )
    info = {"rows": rows, "source": src, "flag_version": version, "columns": cols,
            "cells_match": bool(all(ok)), "cells": len(cells),
            "flagged_cells": int(f.sum())}  # fmt: skip
    Path(out_json).write_text(json.dumps(info, indent=1) + "\n")
    return 0 if all(ok) else 3


def run(mini_ms, spec_path, work, out_dir):
    import casatasks
    import numpy as np
    from casatools import table

    spec = json.loads(Path(spec_path).read_text())
    work, out_dir = Path(work), Path(out_dir)
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    casatasks.casalog.setlogfile(str(work / "casa.log"))
    tb = table()
    results = []
    for e in spec:
        t0 = time.perf_counter()
        ms = work / "w.ms"
        if ms.exists():
            shutil.rmtree(ms)
        shutil.copytree(mini_ms, ms)
        if e.get("unit"):
            tb.open(str(ms), nomodify=False)
            d = tb.getcol("DATA")
            tb.putcol("DATA", np.ones_like(d))
            tb.putcol("FLAG", np.zeros(d.shape, bool))
            tb.putcol("FLAG_ROW", np.zeros(d.shape[-1], bool))
            tb.close()
        error = None
        try:
            casatasks.applycal(vis=str(ms), field=e["field"], gaintable=e["gaintable"],
                               interp=e["interp"], gainfield=e["gainfield"],
                               calwt=[False] * max(1, len(e["gaintable"])),
                               parang=bool(e["parang"]), applymode="calflag",
                               flagbackup=False)  # fmt: skip
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            error = repr(exc)
        tb.open(str(ms))
        cols = tb.colnames()
        v = {
            "FIELD_ID": tb.getcol("FIELD_ID"),
            "FLAG": np.transpose(tb.getcol("FLAG"), (2, 1, 0)),
        }
        if "CORRECTED_DATA" in cols:
            v["CORRECTED_DATA"] = np.transpose(tb.getcol("CORRECTED_DATA"), (2, 1, 0))
        tb.close()
        np.savez(out_dir / f"{e['name']}.npz", **v)
        results.append({"name": e["name"], "error": error,
                        "seconds": time.perf_counter() - t0})  # fmt: skip
        Path(out_dir / "results.json").write_text(json.dumps(results, indent=1) + "\n")
    shutil.rmtree(work / "w.ms", ignore_errors=True)
    return 3 if any(r["error"] for r in results) else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "mini" and len(argv) == 7:
        return mini(*argv[2:7])
    if cmd == "run" and len(argv) == 6:
        return run(*argv[2:6])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
