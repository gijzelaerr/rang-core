"""The chi-offset decision rule (research/chi-offset.md 5), evaluated from the
arms' chi.json files; written 2026-11-13 after the freeze (the rule itself is
the frozen one).

    python evaluate.py SIM_DIR LUNO_DIR OUT.json [QF_JSON ...]

Angles are compared mod 180 deg (wrap to [-90, 90)). Rule (ii): sim truth
feed0 with the configured -90 (rang m90, CASA m90) against -chi0 + 2 psi - 90
per scan within 3 deg, and the slope of chi against psi across scans; feed0
with the receptor angle 0 (rang null, CASA feedms) within 1.11 deg of 33.
Rule (iii): LUNO rerun with the receptor angle 0, |chi - 33.1| <= 7 deg on
both 3C 286 scans (1.3-1.5 GHz), each Xf arm reported. Rule (i): theta_t from
the Xf-free q_f per integration, q_f = p_m cos 2(chi_m - psi - theta) with
the model's p_m, chi_m from MODEL_DATA in the same band; each QF_JSON is
{"label", "corrected": chi_vs_psi json, "model": chi_vs_psi json}; joint fit
over all of them and per file, every local minimum reported (q_f alone has
two branches on a short psi range).
"""

import json
import sys
from pathlib import Path

import numpy as np

CHI0 = 33.0


def wrap(x):
    return (np.asarray(x, float) + 90.0) % 180.0 - 90.0


def load(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def slope(rows):
    """d chi / d psi across scans, chi unwrapped against the 2 psi line."""
    psi = np.array([r["psi_deg"] for r in rows])
    chi = np.array([r["chi_deg"] for r in rows])
    if len(rows) < 2:
        return None
    best = None
    for k in (0.0, 2.0, -2.0):  # unwrap against each candidate slope, keep the best fit
        ref = k * psi
        c = ref + wrap(chi - ref)
        A = np.vstack([psi, np.ones_like(psi)]).T
        sol, res, *_ = np.linalg.lstsq(A, c, rcond=None)
        r = float(np.sum((A @ sol - c) ** 2))
        if best is None or r < best[1]:
            best = (float(sol[0]), r)
    return best[0]


def sim_rule(sim):
    out = {}
    for side, arms in (("rang", ("m90", "null", "gpol_noparang")), ("casa", ("m90", "feedms"))):
        for truth in ("control", "feed0", "revpsi"):
            for arm in arms:
                rows = load(Path(sim) / f"{side}-{truth}-{arm}" / "chi.json")
                if rows is None:
                    continue
                configured = -90.0 if arm in ("m90", "gpol_noparang") or truth != "feed0" else 0.0
                per = []
                for r in rows:
                    h3 = wrap(-CHI0 + 2 * r["psi_deg"] - 90.0)
                    per.append({"scan": r["scan"], "psi": r["psi_deg"], "chi": r["chi_deg"],
                                "p": r["p"], "d_from_33": float(wrap(r["chi_deg"] - CHI0)),
                                "d_from_h3_pred": float(wrap(r["chi_deg"] - h3)),
                                "q_f": r["q_f"]})  # fmt: skip
                out[f"{side}-{truth}-{arm}"] = {
                    "receptor_configured_deg": configured,
                    "scans": per,
                    "max_abs_d_from_33": max(abs(x["d_from_33"]) for x in per),
                    "max_abs_d_from_h3_pred": max(abs(x["d_from_h3_pred"]) for x in per),
                    "slope_chi_per_psi": slope(rows),
                }
    v = {}
    for side, zero in (("rang", "null"), ("casa", "feedms")):
        a = out.get(f"{side}-feed0-m90")
        b = out.get(f"{side}-feed0-{zero}")
        c = out.get(f"{side}-control-m90") or out.get(f"{side}-control-feedms")
        v[side] = {
            "feed0_m90_within_3_of_h3_pred": None if a is None else a["max_abs_d_from_h3_pred"] <= 3.0,
            "feed0_m90_slope_pm2": None if a is None or a["slope_chi_per_psi"] is None
            else abs(abs(a["slope_chi_per_psi"]) - 2.0) < 0.2,
            "feed0_zero_within_1.11_of_33": None if b is None else b["max_abs_d_from_33"] <= 1.11,
            "control_within_1.11_of_33": None if c is None else c["max_abs_d_from_33"] <= 1.11,
        }  # fmt: skip
    return out, v


def luno_rule(luno):
    out = {}
    band = "-CORRECTED_DATA-1.30-1.50"
    for d in sorted(Path(luno).glob("*-*")):
        res = load(d / "chi-all.json")
        if res is None:
            continue
        cor = res[band]
        mod = res["-MODEL_DATA-1.30-1.50"]
        per = []
        for r, m in zip(cor, mod, strict=True):
            per.append({"scan": r["scan"], "psi": r["psi_deg"], "chi": r["chi_deg"], "p": r["p"],
                        "model_chi": m["chi_deg"], "model_p": m["p"], "q_f": r["q_f"],
                        "d_from_33.1": float(wrap(r["chi_deg"] - 33.1))})  # fmt: skip
        # chi against lambda^2 per scan (the RM sign of section 6's added prediction)
        lam, chis = {}, {}
        for tag, rows in res.items():
            if not tag.startswith("-CORRECTED_DATA-") or tag == band:
                continue
            lo, hi = (float(x) for x in tag.split("-")[-2:])
            l2 = (299792458.0 / ((lo + hi) / 2 * 1e9)) ** 2
            for r in rows:
                lam.setdefault(r["scan"], []).append(l2)
                chis.setdefault(r["scan"], []).append(r["chi_deg"])
        rm = {}
        for s in lam:
            x, y = np.array(lam[s]), np.array(chis[s])
            y = y[0] + wrap(y - y[0])
            k, c = np.polyfit(x, y, 1)
            rm[str(s)] = {"slope_deg_per_m2": float(k), "rm_rad_m2": float(np.radians(k)),
                          "intercept_deg": float(c)}  # fmt: skip
        out[d.name] = {"scans": per, "chi_vs_lambda2": rm,
                       "max_abs_d_from_33.1": max(abs(x["d_from_33.1"]) for x in per)}  # fmt: skip
    return out


def theta_fit(specs):
    grid = np.arange(-90.0, 90.0, 0.05)
    allrows = []
    per = {}
    for spec in specs:
        s = json.loads(Path(spec).read_text())
        cor = json.loads(Path(s["corrected"]).read_text())["integrations"]
        mod = json.loads(Path(s["model"]).read_text())["integrations"]
        pm = float(np.mean([r["p"] for r in mod]))
        cm = float(np.degrees(np.angle(np.mean([r["q"] + 1j * r["u"] for r in mod])) / 2))
        rows = [(r["psi_deg"], r["q_f"], pm, cm) for r in cor]
        allrows += rows
        per[s["label"]] = {"model_p": pm, "model_chi": cm, "n": len(rows),
                           "psi_range": [min(r[0] for r in rows), max(r[0] for r in rows)],
                           "q_f_mean": float(np.mean([r[1] for r in rows])),
                           **minima(rows, grid)}  # fmt: skip
    return {"per_scan": per, "joint": minima(allrows, grid)}


def minima(rows, grid):
    psi, qf, pm, cm = (np.array(x) for x in zip(*rows, strict=True))
    pred = pm[None] * np.cos(np.radians(2 * (cm[None] - psi[None] - grid[:, None])))
    chi2 = ((qf[None] - pred) ** 2).sum(1)
    n = len(grid)
    loc = [i for i in range(n) if chi2[i] <= chi2[(i - 1) % n] and chi2[i] <= chi2[(i + 1) % n]]
    loc.sort(key=lambda i: chi2[i])
    rms = np.sqrt(chi2 / len(qf))
    return {"minima": [{"theta_deg": float(grid[i]), "rms_q": float(rms[i])} for i in loc[:4]],
            "rms_q_at_0": float(rms[np.argmin(abs(grid))]),
            "rms_q_at_m90": float(rms[0])}  # fmt: skip


def main(argv):
    sim, luno, outp, *qf = argv
    s, sv = sim_rule(sim)
    res = {"sim": s, "sim_verdict": sv, "luno": luno_rule(luno)}
    if qf:
        res["theta_fit"] = theta_fit(qf)
    Path(outp).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(sv, indent=1))
    for k, v in res["luno"].items():
        print(k, [(r["scan"], round(r["chi"], 2), round(r["d_from_33.1"], 2)) for r in v["scans"]],
              {s: round(x["rm_rad_m2"], 2) for s, x in v["chi_vs_lambda2"].items()})  # fmt: skip
    if qf:
        print(json.dumps(res["theta_fit"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
