"""DL4s stage 3 (research/dl4s-screen.md 2.4): merge one block's selected
scans into a private MS.

    python dl4s_concat.py casa SCANS.json OUT.ms      # inside rang-o-casa_6.7.6.14.sif
    python dl4s_concat.py scans SCANS.json OUT.ms     # python-casacore, after it

`casa`: CASA `concat` of the source MSs (read only) into OUT.ms, as dl2-data.md
19's stage 2 route. `scans`: SCAN_NUMBER of OUT.ms set to each source's katdal
scan index (every source has SCAN_NUMBER 1), by the source's TIME range; then
checks the row sum against the manifest and the field names, and writes
OUT.ms.check.json.
"""

import json
import sys
from pathlib import Path


def casa(scans, out):
    from casatasks import concat

    vis = [s["ms"] for s in scans["scans"]]
    # the sources are read-only (dl2-data.md 4): copy the first without its
    # modes, then append the rest to it (concat's own copy keeps the modes
    # and then fails to move POINTING)
    import shutil

    shutil.copytree(vis[0], out, copy_function=shutil.copyfile)
    concat(vis=vis[1:], concatvis=out, copypointing=False, timesort=False)


def renumber(scans, out):
    import numpy as np
    from casacore import tables

    t = tables.table(out, readonly=False, ack=False)
    time = t.getcol("TIME")
    sn = np.zeros(len(time), np.int32)
    ranges = []
    for s in scans["scans"]:
        with tables.table(s["ms"], ack=False) as src:
            ts = src.getcol("TIME")
            lo, hi = float(ts.min()), float(ts.max())
            n = src.nrows()
        sel = (time >= lo - 1e-3) & (time <= hi + 1e-3)
        if (sn[sel] != 0).any():
            raise SystemExit(f"scan {s['scan']}: time range overlaps another source")
        sn[sel] = s["scan"]
        ranges.append({"scan": s["scan"], "rows_source": n, "rows_matched": int(sel.sum()),
                       "rows_manifest": s["rows"], "t0": lo, "t1": hi})  # fmt: skip
    if (sn == 0).any():
        raise SystemExit(
            f"{int((sn == 0).sum())} rows outside every source's time range"
        )
    t.putcol("SCAN_NUMBER", sn)
    nrows = t.nrows()
    t.close()
    with tables.table(f"{out}/FIELD", ack=False) as f:
        names = list(f.getcol("NAME"))
    want = sorted({s["target"] for s in scans["scans"]})
    check = {
        "rows": nrows,
        "rows_manifest": sum(s["rows"] for s in scans["scans"]),
        "fields": names,
        "fields_wanted": want,
        "scans": ranges,
    }
    check["ok"] = bool(
        nrows == check["rows_manifest"]
        and sorted(set(names)) == want
        and all(
            r["rows_matched"] == r["rows_source"] == r["rows_manifest"] for r in ranges
        )
    )
    Path(f"{out}.check.json").write_text(json.dumps(check, indent=1))
    print(json.dumps({k: check[k] for k in ("rows", "rows_manifest", "fields", "ok")}))
    return 0 if check["ok"] else 1


if __name__ == "__main__":
    mode, scans_json, out = sys.argv[1:4]
    sc = json.loads(Path(scans_json).read_text())
    if mode == "casa":
        casa(sc, out)
        sys.exit(0)
    sys.exit(renumber(sc, out))
