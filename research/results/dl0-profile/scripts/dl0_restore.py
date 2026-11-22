"""DL0 (#37): put flag version `name` back into FLAG of an own copy of E2-N's MS.

    python dl0_restore.py <ms> <version> <out.json>

Writes the flagged fraction before and after to `out.json`."""

import json
import sys
import time

import numpy as np

from rang import core_ms, core_writeback


def fraction(ms):
    with core_ms.open_table(ms) as t:
        n = t.nrows
        step = 20000
        flagged = total = 0
        for start in range(0, n, step):
            f = t.getcol("FLAG", start, min(step, n - start))
            flagged += int(np.count_nonzero(f))
            total += f.size
    return flagged / total


def main(ms, name, out):
    t0 = time.perf_counter()
    before = fraction(ms)
    rows = core_writeback.restore_flags(ms, name)
    after = fraction(ms)
    json.dump(
        {
            "ms": ms,
            "restored": name,
            "rows": int(rows),
            "flagged_before": before,
            "flagged_after": after,
            "seconds": time.perf_counter() - t0,
        },
        open(out, "w"),
        indent=1,
    )


if __name__ == "__main__":
    main(*sys.argv[1:4])
