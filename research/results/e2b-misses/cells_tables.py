"""E2-B gate 2b's applycal cells over class C against rang's tables (post hoc,
research/e2b-misses.md section 2). For each (antenna, channel) of the frozen
arm's cell list, whether rang's B, Df and Xf solutions there are flagged (so
the apply bridges them from the neighbouring channels) and how wide that
flagged run is.

    python cells_tables.py CELLS.json CALIBRATE_DIR OUT.json

CELLS.json: fp-e2-acceptance research/results/e2-acceptance/e2b/frozen/
g2b-applycal-cells.json; CALIBRATE_DIR: the frozen run's rang-run/calibrate.
Reads three tables; no measurement set.
"""

import json
import os
import sys

import numpy as np
from rang.formats import caltable


def run_length(flags, ch):
    if not flags[ch]:
        return 0
    lo = hi = ch
    while lo > 0 and flags[lo - 1]:
        lo -= 1
    while hi < len(flags) - 1 and flags[hi + 1]:
        hi += 1
    return hi - lo + 1


def main(cells_path, caldir, out_path):
    with open(cells_path) as fh:
        cells = json.load(fh)
    tabs = {}
    for name in ("B", "Df", "Xf"):
        t = caltable.read(os.path.join(caldir, name))
        tabs[name] = (np.asarray(t.column("ANTENNA1")), np.asarray(t.flags))
    rows, pairs = [], set()
    for c in cells:
        for ant in c["ant"]:
            key = (ant, c["chan"])
            if key in pairs:
                continue
            pairs.add(key)
            rec = {"ant": ant, "chan": c["chan"]}
            for name, (a1, fl) in tabs.items():
                f = fl[a1 == ant].any(axis=-1).any(axis=0)  # any row, any receptor
                rec[name + "_flagged"] = bool(f[c["chan"]])
                rec[name + "_run"] = run_length(f, c["chan"])
            rows.append(rec)
    cell_any = []
    for c in cells:
        hit = {
            n: any(
                r[n + "_flagged"]
                for r in rows
                if r["ant"] in c["ant"] and r["chan"] == c["chan"]
            )
            for n in tabs
        }
        cell_any.append(hit)
    summary = {
        "cells": len(cells),
        "pairs": len(rows),
        "cells_with_a_flagged_solution": {n: sum(h[n] for h in cell_any) for n in tabs},
        "cells_with_any_flagged_solution": sum(any(h.values()) for h in cell_any),
        "base_rate_ant_chan_flagged": {
            n: float(fl.any(axis=-1).mean()) for n, (_, fl) in tabs.items()
        },
        "base_rate_ant_chan_flagged_B_or_Df": float(
            (tabs["B"][1].any(axis=-1) | tabs["Df"][1].any(axis=-1)).mean()
        ),
    }
    with open(out_path, "w") as fh:
        json.dump({"summary": summary, "pairs": rows}, fh, indent=1)
    print(json.dumps(summary))


if __name__ == "__main__":
    main(*sys.argv[1:4])
