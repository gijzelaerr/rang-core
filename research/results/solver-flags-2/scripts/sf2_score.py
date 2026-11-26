"""solver-flags-2 (#58), research/solver-flags-2.md section 5: records and gates.

    python sf2_score.py e2n RUN_ROOT OUT.json      # on nash: arms R, P0, PB, PG, PBG
    python sf2_score.py a1 RUN_ROOT OUT.json       # on glacier: RUN_ROOT/a1/a1-<arm>.ms, RUN_ROOT/a1/gen
    python sf2_score.py gates E2N.json A1.json M0_SCORE.json OUT.json

The measures are the first note's (research/results/solver-flags/scripts/sf_score.py,
imported unchanged): flagged-solution fractions, refant connectivity, fluxscale,
3C 286's p and chi, J1939-6342's residual polarisation, per-field flagged fraction,
S and Stokes V rms. Added here: gain amplitude ratios of B, G and Gsec against P0,
and A1's recall and false flags on J1939-6342 and SIM-GCAL only (section 5, G-A).
`gates` scores every candidate against R and P0 and reads the frozen outcome
(section 6); M0_SCORE.json is the first note's archived e2n/score.json (reported).
"""

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "solver-flags" / "scripts"))

ARMS = ("R", "P0", "PB", "PG", "PBG")
CANDIDATES = ("PB", "PG", "PBG")
TERMS = {"PB": ["B"], "PG": ["Gsec"], "PBG": ["B", "Gsec"]}
FLAGGED = ("J1939-6342", "J1744-5144")  # the fields the arms flag differently from R
TARGET = "ASKAPJ1745"
A1_FIELDS = ("J1939-6342", "SIM-GCAL")


def amp_ratio(ms_c, ms_0, name):
    """|g_C| / |g_P0| over solutions unflagged in both: median, p5, p95."""
    from rang.formats import caltable

    p_c = Path(f"{ms_c}.rang-run/calibrate/{name}")
    p_0 = Path(f"{ms_0}.rang-run/calibrate/{name}")
    if not (p_c.is_dir() and p_0.is_dir()):
        return None
    c, z = caltable.read(p_c).main, caltable.read(p_0).main
    gc, g0 = np.asarray(c["CPARAM"]), np.asarray(z["CPARAM"])
    if gc.shape != g0.shape:
        return {"shape": [list(gc.shape), list(g0.shape)]}
    ok = ~(np.asarray(c["FLAG"]) | np.asarray(z["FLAG"])) & (np.abs(g0) > 0)
    r = np.abs(gc[ok]) / np.abs(g0[ok])
    return {"median": float(np.median(r)), "p5": float(np.percentile(r, 5)),
            "p95": float(np.percentile(r, 95)), "n": int(r.size)}  # fmt: skip


def e2n(root, outp):
    import sf_score

    root = Path(root)
    rec = {arm: sf_score.e2n_arm(root, arm) for arm in ARMS}
    for arm in CANDIDATES:
        if rec[arm].get("missing") or rec["P0"].get("missing"):
            continue
        rec[arm]["amp_ratio_vs_P0"] = {
            n: amp_ratio(root / f"e2n-{arm}.ms", root / "e2n-P0.ms", n)
            for n in ("G", "B", "Gsec")
        }
    Path(outp).write_text(json.dumps(rec, indent=1, default=float))


def a1_arm(root, arm):
    from rang import core_ms

    gen = root / "a1" / "gen"
    ms = root / "a1" / f"a1-{arm}.ms"
    if not (gen / "truth.npz").is_file() or not ms.is_dir():
        return {"missing": True}
    m = np.load(gen / "a1-full.rfi_mask.npz")
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    want = [names.index(f) for f in A1_FIELDS]
    per = {f: [0, 0, 0, 0] for f in A1_FIELDS}
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        a1_, a2_ = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
        nchan = int(m["nchan"])
        for i in range(0, t.nrows, 20000):
            sl = slice(i, min(i + 20000, t.nrows))
            cross = a1_[sl] != a2_[sl]
            if not np.isin(fid[sl], want).any():
                continue
            f = t.getcol("FLAG", i, sl.stop - i).any(-1)
            any_ = np.unpackbits(m["any"][sl], axis=1, count=nchan).astype(bool)
            a5 = np.unpackbits(m["above_5sigma"][sl], axis=1, count=nchan).astype(bool)
            for name, k in zip(A1_FIELDS, want):
                s = cross & (fid[sl] == k)
                fs, an, a5s = f[s], any_[s], a5[s]
                p = per[name]
                p[0] += int((fs & a5s).sum())
                p[1] += int(a5s.sum())
                p[2] += int((fs & ~an).sum())
                p[3] += int((~an).sum())
    tot = np.sum([per[f] for f in A1_FIELDS], axis=0)
    out = {"recall_above_5sigma": tot[0] / max(tot[1], 1),
           "false_flag_clean": tot[2] / max(tot[3], 1),
           "per_field": {f: {"recall_above_5sigma": p[0] / max(p[1], 1),
                             "false_flag_clean": p[2] / max(p[3], 1)} for f, p in per.items()}}  # fmt: skip
    s = Path(f"{ms}.rang-run/calibrate/summary.json")
    if s.is_file():
        import sf_score

        steps = json.loads(s.read_text())
        out["solver_flags"] = sf_score.solver_records(steps)
    return out


def a1(root, outp):
    root = Path(root)
    rec = {arm: a1_arm(root, arm) for arm in ARMS}
    Path(outp).write_text(json.dumps(rec, indent=1, default=float))


def _flux(r):
    return r["fluxscale"]["J1744-5144"]["fitted_flux_jy"]


def gate_set(c, r, p0, a_c, a_p0):
    """Section 5's gates for candidate record `c` against R (`r`) and P0."""
    out = {}
    sf0, sf1 = p0["solutions_flagged"], c["solutions_flagged"]
    lost = {f: c["connectivity"][f]["antennas_without"] - p0["connectivity"][f]["antennas_without"] for f in FLAGGED}  # fmt: skip
    trip = any(x["solutions_flagged_last"] - x["solutions_flagged_first"] > 0.05 for x in c["solver_flags"])  # fmt: skip
    rise = max(sf1[k] - sf0.get(k, 0.0) for k in sf1) if sf1 else 0.0
    out["G-S"] = {"per_term_rise_max": rise, "lost_refant_antennas": lost, "tripwire_fired": trip,
                  "pass": rise <= 0.01 and all(v <= 0 for v in lost.values()) and not trip}  # fmt: skip
    g = {"flux": (_flux(r), _flux(c)),
         "p_3c286": (r["pol_3c286"]["p_median"], c["pol_3c286"]["p_median"]),
         "chi_3c286": (r["pol_3c286"]["chi_median_deg"], c["pol_3c286"]["chi_median_deg"]),
         "p_1934": (r["pol_1934"]["p_median"], c["pol_1934"]["p_median"])}  # fmt: skip
    g["flux_rel"] = g["flux"][1] / g["flux"][0] - 1
    g["pass"] = (abs(g["flux_rel"]) <= 0.005
                 and abs(g["p_3c286"][1] - g["p_3c286"][0]) <= 0.002
                 and abs(g["chi_3c286"][1] - g["chi_3c286"][0]) <= 0.5
                 and g["p_1934"][1] <= g["p_1934"][0] + 0.0005)  # fmt: skip
    out["G-F"] = g
    k = {f: (r["fields"][f]["flagged"], c["fields"][f]["flagged"]) for f in FLAGGED}
    k["pass"] = all(k[f][0] - k[f][1] >= 0.05 for f in FLAGGED)
    out["G-K"] = k
    n = {
        f: math.sqrt(c["fields"][f]["S"] / r["fields"][f]["S"])
        for f in (*FLAGGED, TARGET)
    }
    n["J1331+3030 (reported)"] = math.sqrt(c["fields"]["J1331+3030"]["S"] / r["fields"]["J1331+3030"]["S"])  # fmt: skip
    n["pass"] = all(n[f] <= 0.98 for f in FLAGGED) and n[TARGET] <= 1.0
    out["G-N"] = n
    vr, vc = r["fields"][TARGET]["v_rms_kept"], c["fields"][TARGET]["v_rms_kept"]
    out["G-V"] = {"R": vr, "C": vc, "ratio": vc / vr, "pass": vc <= 1.02 * vr}
    if a_c is not None and a_p0 is not None:
        out["G-A"] = {"recall": (a_p0["recall_above_5sigma"], a_c["recall_above_5sigma"]),
                      "false": (a_p0["false_flag_clean"], a_c["false_flag_clean"])}  # fmt: skip
        out["G-A"]["pass"] = (a_c["recall_above_5sigma"] >= a_p0["recall_above_5sigma"] + 0.10
                              and a_c["false_flag_clean"] <= a_p0["false_flag_clean"] + 0.02)  # fmt: skip
    return out


def outcome(g):
    """The first note's section 6 rules 2-4 for one candidate."""
    if not (g["G-S"]["pass"] and g["G-F"]["pass"]):
        return 4
    if all(g[k]["pass"] for k in ("G-K", "G-N", "G-V", "G-A") if k in g) and "G-A" in g:
        return 2
    return 3


def selection_ok(arm, c):
    """Rule 1: the pass records name only the arm's terms."""
    return all(x["term"] in TERMS[arm] for x in c["solver_flags"]) and {x["term"] for x in c["solver_flags"]} == set(TERMS[arm])  # fmt: skip


def gates(e2n_p, a1_p, m0_p, outp):
    e = json.loads(Path(e2n_p).read_text())
    a = json.loads(Path(a1_p).read_text()) if Path(a1_p).is_file() else {}
    m0 = json.loads(Path(m0_p).read_text())["e2n"]["M0"]
    r, p0 = e["R"], e["P0"]
    res = {"candidates": {}, "outcomes": {}}
    for arm in CANDIDATES:
        c = e[arm]
        if c.get("missing"):
            continue
        g = gate_set(c, r, p0, a.get(arm), a.get("P0"))
        g["selection_ok"] = selection_ok(arm, c)
        g["vs_M0 (reported)"] = {
            "flagged": {f: (m0["fields"][f]["flagged"], c["fields"][f]["flagged"]) for f in FLAGGED},
            "noise": {f: math.sqrt(c["fields"][f]["S"] / m0["fields"][f]["S"]) for f in (*FLAGGED, TARGET)},
            "flux": (_flux(m0), _flux(c)),
        }  # fmt: skip
        g["flux_vs_P0 (reported)"] = _flux(c) / _flux(p0) - 1
        g["amp_ratio_vs_P0 (reported)"] = c.get("amp_ratio_vs_P0")
        res["candidates"][arm] = g
        res["outcomes"][arm] = outcome(g)
    # P0 against R (reported, no outcome): the R-relative gates.
    gp = gate_set(p0, r, p0, None, None)
    res["P0_vs_R (reported)"] = {k: gp[k] for k in ("G-F", "G-K", "G-N", "G-V")}
    outs = res["outcomes"]
    if not all(g["selection_ok"] for g in res["candidates"].values()):
        note = 1
    elif any(v == 2 for v in outs.values()):
        note = 2
        passing = [k for k, v in outs.items() if v == 2]
        res["recipe"] = min(passing, key=lambda k: (res["candidates"][k]["G-N"][TARGET], len(TERMS[k])))  # fmt: skip
    elif any(v == 3 for v in outs.values()):
        note = 3
    else:
        note = 4
    res["outcome"] = note
    Path(outp).write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({"outcomes": outs, "outcome": note, "recipe": res.get("recipe")}))


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    {"e2n": e2n, "a1": a1, "gates": gates}[mode](*args)
