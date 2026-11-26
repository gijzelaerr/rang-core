"""Read-only: on J1939-6342, how many baselines are wholly flagged in each flag version,
and which antennas' baselines to each candidate refant are wholly flagged."""

import json
import sys

import numpy as np
from casacore.tables import table

ms, field, out = sys.argv[1:4]
versions = sys.argv[4:]
t = table(ms, ack=False)
fid = list(table(f"{ms}::FIELD", ack=False).getcol("NAME")).index(field)
names = list(table(f"{ms}::ANTENNA", ack=False).getcol("NAME"))
sel = t.query(
    f"FIELD_ID=={fid} && ANTENNA1!=ANTENNA2",
    columns="ROWNUMBER() AS R, ANTENNA1, ANTENNA2",
)
rows, b1, b2 = sel.getcol("R"), sel.getcol("ANTENNA1"), sel.getcol("ANTENNA2")
t.close()
nant = len(names)
res = {"ms": ms, "field": field, "antennas": names, "versions": {}}
for v in versions:
    src = f"{ms}.flagversions/flags.{v}" if v != "MAIN" else ms
    fv = table(src, ack=False)
    cnt = np.zeros((nant, nant))
    tot = np.zeros((nant, nant))
    step = 20000
    for s in range(0, len(rows), step):
        r = rows[s : s + step]
        f = fv.getcol("FLAG", int(r[0]), int(r[-1] - r[0] + 1))[r - r[0]]
        ok = (~f).all(-1).sum(-1)  # unflagged cells (all 4 corr) per row
        np.add.at(cnt, (b1[s : s + step], b2[s : s + step]), ok)
        np.add.at(tot, (b1[s : s + step], b2[s : s + step]), f.shape[1])
    fv.close()
    cnt, tot = cnt + cnt.T, tot + tot.T
    present = tot > 0
    dead = present & (cnt == 0)
    per_ant_dead = dead.sum(1)
    res["versions"][v] = {
        "unflagged_frac": float(cnt.sum() / tot.sum()),
        "baselines": int(present.sum() // 2),
        "baselines_wholly_flagged": int(dead.sum() // 2),
        "per_ant_wholly_flagged_baselines": per_ant_dead.tolist(),
        "dead_to": {
            names[r]: [int(a) for a in np.where(dead[r])[0]] for r in range(nant)
        },
        "fully_connected_ants": [
            int(a) for a in range(nant) if per_ant_dead[a] == 0 and present[a].any()
        ],
        "per_ant_unflagged_frac": (cnt.sum(1) / np.maximum(tot.sum(1), 1)).tolist(),
    }
    vv = res["versions"][v]
    print(
        v,
        "unflagged",
        round(vv["unflagged_frac"], 4),
        "bl",
        vv["baselines"],
        "dead",
        vv["baselines_wholly_flagged"],
        "fully connected",
        vv["fully_connected_ants"],
    )
json.dump(res, open(out, "w"), indent=1)  # noqa: SIM115
