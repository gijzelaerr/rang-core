"""E2-B rows in the visibility domain (research/e2-acceptance.md 6.5; A0 6.3,
appendix A): Stokes I, p and chi per frequency bin of a calibrated field,
rang's arm against CASA's. Written and run on the development dry run
before it read an E2-B visibility.

    python e2_rows_b.py ROW RANG_MS RANG_DATA RANG_FLAG CASA_MS CASA_DATA CASA_FLAG OUT.json

ROW is `parity` (J1331+3030, scan 17: |dp| <= 0.1 point, |dchi| <= 0.5 deg)
or `j1830` (J1833-2103, scans 19 and 20: |I_rang / I_casa - 1| <= 1 %,
|dp| <= 0.1 point, |dchi| <= 1 deg); `field=NAME scans=a,b` after ROW
overrides the field and scans (the development test only). Each arm is read
from its own MS and columns (on the CASA copy: RANG_CORRECTED_DATA with
RANG_FLAG, and CORRECTED_DATA with FLAG).

Estimator, fixed here: "derotation to the sky frame" is the apply's (both
arms apply with parang true, CASA's P Jones and rang's port of it); the
scorer adds no rotation of its own. Development reading (dry run, LUNO
scan 1, 13 integrations, parallactic angle -169 deg), before any E2-B
visibility: MODEL_DATA through this estimator gives chi 32.6-33.0 deg (the
model's 33.0), DATA 10-16 deg, and both arms' CORRECTED_DATA 86-89 deg
(rang and CASA within 0.1 deg of each other), p 8.9-10.0 %. Per arm and bin, each correlation is averaged over the cells
whose four correlations are all unflagged in that arm's flags (unit weights,
as the solves); I = (XX + YY) / 2, Q = (XX - YY) / 2, U = (XY + YX) / 2,
V = (XY - YX) / 2j (E1b's _stokes4), real parts; p = hypot(Q, U) / I and
chi = atan2(U, Q) / 2. Bins: 100 MHz from 1.00 GHz, the last 1.60-1.65 GHz;
a bin is scored when both arms have >= 10 % of its cells unflagged, and
every scored bin must meet the limits.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from rang import core_ms

BLOCK = 2000
ROWS = {
    "parity": {"field": "J1331+3030", "scans": [17], "dp": 0.001, "dchi_deg": 0.5, "di": None},
    "j1830": {"field": "J1833-2103", "scans": [19, 20], "dp": 0.001, "dchi_deg": 1.0,
              "di": 0.01},
}  # fmt: skip
EDGES = [1.0e9, 1.1e9, 1.2e9, 1.3e9, 1.4e9, 1.5e9, 1.6e9, 1.65e9]


def accumulate(ms, data_col, flag_col, field, scans, freq):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(field)
    nb = len(EDGES) - 1
    chan_bin = np.digitize(freq, EDGES) - 1
    chan_bin[(freq < EDGES[0]) | (freq > EDGES[-1])] = -1
    chan_bin[freq == EDGES[-1]] = nb - 1
    s = np.zeros((nb, 4), complex)
    n = np.zeros(nb)
    tot = np.zeros(nb)
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        for r0 in range(0, nrow, BLOCK):
            k = min(BLOCK, nrow - r0)
            sel = np.isin(np.asarray(t.getcol("SCAN_NUMBER", r0, k)), scans) & (
                np.asarray(t.getcol("FIELD_ID", r0, k)) == fid
            )
            sel &= np.asarray(t.getcol("ANTENNA1", r0, k)) != np.asarray(
                t.getcol("ANTENNA2", r0, k)
            )
            if not sel.any():
                continue
            d = np.asarray(t.getcol(data_col, r0, k))[sel]
            f = np.asarray(t.getcol(flag_col, r0, k), bool)[sel]
            fr = np.asarray(t.getcol("FLAG_ROW", r0, k), bool)[sel]
            good = ~f.any(-1) & ~fr[:, None]
            for b in range(nb):
                cb = chan_bin == b
                g = good[:, cb]
                tot[b] += g.size
                n[b] += g.sum()
                s[b] += (d[:, cb] * g[..., None]).sum((0, 1))
    return s, n, tot


def stokes(s, n):
    v = s / np.maximum(n, 1)[:, None]
    i = ((v[:, 0] + v[:, 3]) / 2).real
    q = ((v[:, 0] - v[:, 3]) / 2).real
    u = ((v[:, 1] + v[:, 2]) / 2).real
    w = ((v[:, 1] - v[:, 2]) / 2j).real
    return i, q, u, w


def main(argv):
    row, *rest = argv
    spec = dict(ROWS[row])
    while rest and "=" in rest[0]:
        k, v = rest.pop(0).split("=", 1)
        spec[k] = v if k == "field" else [int(x) for x in v.split(",")]
    r_ms, r_col, r_flag, c_ms, c_col, c_flag, out = rest
    with core_ms.open_table(Path(r_ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ"))[0]
    arms = {}
    for arm, ms, col, fl in (
        ("rang", r_ms, r_col, r_flag),
        ("casa", c_ms, c_col, c_flag),
    ):
        s, n, tot = accumulate(ms, col, fl, spec["field"], spec["scans"], freq)
        i, q, u, v = stokes(s, n)
        arms[arm] = {"I": i, "Q": q, "U": u, "V": v, "frac": n / np.maximum(tot, 1),
                     "p": np.hypot(q, u) / i, "chi_deg": np.degrees(0.5 * np.arctan2(u, q))}  # fmt: skip
    bins = []
    for b in range(len(EDGES) - 1):
        a, c = arms["rang"], arms["casa"]
        rec = {"lo_hz": EDGES[b], "hi_hz": EDGES[b + 1],
               "frac_unflagged": [float(a["frac"][b]), float(c["frac"][b])],
               **{f"{k}_{arm}": float(arms[arm][k][b]) for k in ("I", "Q", "U", "V", "p",
                                                                 "chi_deg")
                  for arm in ("rang", "casa")}}  # fmt: skip
        rec["scored"] = bool(min(rec["frac_unflagged"]) >= 0.1)
        dchi = (a["chi_deg"][b] - c["chi_deg"][b] + 90) % 180 - 90
        rec["dp"] = float(a["p"][b] - c["p"][b])
        rec["dchi_deg"] = float(dchi)
        rec["dI_rel"] = float(a["I"][b] / c["I"][b] - 1)
        ok = abs(rec["dp"]) <= spec["dp"] and abs(dchi) <= spec["dchi_deg"]
        if spec["di"] is not None:
            ok = ok and abs(rec["dI_rel"]) <= spec["di"]
        rec["met"] = bool(ok) if rec["scored"] else None
        bins.append(rec)
    scored = [x for x in bins if x["scored"]]
    res = {"row": row, "spec": spec, "rang": [r_ms, r_col, r_flag], "casa": [c_ms, c_col, c_flag],
           "bins": bins, "bins_scored": len(scored),
           "max_abs_dp": max((abs(x["dp"]) for x in scored), default=None),
           "max_abs_dchi_deg": max((abs(x["dchi_deg"]) for x in scored), default=None),
           "max_abs_dI_rel": max((abs(x["dI_rel"]) for x in scored), default=None),
           "met": bool(scored) and all(x["met"] for x in scored)}  # fmt: skip
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "bins"}, indent=1))
    for x in bins:
        print(f"{x['lo_hz'] / 1e9:.2f}-{x['hi_hz'] / 1e9:.2f} GHz frac {x['frac_unflagged']} "
              f"p {x['p_rang']:.5f}/{x['p_casa']:.5f} chi {x['chi_deg_rang']:.2f}/"
              f"{x['chi_deg_casa']:.2f} dI {x['dI_rel']:+.2e} met {x['met']}")  # fmt: skip
    return 0 if math.isfinite(res["max_abs_dp"] or 0.0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
