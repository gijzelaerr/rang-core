"""E2-N's calibrator rows (research/e2n-native.md section 6), E2-B's estimators
(`e2_rows_b.py`, `e2_leakage.py`) with E2-N's fields. The in-place order drops
rang's columns at `restore` before CASA's arm writes its own, so each arm's
per-bin sums are saved first (`snap`) and compared afterwards (`score`).

    python e2n_rows.py snap ARM MS DATA FLAG OUT.npz
        ARM rang or casa; per row field and scans (MS SCAN_NUMBER), E2-B's
        `accumulate` over E2-B's bins, plus the 1.3-1.5 GHz single bin of
        J1331+3030 (the same-scan reading that stands in for the transfer)
    python e2n_rows.py score RANG.npz CASA.npz OUT.json
        parity (J1331+3030: |dp| <= 0.1 point, |dchi| <= 0.5 deg) and the
        J1744-5144 row (E2-B's 1830-211 limits: |dI| <= 1 %, |dp| <= 0.1
        point, |dchi| <= 1 deg); every scored bin must meet; plus the
        same-scan 3C 286 reading per arm (reported, not gated)
    python e2n_rows.py leakage MS_DIR MS_NAME COLUMN OUT_DIR LABEL
        e2_leakage.py with FIELD = J0408-6545 (the adapted row: peak Q, U, V
        over I <= 0.3 %)

The scans come from SCANS below, set from the converted MS's own SCAN_NUMBER
and FIELD before the run (e2n-native.md results, MS map).
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))

import e2_rows_b as B

XCAL, GCAL, LEAK = "J1331+3030", "J1744-5144", "J0408-6545"
SCANS = {XCAL: None, GCAL: None}  # filled from the MS map before the run
LIMITS = {
    "parity": {"field": XCAL, "dp": 0.001, "dchi_deg": 0.5, "di": None},
    "j1744": {"field": GCAL, "dp": 0.001, "dchi_deg": 1.0, "di": 0.01},
}


def scans_of(ms, field):
    if SCANS.get(field):
        return SCANS[field]
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(field)
    with core_ms.open_table(ms) as t:
        f = np.asarray(t.getcol("FIELD_ID"))
        s = np.asarray(t.getcol("SCAN_NUMBER"))
    return sorted({int(x) for x in s[f == fid]})


def snap(arm, ms, col, flag, out):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ"))[0]
    res = {"arm": arm, "ms": str(ms), "column": col, "flag": flag}
    for row, lim in LIMITS.items():
        sc = scans_of(ms, lim["field"])
        s, n, tot = B.accumulate(ms, col, flag, lim["field"], sc, freq)
        res[row] = {"scans": sc, "s": s, "n": n, "tot": tot}
    sc = scans_of(ms, XCAL)
    s, n, tot = B.accumulate(ms, col, flag, XCAL, sc, freq, [1.3e9, 1.5e9])
    res["xcal_1p3_1p5"] = {"scans": sc, "s": s, "n": n, "tot": tot}
    np.save(out, res, allow_pickle=True)
    print(
        json.dumps(
            {k: (v if not isinstance(v, dict) else v["scans"]) for k, v in res.items()}
        )
    )
    return 0


def arm_stokes(a):
    i, q, u, v = B.stokes(a["s"], a["n"])
    return {"I": i, "Q": q, "U": u, "V": v, "frac": a["n"] / np.maximum(a["tot"], 1),
            "p": np.hypot(q, u) / i, "chi_deg": np.degrees(0.5 * np.arctan2(u, q))}  # fmt: skip


def score(rang_npz, casa_npz, out):
    ra = np.load(rang_npz, allow_pickle=True).item()
    ca = np.load(casa_npz, allow_pickle=True).item()
    edges = B.EDGES_DEFAULT
    res = {"rang": ra["ms"], "casa": ca["ms"]}
    for row, lim in LIMITS.items():
        a, c = arm_stokes(ra[row]), arm_stokes(ca[row])
        bins = []
        for b in range(len(edges) - 1):
            rec = {"lo_hz": edges[b], "hi_hz": edges[b + 1],
                   "frac_unflagged": [float(a["frac"][b]), float(c["frac"][b])],
                   **{f"{k}_{arm}": float(x[k][b]) for k in ("I", "p", "chi_deg")
                      for arm, x in (("rang", a), ("casa", c))}}  # fmt: skip
            rec["scored"] = bool(min(rec["frac_unflagged"]) >= 0.1)
            dchi = (a["chi_deg"][b] - c["chi_deg"][b] + 90) % 180 - 90
            rec["dp"] = float(a["p"][b] - c["p"][b])
            rec["dchi_deg"] = float(dchi)
            rec["dI_rel"] = float(a["I"][b] / c["I"][b] - 1)
            ok = abs(rec["dp"]) <= lim["dp"] and abs(dchi) <= lim["dchi_deg"]
            if lim["di"] is not None:
                ok = ok and abs(rec["dI_rel"]) <= lim["di"]
            rec["met"] = bool(ok) if rec["scored"] else None
            bins.append(rec)
        scored = [x for x in bins if x["scored"]]
        res[row] = {"limits": lim, "scans": ra[row]["scans"], "bins": bins,
                    "bins_scored": len(scored),
                    "max_abs_dp": max((abs(x["dp"]) for x in scored), default=None),
                    "max_abs_dchi_deg": max((abs(x["dchi_deg"]) for x in scored), default=None),
                    "max_abs_dI_rel": max((abs(x["dI_rel"]) for x in scored), default=None),
                    "met": bool(scored) and all(x["met"] for x in scored)}  # fmt: skip
    same = {}
    for arm, d in (("rang", ra), ("casa", ca)):
        x = arm_stokes(d["xcal_1p3_1p5"])
        p, chi = float(x["p"][0]), float(x["chi_deg"][0])
        dchi = (chi - 33.1 + 90) % 180 - 90
        same[arm] = {"p": p, "chi_deg": chi, "chi_minus_33_1_deg": float(dchi),
                     "frac_unflagged": float(x["frac"][0]),
                     "in_frozen_window": bool(0.090 <= p <= 0.101 and abs(dchi) <= 7.0)}  # fmt: skip
    res["xcal_same_scan_reported"] = same
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "bins"}
                      if isinstance(v, dict) else v for k, v in res.items()}, indent=1))  # fmt: skip
    return 0


def leakage(ms_dir, ms_name, column, out_dir, label):
    import e2_leakage as L

    L.FIELD = LEAK
    return L.main(ms_dir, ms_name, column, out_dir, label)


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    sys.exit({"snap": snap, "score": score, "leakage": leakage}[cmd](*args))
