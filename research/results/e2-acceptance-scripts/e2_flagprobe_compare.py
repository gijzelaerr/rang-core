"""E2 flag probe: compare the probe runs with each other and with E1's
whole-array flags, step by step.

    python e2_flagprobe_compare.py DIR

Reads DIR/group-scan*.npz and every DIR/{rang,tri}-*.npz; writes DIR/compare.json.
"""

import json
import sys
from pathlib import Path

import numpy as np


def main():
    d = Path(sys.argv[1])
    g = np.load(next(d.glob("group-scan*.npz")))
    scan, a1, a2 = g["probe"]
    sel = (g["antenna1"] == a1) & (g["antenna2"] == a2)
    e1 = {"e1-rang": g["rang"][sel], "e1-tricolour": g["tricolour"][sel]}
    runs = {
        p.stem: np.load(p)
        for p in sorted(d.glob("*.npz"))
        if p.stem.startswith(("rang-", "tri-"))
    }
    rep = {
        "probe": {"scan": int(scan), "a1": int(a1), "a2": int(a2)},
        "flagged": {k: int(v.sum()) for k, v in e1.items()},
    }
    for k, r in runs.items():
        rep["flagged"][k] = int(r["flags"].sum())
    finals = {**e1, **{k: r["flags"] for k, r in runs.items()}}
    names = list(finals)
    rep["final_cells_differ"] = {
        f"{x} vs {y}": int((finals[x] != finals[y]).sum())
        for i, x in enumerate(names)
        for y in names[i + 1 :]
    }
    ref = next(k for k in runs if k.startswith("tri-"))
    steps = [str(s) for s in runs[ref]["names"]]
    rep["steps"] = steps
    rep["stage_cells_differ_vs_" + ref] = {
        k: [
            int((r["stages"][i] != runs[ref]["stages"][i]).sum())
            for i in range(len(steps))
        ]
        for k, r in runs.items()
        if k != ref
    }
    rep["stage_flagged"] = {
        k: [int(s.sum()) for s in r["stages"]] for k, r in runs.items()
    }
    print(json.dumps(rep, indent=1))
    (d / "compare.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
