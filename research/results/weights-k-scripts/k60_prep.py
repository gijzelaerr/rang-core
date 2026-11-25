"""#60 arms (research/k-fallback-60.md section 2): flags of an own copy of E2-N's MS.

    python k60_prep.py <ms> A|B <out.json>

A: every row restored to the flag stage's version (rang_calibrate_20261117T022650Z).
B: as A, then the J1939-6342 rows from the after-calibrate version
   (rang_apply_20261117T034709Z), the state that cuts 19 antennas off m022.
Writes the flagged fractions, the J1939 baselines wholly flagged and the antennas with
no unflagged cell to each antenna of interest (m022, m058) to out.json."""

import json
import sys
import time

import numpy as np
from rang import core_ms, core_ms_write, core_writeback
from rang.formats import flagversions

FLAGSTAGE = "rang_calibrate_20261117T022650Z"
AFTERCAL = "rang_apply_20261117T034709Z"
PRIMARY = "J1939-6342"
STEP = 20000


def cut_off(ms, fid, names):
    """Per antenna name: the antennas with no unflagged cross cell to it on field fid."""
    with core_ms.open_table(ms) as t:
        f = t.getcol("FIELD_ID")
        rows = np.flatnonzero(f == fid)
        a1, a2 = t.getcol("ANTENNA1")[rows], t.getcol("ANTENNA2")[rows]
        live = np.zeros(len(rows), bool)
        for s in range(0, len(rows), STEP):
            r = rows[s : s + STEP]
            fl = t.getcol_rows("FLAG", r)
            fr = t.getcol_rows("FLAG_ROW", r).astype(bool)
            live[s : s + STEP] = (~fl).reshape(len(r), -1).any(1) & ~fr
    cross = a1 != a2
    nant = int(max(a1.max(), a2.max())) + 1
    bl = set(zip(a1[cross & live].tolist(), a2[cross & live].tolist()))
    allbl = set(zip(a1[cross].tolist(), a2[cross].tolist()))
    out = {"baselines": len(allbl), "baselines_wholly_flagged": len(allbl - bl)}
    for name, a in names.items():
        linked = {q if p == a else p for p, q in bl if a in (p, q)}
        out[f"cut_off_from_{name}"] = [
            x for x in range(nant) if x != a and x not in linked
        ]
    return out


def fraction(ms):
    with core_ms.open_table(ms) as t:
        flagged = total = 0
        for s in range(0, t.nrows, STEP):
            fl = t.getcol("FLAG", s, min(STEP, t.nrows - s))
            flagged += int(np.count_nonzero(fl))
            total += fl.size
    return flagged / total


def main(ms, arm, out):
    t0 = time.perf_counter()
    rec = {"ms": ms, "arm": arm, "flagged_before": fraction(ms)}
    rec["rows_restored"] = int(core_writeback.restore_flags(ms, FLAGSTAGE))
    with core_ms.open_table(f"{ms}/FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(PRIMARY)
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        ants = [str(n) for n in t.getcol("NAME")]
    names = {n: ants.index(n) for n in ("m022", "m058")}
    if arm == "B":
        with core_ms.open_table(ms) as t:
            rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        w = core_ms_write.open_table(ms, readonly=False)
        try:
            # rows of one field are contiguous runs; write run by run
            breaks = np.flatnonzero(np.diff(rows) != 1) + 1
            for run in np.split(rows, breaks):
                for s in range(0, len(run), STEP):
                    start, n = int(run[s]), int(min(STEP, len(run) - s))
                    f, r = flagversions.load(ms, AFTERCAL, start, n)
                    w.putcol("FLAG", f, start)
                    w.putcol("FLAG_ROW", r, start)
                    w.flush()
        finally:
            w.close()
        rec["primary_rows_from"] = AFTERCAL
        rec["primary_rows"] = len(rows)
    rec["flagged_after"] = fraction(ms)
    rec["primary"] = cut_off(ms, fid, names)
    rec["antenna_ids"] = names
    rec["seconds"] = time.perf_counter() - t0
    json.dump(rec, open(out, "w"), indent=1)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    if sys.argv[2] not in ("A", "B"):
        raise SystemExit("arm must be A or B")
    main(*sys.argv[1:4])
