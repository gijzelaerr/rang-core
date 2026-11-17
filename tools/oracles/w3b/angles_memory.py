# SPDX-License-Identifier: GPL-3.0-or-later
"""P's angle memory before and after W3b (research/w3b-chainchunks.md 1.5).

    python angles_memory.py MS CHUNK_ROWS OUT.json

Measures, with tracemalloc (NumPy reports its buffers to it), the peak
memory of `applycal`'s angle step: `ba65792`'s `_field_angles` (two float64
per MS row, the four row columns read whole; copied here verbatim) against
this branch's angle tables (`rang.applycal._field_angles`), on every field
of a read-only MS, and checks that both give the same angle for every row.
"""

import json
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
from rang import applycal, cal_pol, core_ms


class Reader:
    """The `WriteBack` calls `_field_angles` makes, on a read-only table."""

    def __init__(self, ms):
        self.ms = Path(ms)
        self.t = core_ms.open_table(ms)

    def chunks(self, n):
        n = int(n or self.t.nrows)
        for s in range(0, self.t.nrows, n):
            yield s, min(n, self.t.nrows - s)

    def read(self, name, s, n):
        return self.t.getcol(name, s, n)


def old_field_angles(w, chunk_rows, fields, frame, receptor_angle):
    """`rang.applycal._field_angles` at main ba65792."""
    spans = list(w.chunks(chunk_rows))
    names = ("FIELD_ID", "TIME", "ANTENNA1", "ANTENNA2")
    meta = {k: np.concatenate([w.read(k, s, n) for s, n in spans]) for k in names}
    ap = np.zeros(len(meta["TIME"]))
    aq = np.zeros(len(meta["TIME"]))
    for f in fields:
        rows = np.flatnonzero(meta["FIELD_ID"] == f)
        if not len(rows):
            continue
        ap[rows], aq[rows] = cal_pol.row_angles(
            w.ms,
            meta["TIME"][rows],
            meta["ANTENNA1"][rows],
            meta["ANTENNA2"][rows],
            f,
            frame,
            receptor_angle,
        )
    return ap, aq


def measure(fn, *args):
    tracemalloc.start()
    t0 = time.perf_counter()
    out = fn(*args)
    seconds = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return out, peak, seconds


def main(ms, chunk_rows, out):
    chunk_rows = int(chunk_rows)
    w = Reader(ms)
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        fields = list(range(t.nrows))
    receptor = -np.pi / 2
    # Warm up (astropy's tables and caches) so neither peak counts them.
    applycal._field_angles(w, chunk_rows, fields, "casa", receptor)
    (ap, aq), old_peak, old_s = measure(
        old_field_angles, w, chunk_rows, fields, "casa", receptor
    )
    tables, new_peak, new_s = measure(
        applycal._field_angles, w, chunk_rows, fields, "casa", receptor
    )
    equal = True
    for s, n in w.chunks(chunk_rows):
        fid, t, a1, a2 = (
            w.read(k, s, n) for k in ("FIELD_ID", "TIME", "ANTENNA1", "ANTENNA2")
        )
        for f, table in tables.items():
            sel = fid == f
            if sel.any():
                p, q = cal_pol.table_angles(table, t[sel], a1[sel], a2[sel])
                equal &= np.array_equal(p, ap[s : s + n][sel])
                equal &= np.array_equal(q, aq[s : s + n][sel])
    record = {
        "ms": str(ms),
        "rows": int(w.t.nrows),
        "chunk_rows": chunk_rows,
        "fields": fields,
        "table_bytes": int(sum(q.nbytes + t.nbytes for t, q in tables.values())),
        "old_peak_bytes": int(old_peak),
        "new_peak_bytes": int(new_peak),
        "old_seconds": old_s,
        "new_seconds": new_s,
        "angles_equal": bool(equal),
    }
    Path(out).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
