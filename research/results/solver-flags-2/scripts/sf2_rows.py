"""solver-flags-2 (#58), section 4: give the rows of FIELD... of MS the flags of
flag version VERSION of SRC_MS (R's flags after its flag stage), after MS was
restored to its online flags. MS and SRC_MS are copies of one MS (same rows).

    python sf2_rows.py MS SRC_MS VERSION OUT.json FIELD [FIELD ...]

Writes FLAG and FLAG_ROW of those rows only, reads each chunk back, and
records per field the flagged fraction of the rows (all elements, and
(row, channel) cells flagged in any correlation over cross-correlations).
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_chunks, core_ms, core_ms_write
from rang.formats import flagversions

CHUNK = 4096


def main(ms, src, version, outp, *fields):
    t0 = time.perf_counter()
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    with core_ms.open_table(Path(src) / "FIELD") as t:
        if [str(n) for n in t.getcol("NAME")] != names:
            raise SystemExit("FIELD tables differ")
    out = {"ms": ms, "src": src, "version": version, "fields": {}}
    t = core_ms_write.open_table(ms, readonly=False)
    try:
        if t.nrows() != len(fid):
            raise SystemExit("row count")
        for name in fields:
            f_id = names.index(name)
            rows = np.flatnonzero(fid == f_id)
            el = el_n = cell = cell_n = 0
            for start, n in core_chunks.runs(rows.astype(np.int64)):
                for s0 in range(start, start + n, CHUNK):
                    k = min(CHUNK, start + n - s0)
                    f, r = flagversions.load(src, version, s0, k)
                    t.putcol("FLAG", f, s0)
                    t.putcol("FLAG_ROW", r, s0)
                    t.flush()
                    if not np.array_equal(t.getcol("FLAG", s0, k), f):
                        raise RuntimeError(f"rows {s0}+{k} read back differently")
                    el += int(f.sum())
                    el_n += f.size
                    x = a1[s0 : s0 + k] != a2[s0 : s0 + k]
                    fa = f[x].any(-1)
                    cell += int(fa.sum())
                    cell_n += fa.size
            out["fields"][name] = {"rows": len(rows), "flagged_elements": el / el_n,
                                   "flagged_cross_cells": cell / cell_n}  # fmt: skip
            print(name, out["fields"][name], flush=True)
    finally:
        t.close()
    out["seconds"] = time.perf_counter() - t0
    Path(outp).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4], sys.argv[4], *sys.argv[5:])
