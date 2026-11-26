"""Read-only probe: CASA's K table on J1939-6342 and the flags it was given, per antenna."""

import json
import sys

import numpy as np
from casacore.tables import table

ms, ktab, version, out = sys.argv[1:5]
REF = [22, 23, 24]

k = table(ktab, ack=False)
a1 = k.getcol("ANTENNA1")
fp = k.getcol("FPARAM")[:, 0, :]
fl = k.getcol("FLAG")[:, 0, :]
snr = k.getcol("SNR")[:, 0, :]
a2k = k.getcol("ANTENNA2")
k.close()
ktab_rows = [
    {"ant": int(a), "refant": int(r), "tau_ns": fp[i].tolist(), "flag": fl[i].tolist(),
     "snr": snr[i].tolist()}
    for i, (a, r) in enumerate(zip(a1, a2k))
]  # fmt: skip

t = table(ms, ack=False)
fid = [  # noqa: RUF015
    i
    for i, n in enumerate(table(f"{ms}::FIELD", ack=False).getcol("NAME"))
    if n == "J1939-6342"
][0]
sel = t.query(
    f"FIELD_ID=={fid} && ANTENNA1!=ANTENNA2",
    columns="ROWNUMBER() AS R, ANTENNA1, ANTENNA2, TIME",
)
rows = sel.getcol("R")
b1 = sel.getcol("ANTENNA1")
b2 = sel.getcol("ANTENNA2")
tm = sel.getcol("TIME")
fv = table(f"{ms}.flagversions/flags.{version}", ack=False)
nant = 64
unfl_bl = np.zeros((nant, nant))
tot_bl = np.zeros((nant, nant))
# per time-averaged (solint inf) channel: cell unflagged if any time unflagged
anych = {}
step = 20000
for s in range(0, len(rows), step):
    r = rows[s : s + step]
    f = (
        np.stack([fv.getcell("FLAG", int(x)) for x in r])
        if False
        else fv.getcol("FLAG", int(r[0]), int(r[-1] - r[0] + 1))[r - r[0]]
    )
    ok = ~f  # (nrow, nchan, ncorr)
    okp = ok[..., [0, 3]].all(-1)  # both parallel hands unflagged
    for j in range(len(r)):
        i1, i2 = b1[s + j], b2[s + j]
        unfl_bl[i1, i2] += okp[j].sum()
        tot_bl[i1, i2] += okp[j].size
        key = (int(i1), int(i2))
        anych[key] = anych.get(key, np.zeros(okp.shape[1], bool)) | okp[j]
fv.close()
t.close()
unfl_bl = unfl_bl + unfl_bl.T
tot_bl = tot_bl + tot_bl.T
nch_any = np.zeros((nant, nant))
for (i1, i2), v in anych.items():
    nch_any[i1, i2] = nch_any[i2, i1] = v.sum()
ants = sorted(set(b1) | set(b2))
per = []
for a in ants:
    others = [b for b in ants if b != a]
    per.append({
        "ant": int(a),
        "unflagged_frac": float(unfl_bl[a, others].sum() / max(tot_bl[a, others].sum(), 1)),
        "bl_with_ref_unflagged_frac": {str(r): float(unfl_bl[a, r] / max(tot_bl[a, r], 1)) for r in REF if r != a},
        "bl_with_ref_chan_any_unflagged": {str(r): int(nch_any[a, r]) for r in REF if r != a},
        "n_bl_any_unflagged": int(sum(1 for b in others if nch_any[a, b] > 0)),
    })  # fmt: skip
json.dump({"ms": ms, "ktab": ktab, "flag_version": version, "field_id": fid,
           "ntimes": len(np.unique(tm)), "k": ktab_rows, "per_ant": per},
          open(out, "w"), indent=1)  # fmt: skip  # noqa: SIM115
for p, kk in zip(per, ktab_rows):
    print(
        p["ant"],
        kk["refant"],
        ["F" if x else "." for x in kk["flag"]],
        np.round(kk["tau_ns"], 3),
        np.round(kk["snr"], 1),
        round(p["unflagged_frac"], 3),
        p["bl_with_ref_unflagged_frac"],
        p["bl_with_ref_chan_any_unflagged"],
        p["n_bl_any_unflagged"],
    )
