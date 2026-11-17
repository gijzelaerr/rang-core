# SPDX-License-Identifier: MIT
"""research/e2a-kzero.md: gate 3b's composites and the K1 outlier count per
arm, on E2-A's field-0 rows (e2a-3b-k's `f0.ms`, read only for its row
metadata). Composites are `e2avg_common.composite` through `k_score.Comp`
(every 8th time, pooled field map), unchanged.

    python kz_score.py configs        the arms' resolved calibrate keys -> O/score-configs.json
    python kz_score.py score          every arm whose tables exist      -> O/score-kz.json

Arms: `archived` (E2-A's run, Windows, frozen wheel; e2a-3b-k's f0win), and
`off`, `zs`, `zsd` (this note, nash). Per arm: KGB1 (and KGB0, reported) of
the arm's K1 G1 B1 against
- CASA with its own K (step F's `tf`: pass 0 on the arm's flag-stage FLAG,
  pass 1 on its after-A FLAG), and
- CASA on the arm's K (step F's `k`, T-K3's construction: the arm's K0, K1,
  CASA's G0 B0 G1 B1),
median and p95, with and without ID 50 (m053). The archived arm's CASA
tables are e2a-3b-k's f0-casa-tf and f0-casa-k: control S, its composites
equal score-f0.json's to 1e-6 relative.
K1 outliers: unflagged K1 solutions (antenna, interval, hand) with
|tau| > 10 ns, listed; ID 50's interval 7 against the median of its other
intervals.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

# The pinned wheel's rang, imported before any script below puts the
# checkout's python/ (no extension built there) on sys.path; its submodules
# then resolve through the installed package.
import rang

if "site-packages" not in rang.__file__:
    raise SystemExit(f"rang from {rang.__file__}, not the installed wheel")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2a-3b-k"))

import k_score as KS

C = KS.C
O = Path.home() / "rang-data" / "outputs" / "e2a-kzero-20261117"
K = KS.O  # e2a-3b-k's outputs, read only
ARMS = ("archived", "off", "zs", "zsd")
NAMES1, NAMES0 = KS.NAMES1, KS.NAMES0
LIMIT_NS = 10.0
ODD, RANK = 50, 7
KEYS = ("k_zero_start", "bandpass_model_divided", "average_time", "refant", "uvrange")


def rang_dir(arm):
    if arm == "archived":
        return K / "f0win" / "rang-run" / "calibrate"
    # prep's copy of the arm's tables (what CASA's `k` arm used); the live run
    # directory is moved by `restore` and replaced by flux-run's scan-9 tables
    return O / arm / "f0" / "f0win" / "rang-run" / "calibrate"


def casa_dir(arm, case):
    if arm == "archived":
        return K / f"f0-casa-{case}"
    return O / arm / "f0" / f"f0-casa-{case}"


def configs():
    out = {}
    for arm in ARMS[1:]:
        p = O / arm / "e2a.ms.rang-run" / "config.resolved.json"
        if p.exists():
            cal = json.loads(p.read_text())["calibrate"]
            out[arm] = {k: cal.get(k) for k in KEYS}
            out[arm]["stages"] = json.loads(p.read_text())["run"]["stages"]
    want = {"off": (False, False), "zs": (True, False), "zsd": (True, True)}
    out["met"] = all(
        (out[a]["k_zero_start"], out[a]["bandpass_model_divided"]) == want[a]
        for a in want
        if a in out
    )
    C.write(O / "score-configs.json", out)
    return 0 if out["met"] else 3


def k1_outliers(path):
    _times, v = KS._kvals(C.table(path))  # (interval, antenna, hand), NaN flagged
    hit = np.argwhere(np.abs(v) > LIMIT_NS)
    rows = [{"interval": int(i), "antenna": int(a), "hand": "XY"[h], "ns": float(v[i, a, h])}
            for i, a, h in hit]  # fmt: skip
    odd = v[:, ODD, :]
    others = np.delete(odd, RANK, axis=0)
    return {
        "intervals": int(v.shape[0]),
        "unflagged_solutions": int(np.isfinite(v).sum()),
        "count_abs_gt_10ns": len(rows),
        "solutions": rows,
        "id50_interval7_ns": [float(x) for x in odd[RANK]],
        "id50_other_intervals_median_ns": [
            float(np.nanmedian(others[:, h])) for h in (0, 1)
        ],
        "id50_interval7_off_median_ns": [
            float(abs(odd[RANK, h] - np.nanmedian(others[:, h]))) for h in (0, 1)
        ],
        "median_abs_ns": float(np.nanmedian(np.abs(v))),
    }


def score():
    t0 = time.perf_counter()
    cp = KS.Comp(K / "f0.ms")
    out = {"rows_ms": str(K / "f0.ms"), "arms": {}, "pairs": {}}
    have = {}
    for arm in ARMS:
        rd = rang_dir(arm)
        if not (rd / "B1").exists():
            continue
        have[arm] = {"rang1": KS.tabs(rd, NAMES1), "rang0": KS.tabs(rd, NAMES0)}
        rec = {"k1": k1_outliers(rd / "K1")}
        for case, label in (("tf", "casa_own_k"), ("k", "casa_on_rang_k")):
            cd = casa_dir(arm, case)
            if not (cd / "B1").exists():
                rec[label] = "not run"
                continue
            if case == "tf":
                c1, c0 = KS.tabs(cd, NAMES1), KS.tabs(cd, NAMES0)
                rec["casa_own_k_k1"] = k1_outliers(cd / "K1")
            else:
                r = have[arm]
                c1 = [r["rang1"][0], *KS.tabs(cd, ("G1", "B1"))]
                c0 = [r["rang0"][0], *KS.tabs(cd, ("G0", "B0"))]
            rec[label] = {
                "KGB1": cp.rel(
                    f"{arm} rang1", have[arm]["rang1"], f"{arm} {case}1", c1
                ),
                "KGB0": cp.rel(
                    f"{arm} rang0", have[arm]["rang0"], f"{arm} {case}0", c0
                ),
            }
        out["arms"][arm] = rec
        for key in [k for k in cp.cache if not k.endswith(("rang1", "rang0"))]:
            del cp.cache[key]  # memory: keep only the rang composites for the pairs
    # added 2026-11-17 17:30, before any arm table existed: per solution, K0 and
    # K1 of each arm against OFF's (section 5's "no other K1 solution moves by
    # more than 1e-3 ns")
    out["k_moves"] = {}
    for a in ("zs", "zsd"):
        if a in have and "off" in have:
            rec = {}
            for n in ("K0", "K1"):
                _, va = KS._kvals(C.table(rang_dir(a) / n))
                _, vb = KS._kvals(C.table(rang_dir("off") / n))
                if va.shape != vb.shape:
                    rec[n] = {"shapes": [list(va.shape), list(vb.shape)]}
                    continue
                d = np.abs(va - vb)
                big = np.argwhere(d > 1e-3)
                rec[n] = {"max_ns": float(np.nanmax(d)), "median_ns": float(np.nanmedian(d)),
                          "flag_differs": int((np.isnan(va) != np.isnan(vb)).sum()),
                          "moved_gt_1e-3ns": [{"interval": int(i), "antenna": int(j), "hand": "XY"[h],
                                               "ns": float(va[i, j, h]), "off_ns": float(vb[i, j, h])}
                                              for i, j, h in big]}  # fmt: skip
            out["k_moves"][f"{a} vs off"] = rec
    # same-tool pairs (rang against rang): what the keys move, and host/build drift
    for a, b in (("off", "archived"), ("zs", "off"), ("zsd", "off"), ("zsd", "zs"),
                 ("zs", "archived"), ("zsd", "archived")):  # fmt: skip
        if a in have and b in have:
            out["pairs"][f"{a} vs {b}"] = {
                "KGB1": cp.rel(
                    f"{a} rang1", have[a]["rang1"], f"{b} rang1", have[b]["rang1"]
                ),
                "KGB0": cp.rel(
                    f"{a} rang0", have[a]["rang0"], f"{b} rang0", have[b]["rang0"]
                ),
            }
    # control S: the archived arm reproduces e2a-3b-k's score-f0.json
    ref = json.loads((ROOT / "research" / "results" / "e2a-3b-k" / "receipts"
                      / "score-f0.json").read_text())  # fmt: skip
    arc = out["arms"].get("archived", {})
    ctrl = {}
    for label, key in (("casa_own_k", "rang archived vs CASA own K, matched flags"),
                       ("casa_on_rang_k", "rang archived vs CASA on rang's K (T-K3 construction)")):  # fmt: skip
        got = (
            arc.get(label, {}).get("KGB1") if isinstance(arc.get(label), dict) else None
        )
        if got:
            ctrl[label] = {s: [got[s], ref[key][s], abs(got[s] / ref[key][s] - 1) <= 1e-6]
                           for s in ("median", "p95")}  # fmt: skip
    out["control_s"] = ctrl
    out["control_s_met"] = bool(ctrl) and all(
        v[2] for c in ctrl.values() for v in c.values()
    )
    out["seconds"] = time.perf_counter() - t0
    C.write(O / "score-kz.json", out)
    brief = {a: {lab: (KS.brief(r[lab]["KGB1"]) if isinstance(r.get(lab), dict) else r.get(lab))
                 for lab in ("casa_own_k", "casa_on_rang_k")} | {"k1_gt10": r["k1"]["count_abs_gt_10ns"]}
             for a, r in out["arms"].items()}  # fmt: skip
    print(json.dumps({"arms": brief, "control_s_met": out["control_s_met"]}, indent=1))
    return 0


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    sys.exit({"configs": configs, "score": score}[step](*args))
