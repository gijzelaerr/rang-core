"""Per-antenna K on J1939-6342: rang's, E2-N's CASA K, the follow-up's CASA K
(pre-extendflags flags) and the m058 mechanism probe, beside the unflagged
cells on each antenna's baseline to m022 (probe/k-probe.json).

python fu_kcompare.py RANG_K E2N_CASA_K FU_CASA_K PROBE_K K_PROBE_JSON OUT.json
Delays in ns, each table re-referenced to m022 (index 22) where m022 is unflagged.
"""

import json
import sys

import numpy as np
from casacore.tables import table


def read(path):
    t = table(path, ack=False)
    a = t.getcol("ANTENNA1")
    fp = t.getcol("FPARAM")[:, 0, :]
    fl = t.getcol("FLAG")[:, 0, :]
    snr = t.getcol("SNR")[:, 0, :] if "SNR" in t.colnames() else np.zeros_like(fp)
    t.close()
    n = int(a.max()) + 1
    tau = np.full((n, 2), np.nan)
    f = np.ones((n, 2), bool)
    s = np.full((n, 2), np.nan)
    tau[a], f[a], s[a] = fp, fl, snr
    tau[f] = np.nan
    return tau - tau[22], f, s


rk, ek, fk, pk, probe, out = sys.argv[1:7]
names = ("rang", "casa_e2n", "casa_followup", "casa_probe_m058")
tabs = dict(zip(names, (read(p) for p in (rk, ek, fk, pk))))
pr = {p["ant"]: p for p in json.load(open(probe))["per_ant"]}  # noqa: SIM115
rows = []
for i in range(tabs["rang"][0].shape[0]):
    row = {
        "ant": i,
        "cells_to_m022_after_calibrate": pr[i]["bl_with_ref_chan_any_unflagged"].get(
            "22"
        ),
    }
    for n, (tau, f, s) in tabs.items():
        row[f"{n}_tau_ns"] = [None if np.isnan(x) else float(x) for x in tau[i]]
        row[f"{n}_flag"] = bool(f[i].all())
        row[f"{n}_snr"] = [None if np.isnan(x) else float(x) for x in s[i]]
    rows.append(row)


def diff(a, b):
    d = np.abs(tabs[a][0] - tabs[b][0])
    d = d[~np.isnan(d)]
    return {"n": int(d.size), "median": float(np.median(d)) if d.size else None,
            "p95": float(np.percentile(d, 95)) if d.size else None,
            "max": float(d.max()) if d.size else None}  # fmt: skip


summary = {
    n: {"flagged_antennas": [i for i in range(len(rows)) if rows[i][f"{n}_flag"]]}
    for n in names
}
summary["abs_diff_ns"] = {f"{a} vs {b}": diff(a, b) for a, b in
                          (("rang", "casa_e2n"), ("rang", "casa_followup"), ("casa_e2n", "casa_followup"),
                           ("casa_followup", "casa_probe_m058"))}  # fmt: skip
json.dump({"summary": summary, "per_antenna": rows}, open(out, "w"), indent=1)  # noqa: SIM115
print(json.dumps(summary, indent=1))
