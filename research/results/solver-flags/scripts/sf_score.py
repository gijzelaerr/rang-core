"""solver-flags (#58, #59), research/solver-flags.md section 5: the gates on E2-N and A1.

    python sf_score.py RUN_ROOT OUT.json

Arms R, M0, M1, M2 (RUN_ROOT/e2n-<arm>.ms and RUN_ROOT/a1/a1-<arm>.ms with their run
directories). Measures, after `apply`, per arm (flag-residual's fr_score.py measures
where they are the same):

- G-S: flagged fraction of every solved table's solutions; per calibrator field, each
  antenna's unflagged cells on its baselines to the reference antenna (antennas with
  none counted); the solver_flags records of the calibrate summary (tripwire).
- G-F: J1744-5144's fluxscale; 3C 286's p and chi and J1939-6342's residual
  polarisation from CORRECTED_DATA averaged over rows per 64-channel block.
- G-K, G-N, G-V, per field (calibrators and the target), over the rows of consecutive
  dump pairs (every row when a field's dump count is even): the flagged fraction (any
  correlation), also by baseline length in the reporter's seven bins; S = sum w^2 |d|^2 /
  (sum w)^2 with d the Stokes V consecutive-dump differences of CORRECTED_DATA over cells
  unflagged in that arm (fr_score.py's implied_noise); the rms of Stokes V over the kept
  cells.
- G-A (A1): on the calibrator fields (0, 1, 2), cross baselines, recall of the truth's
  above_5sigma cells and false flags on cells clean in `any`, after each arm's run.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from rang import core_ms, flag_residual

CAL_FIELDS = ("J1939-6342", "J1744-5144", "J1331+3030")
TARGET = "ASKAPJ1745"
ARMS = ("R", "M0", "M1", "M2")
XY, YX = 1, 2
BLOCK = 64
BINS_M = (0, 100, 200, 500, 1000, 2000, 4000, 9000)


def field_ids(ms):
    with core_ms.open_table(f"{ms}/FIELD") as t:
        return {str(n): i for i, n in enumerate(t.getcol("NAME"))}


def summary(ms, stage="calibrate"):
    p = Path(f"{ms}.rang-run") / stage / "summary.json"
    return json.loads(p.read_text()) if p.is_file() else None


def stokes(ms, fid):
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        cross = rows[a1 != a2]
        acc = cnt = None
        for i in range(0, len(cross), 20000):
            r = cross[i : i + 20000]
            d = t.getcol_rows("CORRECTED_DATA", r)
            f = t.getcol_rows("FLAG", r)
            d = np.where(f, 0, d)
            s, n = d.sum(0), (~f).sum(0)
            acc = s if acc is None else acc + s
            cnt = n if cnt is None else cnt + n
    v = acc / np.maximum(cnt, 1)
    nb = v.shape[0] // BLOCK
    v = v[: nb * BLOCK].reshape(nb, BLOCK, 4).mean(1)
    i_, q_ = (v[:, 0] + v[:, 3]).real / 2, (v[:, 0] - v[:, 3]).real / 2
    u_ = (v[:, 1] + v[:, 2]).real / 2
    p = np.sqrt(q_**2 + u_**2) / i_
    chi = 0.5 * np.degrees(np.arctan2(u_, q_))
    return {"p_median": float(np.nanmedian(p)), "chi_median_deg": float(np.nanmedian(chi)),
            "i_median": float(np.nanmedian(i_))}  # fmt: skip


def refant_connectivity(ms, fid, refant):
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
    ref = names.index(refant)
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        sel = rows[(a1 != a2) & ((a1 == ref) | (a2 == ref))]
        b1, b2 = t.getcol_rows("ANTENNA1", sel), t.getcol_rows("ANTENNA2", sel)
        good = np.zeros(len(names))
        for i in range(0, len(sel), 20000):
            f = t.getcol_rows("FLAG", sel[i : i + 20000])
            other = np.where(
                b1[i : i + 20000] == ref, b2[i : i + 20000], b1[i : i + 20000]
            )
            np.add.at(good, other, (~f.any(-1)).sum(1))
    good[ref] = np.nan
    return {"antennas_without": int(np.sum(good == 0)),
            "min_unflagged_cells": float(np.nanmin(good))}  # fmt: skip


def field_stats(ms, fid):
    """Flag fractions (overall, by baseline length), S and the Stokes V rms of kept
    cells over the rows of consecutive dump pairs (k, k+1), k even."""
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        rows = rows[a1 != a2]
        a1, a2 = t.getcol_rows("ANTENNA1", rows), t.getcol_rows("ANTENNA2", rows)
        tm = t.getcol_rows("TIME", rows)
        uvw = t.getcol_rows("UVW", rows)
        blen = np.hypot(uvw[:, 0], uvw[:, 1])
        nb = len(BINS_M) - 1
        bin_of = np.clip(np.searchsorted(BINS_M, blen, side="right") - 1, 0, nb - 1)
        fl_bin, n_bin = np.zeros(nb), np.zeros(nb)
        sw = sw2d = v2 = nv = 0.0
        flagged = cells = 0
        times = np.unique(tm)
        for k in range(0, len(times) - 1, 2):
            ia_all = np.flatnonzero(tm == times[k])
            ib_all = np.flatnonzero(tm == times[k + 1])
            for idx in (ia_all, ib_all):
                f = t.getcol_rows("FLAG", rows[idx]).any(-1)
                flagged += int(f.sum())
                cells += f.size
                np.add.at(fl_bin, bin_of[idx], f.sum(1))
                np.add.at(n_bin, bin_of[idx], f.shape[1])
            ka = a1[ia_all].astype(np.int64) * 1000 + a2[ia_all]
            kb = a1[ib_all].astype(np.int64) * 1000 + a2[ib_all]
            _, ia, ib = np.intersect1d(ka, kb, return_indices=True)
            if not len(ia):
                continue
            ra, rb = rows[ia_all[ia]], rows[ib_all[ib]]
            da, db = (
                t.getcol_rows("CORRECTED_DATA", ra),
                t.getcol_rows("CORRECTED_DATA", rb),
            )
            fa, fb = t.getcol_rows("FLAG", ra), t.getcol_rows("FLAG", rb)
            wa = t.getcol_rows("WEIGHT_SPECTRUM", ra).astype(np.float64)
            va, vb = (da[..., XY] - da[..., YX]) / 2j, (db[..., XY] - db[..., YX]) / 2j
            ka_ok = ~(fa[..., XY] | fa[..., YX])
            kb_ok = ~(fb[..., XY] | fb[..., YX])
            v2 += float((np.abs(va[ka_ok]) ** 2).sum() + (np.abs(vb[kb_ok]) ** 2).sum())
            nv += float(ka_ok.sum() + kb_ok.sum())
            ok = ka_ok & kb_ok
            with np.errstate(divide="ignore", invalid="ignore"):
                w = 4.0 / (1.0 / wa[..., XY] + 1.0 / wa[..., YX])
            ok &= np.isfinite(w) & (w > 0)
            d2 = np.abs(va - vb) ** 2 / 2.0
            sw += float(w[ok].sum())
            sw2d += float((w[ok] ** 2 * d2[ok]).sum())
    return {
        "flagged": flagged / max(cells, 1),
        "cells": cells,
        "flagged_by_length_m": {
            f"{BINS_M[i]}-{BINS_M[i + 1]}": (fl_bin[i] / n_bin[i] if n_bin[i] else None)
            for i in range(nb)
        },
        "S": sw2d / sw**2 if sw > 0 else math.nan,
        "v_rms_kept": math.sqrt(v2 / nv) if nv else math.nan,
    }


def solver_records(s):
    out = []
    for st in s["steps"]:
        for rec in st.get("solutions") or []:
            if isinstance(rec, dict) and "solver_flags" in rec:
                sf = rec["solver_flags"]
                out.append({"term": st["name"], "field_id": rec["field_id"],
                            "added": sf["added"], "resolved": sf["resolved"],
                            "solutions_flagged_first": sf["solutions_flagged_first"],
                            "solutions_flagged_last": sf["solutions_flagged_last"],
                            "passes": [{k: p[k] for k in ("cells", "input_flagged", "added")}
                                       for p in sf["passes"]]})  # fmt: skip
    return out


def e2n_arm(root, arm):
    ms = root / f"e2n-{arm}.ms"
    s = summary(ms)
    if s is None or summary(ms, "apply") is None:
        return {"missing": True}
    ids = field_ids(ms)
    refant = (s.get("refant_auto") or {}).get("names", [None])[0]
    rec = {
        "solutions_flagged": flag_residual.solution_flag_fractions(s["steps"]),
        "fluxscale": next((st.get("fluxscale") for st in s["steps"] if st["type"] == "F"), None),
        "refant": refant,
        "connectivity": {f: refant_connectivity(ms, ids[f], refant) for f in CAL_FIELDS if refant},
        "pol_3c286": stokes(ms, ids["J1331+3030"]),
        "pol_1934": stokes(ms, ids["J1939-6342"]),
        "fields": {f: field_stats(ms, ids[f]) for f in (*CAL_FIELDS, TARGET)},
        "solver_flags": solver_records(s),
    }  # fmt: skip
    flag = summary(ms, "flag")
    if flag is not None:
        rec["flag_stage"] = {
            k: flag.get(k) for k in ("flagged_before", "flagged_after", "known_rfi")
        }
    res = Path(f"{ms}.rang-run/calibrate/residual.json")
    if res.is_file():
        r = json.loads(res.read_text())
        rec["residual"] = {k: r.get(k) for k in ("solutions_flagged_before", "solutions_flagged_after", "tripwire_fired")}  # fmt: skip
    return rec


def a1_arm(root, arm):
    gen = root / "a1" / "gen"
    ms = root / "a1" / f"a1-{arm}.ms"
    if not (gen / "truth.npz").is_file() or summary(ms) is None:
        return {"missing": True}
    m = np.load(gen / "a1-full.rfi_mask.npz")
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        a1_, a2_ = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        nchan = int(m["nchan"])
        hit5 = n5 = hitc = nc = 0
        for i in range(0, t.nrows, 20000):
            sl = slice(i, min(i + 20000, t.nrows))
            sel = (fid[sl] <= 2) & (a1_[sl] != a2_[sl])
            f = t.getcol("FLAG", i, sl.stop - i).any(-1)
            any_ = np.unpackbits(m["any"][sl], axis=1, count=nchan).astype(bool)
            a5 = np.unpackbits(m["above_5sigma"][sl], axis=1, count=nchan).astype(bool)
            f, any_, a5 = f[sel], any_[sel], a5[sel]
            hit5 += int((f & a5).sum())
            n5 += int(a5.sum())
            hitc += int((f & ~any_).sum())
            nc += int((~any_).sum())
    s = summary(ms)
    return {"recall_above_5sigma": hit5 / max(n5, 1), "false_flag_clean": hitc / max(nc, 1),
            "solutions_flagged": flag_residual.solution_flag_fractions(s["steps"]),
            "solver_flags": solver_records(s)}  # fmt: skip


def gates(e, a):
    """Section 5's gates for M1 (None where an input is missing)."""
    out = {}
    r, m0, m1 = e.get("R", {}), e.get("M0", {}), e.get("M1", {})
    if not any(x.get("missing") for x in (r, m0, m1)):
        sf0, sf1 = m0["solutions_flagged"], m1["solutions_flagged"]
        out["G-S"] = {
            "per_term_rise_max": max(sf1[k] - sf0.get(k, 0.0) for k in sf1) if sf1 else 0.0,
            "lost_refant_antennas": {f: m1["connectivity"][f]["antennas_without"] - m0["connectivity"][f]["antennas_without"] for f in CAL_FIELDS},
            "tripwire_fired": any(x["solutions_flagged_last"] - x["solutions_flagged_first"] > 0.05 for x in m1["solver_flags"]),
        }  # fmt: skip
        g = out["G-S"]
        g["pass"] = g["per_term_rise_max"] <= 0.01 and all(v <= 0 for v in g["lost_refant_antennas"].values()) and not g["tripwire_fired"]  # fmt: skip
        fr, f1 = r["fluxscale"], m1["fluxscale"]
        out["G-F"] = {"fluxscale_R": fr, "fluxscale_M1": f1,
                      "p_3c286": (r["pol_3c286"]["p_median"], m1["pol_3c286"]["p_median"]),
                      "chi_3c286": (r["pol_3c286"]["chi_median_deg"], m1["pol_3c286"]["chi_median_deg"]),
                      "p_1934": (r["pol_1934"]["p_median"], m1["pol_1934"]["p_median"])}  # fmt: skip
        g = out["G-F"]
        flux = (fr["J1744-5144"]["fitted_flux_jy"], f1["J1744-5144"]["fitted_flux_jy"])
        g["flux_rel"] = flux[1] / flux[0] - 1
        g["pass"] = (abs(g["flux_rel"]) <= 0.005
                     and abs(g["p_3c286"][1] - g["p_3c286"][0]) <= 0.002
                     and abs(g["chi_3c286"][1] - g["chi_3c286"][0]) <= 0.5
                     and g["p_1934"][1] <= g["p_1934"][0] + 0.0005)  # fmt: skip
        out["G-K"] = {
            f: (r["fields"][f]["flagged"], m1["fields"][f]["flagged"])
            for f in CAL_FIELDS
        }
        out["G-K"]["pass"] = all(r["fields"][f]["flagged"] - m1["fields"][f]["flagged"] >= 0.05 for f in CAL_FIELDS)  # fmt: skip
        out["G-N"] = {f: math.sqrt(m1["fields"][f]["S"] / r["fields"][f]["S"]) for f in (*CAL_FIELDS, TARGET)}  # fmt: skip
        out["G-N"]["pass"] = all(out["G-N"][f] <= 0.98 for f in CAL_FIELDS) and out["G-N"][TARGET] <= 1.0  # fmt: skip
        vr, v1 = r["fields"][TARGET]["v_rms_kept"], m1["fields"][TARGET]["v_rms_kept"]
        out["G-V"] = {"R": vr, "M1": v1, "ratio": v1 / vr, "pass": v1 <= 1.02 * vr}
    a0, a1_ = a.get("M0", {}), a.get("M1", {})
    if not (a0.get("missing") or a1_.get("missing")) and a0 and a1_:
        out["G-A"] = {"recall": (a0["recall_above_5sigma"], a1_["recall_above_5sigma"]),
                      "false": (a0["false_flag_clean"], a1_["false_flag_clean"])}  # fmt: skip
        out["G-A"]["pass"] = (a1_["recall_above_5sigma"] >= a0["recall_above_5sigma"] + 0.10
                              and a1_["false_flag_clean"] <= a0["false_flag_clean"] + 0.02)  # fmt: skip
    return out


def main(root, outp, *arms):
    root = Path(root)
    arms = arms or ARMS
    e = {arm: e2n_arm(root, arm) for arm in arms}
    a = {arm: a1_arm(root, arm) for arm in arms}
    res = {"e2n": e, "a1": a, "gates_M1": gates(e, a)}
    Path(outp).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res["gates_M1"], indent=1, default=float))


if __name__ == "__main__":
    main(*sys.argv[1:])
