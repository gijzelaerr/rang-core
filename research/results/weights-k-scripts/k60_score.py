"""#60 scores (research/k-fallback-60.md sections 4 and 8, A1).

    python k60_score.py RUN_ROOT FU_KCOMPARE.json OUT.json

RUN_ROOT holds A/, B/, C/ (each e2n.ms and e2n.ms.rang-run) and prep-{A,B,C}.json. K1: arm B's K
flags (antenna and hand) against the antennas with no unflagged cross cell. K2: arm B's delays
re-referenced to m058 (tau_p - tau_m058, per hand) against CASA K at m058 on the same flags
(`casa_probe_m058_tau_ns` of e2n-followup's fu-kcompare.json), over antennas both solve. K3: arm B
against arm A, both re-referenced to m058, over the cut-off antennas. D1: flagged-solution
fraction per table in A, B (and C). D2: the target's flagged fraction after apply in A and B.
"""

import json
import sys
from pathlib import Path

import numpy as np

TABLES = ("K", "G", "B", "Gsec", "F", "Gpol", "Kcross", "Xf", "Df")
TARGET = "ASKAPJ1745"


def table(path):
    from rang.formats import caltable

    return caltable.read(path).main


def flag_fraction(main):
    f = np.concatenate([np.asarray(x, bool).ravel() for x in main["FLAG"]])
    return float(f.mean()), int(f.size)


def k_delays(main, nant):
    """Per antenna and hand: delay in ns and flag (one interval: solint inf, one row each)."""
    tau = np.full((nant, 2), np.nan)
    flag = np.ones((nant, 2), bool)
    for a, fp, fl in zip(main["ANTENNA1"], main["FPARAM"], main["FLAG"], strict=True):
        fp, fl = np.asarray(fp), np.asarray(fl, bool)
        tau[int(a)] = fp[0, :2]
        flag[int(a)] = fl[0, :2]
    return tau, flag


def stats(d):
    d = np.abs(np.asarray(d, float))
    d = d[np.isfinite(d)]
    if not d.size:
        return {"n": 0}
    return {"n": int(d.size), "median": float(np.median(d)), "p95": float(np.percentile(d, 95)),
            "max": float(d.max())}  # fmt: skip


def target_flagged(ms):
    from rang import core_ms

    with core_ms.open_table(f"{ms}/FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(TARGET)
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        n = f = 0
        for s in range(0, len(rows), 20000):
            fl = t.getcol_rows("FLAG", rows[s : s + 20000])
            f += int(np.count_nonzero(fl))
            n += fl.size
    return f / n


def main(root, kcompare, out):
    root = Path(root)
    rec = {"arms": {}}
    prep = {a: json.loads((root / f"prep-{a}.json").read_text()) for a in "ABC"}
    ids = prep["B"]["antenna_ids"]
    m058 = ids["m058"]
    cut = prep["B"]["primary"]["cut_off_from_m022"]
    rec["cut_off_from_m022"] = cut
    rec["flag_hashes"] = {a: {k: prep[a].get(k) for k in ("primary_flag_sha256",
                          "aftercal_primary_flag_sha256")} for a in "ABC"}  # fmt: skip
    taus = {}
    for arm in "ABC":
        cal = root / arm / "e2n.ms.rang-run" / "calibrate"
        if not (cal / "summary.json").exists():
            continue
        summ = json.loads((cal / "summary.json").read_text())
        r = {"refant_auto": summ.get("refant_auto"), "tables": {},
             "steps": [{"name": s.get("name"), "solutions": s.get("solutions")} for s in summ["steps"]]}
        for name in TABLES:
            if (cal / name).exists():
                frac, n = flag_fraction(table(cal / name))
                r["tables"][name] = {"flagged": frac, "cells": n}
        k = table(cal / "K")
        nant = max(int(a) for a in k["ANTENNA1"]) + 1
        tau, flag = k_delays(k, nant)
        taus[arm] = (tau, flag)
        r["K_flagged_antennas"] = [int(a) for a in np.flatnonzero(flag.all(1))]
        r["K_flagged_antenna_hands"] = int(flag.sum())
        applied = root / arm / "e2n.ms.rang-run" / "apply"
        if (applied / "summary.json").exists():
            r["target_flagged_after_apply"] = target_flagged(root / arm / "e2n.ms")
        rec["arms"][arm] = r
    fu = json.loads(Path(kcompare).read_text())["per_antenna"]
    casa = np.array([[np.nan if v is None else v for v in p["casa_probe_m058_tau_ns"]] for p in fu])
    casa_flag = np.array([p["casa_probe_m058_flag"] for p in fu])
    if "B" in taus:
        tau, flag = taus["B"]
        rel = tau - tau[m058]
        both = ~flag & ~casa_flag[:, None] & np.isfinite(casa)
        rec["K1_no_data_antennas"] = prep["B"]["primary"].get("no_data", [])
        rec["K2_B_vs_casa_m058"] = stats((rel - casa)[both])
        rec["K2_cut_off_only"] = stats((rel - casa)[cut][both[cut]])
        if "A" in taus:
            ta, fa = taus["A"]
            ra = ta - ta[m058]
            ok = ~flag & ~fa
            rec["K3_B_vs_A_cut_off"] = stats((rel - ra)[cut][ok[cut]])
            rec["K3_B_vs_A_all"] = stats((rel - ra)[ok])
    a, b = rec["arms"].get("A"), rec["arms"].get("B")
    if a and b:
        rec["D1"] = {n: b["tables"][n]["flagged"] - a["tables"][n]["flagged"]
                     for n in ("G", "B", "Gsec", "F") if n in a["tables"] and n in b["tables"]}  # fmt: skip
        if "target_flagged_after_apply" in a and "target_flagged_after_apply" in b:
            rec["D2"] = b["target_flagged_after_apply"] - a["target_flagged_after_apply"]
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
