"""D1 scores of research/e2a-3b-diag.md: composites (every 8th time, pooled,
`e2avg_common.composite` unchanged) and term differences between the
subset's arms, and the residual-delay check (section 3, "which delay is
right").

    python d1_run.py score D     -> D/d1-score.json
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply, core_ms

FCAL = "J1939-6342"
STEP = 8
NAMES = ("K0", "G0", "B0", "K1", "G1", "B1")
POOLED = [cal_apply.POOLED] * 3

# (label, arm a, arm b): rang arms first where one is rang
PAIRS = [
    ("reproduction R0-C0", "r0", "c0"),
    ("H-F R0-TF", "r0", "tf"),
    ("H-W R0-TW", "r0", "tw"),
    ("H-W TF-TW (CASA-CASA)", "tf", "tw"),
    ("H-M R0-TM", "r0", "tm"),
    ("H-M TF-TM (CASA-CASA)", "tf", "tm"),
    ("H-K R0-TK", "r0", "tk"),
    ("H-T TT-TF", "tt", "tf"),
    ("H-T R0-TT (rang-rang)", "r0", "tt"),
    ("H-I TI-TF", "ti", "tf"),
    ("H-I R0-TI (rang-rang)", "r0", "ti"),
]


def arm_dir(d, arm):
    if arm in ("r0", "tt", "ti"):
        return d / f"rang-{arm}.ms.rang-run" / "calibrate"
    return d / f"casa-{arm}"


def load(d, arm):
    p = arm_dir(d, arm)
    out = {}
    for n in NAMES:
        q = p / n
        if arm == "tk" and n in ("K0", "G0", "B0"):
            q = arm_dir(d, "tf") / n
        if arm == "tk" and n == "K1":
            q = arm_dir(d, "r0") / "K1"
        if q.exists():
            out[n] = C.table(q)
    return out


def composite_rel(ms, fid, ta, tb):
    a, fa = C.composite(ms, fid, ta, POOLED, step=STEP)
    b, fb = C.composite(ms, fid, tb, POOLED, step=STEP)
    return C.rel_stats(a, fa, b, fb)


def pair(ms, fid, A, B):
    out = {"terms": {}}
    for n in NAMES:
        if n in A and n in B:
            d = C.term_diff(A[n], B[n], "delay" if n[0] == "K" else "complex")
            out["terms"][n] = {k: v for k, v in d.items() if k != "rows"}
    for tag, ts in (("1", ("K1", "G1", "B1")), ("0", ("K0", "G0", "B0"))):
        if all(n in A and n in B for n in ts):
            out[f"KGB{tag}"] = composite_rel(ms, fid, [A[n] for n in ts], [B[n] for n in ts])
    return out


def residual_delays(ms, fid, tabs, k1):
    """Per K1 interval and antenna: the phase slope (ns) of the data
    corrected by `tabs` (K1, G1, B1; linear) against the model, from
    interval-averaged baselines (unflagged parallel hands, weights unit),
    solved per antenna by least squares with m022 fixed at 0; returns the
    statistics of |tau - mean over intervals of tau| per antenna."""
    with core_ms.open_table(ms) as t:
        n = t.nrows
        cols = {c: np.asarray(t.getcol(c)) for c in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
        data = np.asarray(t.getcol("DATA"))
        flag = np.asarray(t.getcol("FLAG"), bool) | np.asarray(t.getcol("FLAG_ROW"), bool)[:, None, None]
        model = np.asarray(t.getcol("MODEL_DATA"))
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        names = [str(x) for x in t.getcol("NAME")]
    ref = names.index("m022")
    rows = (cols["FIELD_ID"] == fid) & (cols["ANTENNA1"] != cols["ANTENNA2"])
    v, f = cal_apply.apply(data[rows], flag[rows], cols["TIME"][rows], cols["ANTENNA1"][rows],
                           cols["ANTENNA2"][rows], freq, tabs, interp="linear",
                           table_fields=POOLED)  # fmt: skip
    m = model[rows]
    t_rows, a1, a2 = cols["TIME"][rows], cols["ANTENNA1"][rows], cols["ANTENNA2"][rows]
    ktimes = np.unique(np.round(k1.column("TIME"), 3))
    # each row to its nearest K1 solution time (the interval it was solved in)
    ti = np.abs(t_rows[:, None] - ktimes[None, :]).argmin(1)
    x = (freq - freq.mean()) / 1e9
    ants = sorted(set(a1.tolist()) | set(a2.tolist()))
    col = {a: i for i, a in enumerate(a for a in ants if a != ref)}
    taus = np.full((len(ktimes), len(ants), 2), np.nan)
    for k in range(len(ktimes)):
        for h, hand in enumerate((0, 3)):
            eqs, rhs = [], []
            for p, q in sorted(set(zip(a1[ti == k].tolist(), a2[ti == k].tolist()))):
                sel = (ti == k) & (a1 == p) & (a2 == q)
                ok = ~f[sel][..., hand] & (np.abs(m[sel][..., hand]) > 0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    r = np.where(ok, v[sel][..., hand] / np.where(ok, m[sel][..., hand], 1), 0)
                s = r.sum(0)
                good = ok.any(0)
                if good.sum() < 16:
                    continue
                phi = np.angle(s[good])
                xx = x[good]
                beta = np.polyfit(xx, phi, 1)[0] / (2 * np.pi)  # ns
                row = np.zeros(len(col))
                if p != ref:
                    row[col[p]] += 1
                if q != ref:
                    row[col[q]] -= 1
                eqs.append(row)
                rhs.append(beta)
            if len(eqs) >= len(col):
                sol = np.linalg.lstsq(np.array(eqs), np.array(rhs), rcond=None)[0]
                for a, i in col.items():
                    taus[k, ants.index(a), h] = sol[i]
                taus[k, ants.index(ref), h] = 0.0
    dev = np.abs(taus - np.nanmean(taus, axis=0, keepdims=True))
    absolute = np.abs(taus)
    return {"about_antenna_mean_ns": C.stats(dev[np.isfinite(dev)]),
            "absolute_ns": C.stats(absolute[np.isfinite(absolute)]),
            "intervals": len(ktimes), "antennas": len(ants)}  # fmt: skip


def main(d):
    t0 = time.perf_counter()
    d = Path(d)
    ms = d / "rang-r0.ms"
    fid = C.field_id(ms, FCAL)
    arms = {a: load(d, a) for a in ("r0", "c0", "tf", "tw", "tm", "tk", "tt", "ti")}
    have = {a: sorted(v) for a, v in arms.items()}
    out = {"tables_present": have, "pairs": {}}
    for label, a, b in PAIRS:
        if len(arms[a]) == 6 and len(arms[b]) == 6:
            out["pairs"][label] = pair(ms, fid, arms[a], arms[b])
    # D0's swaps on the subset, against C0 and TF
    if len(arms["r0"]) == 6:
        r = arms["r0"]
        for base in ("c0", "tf"):
            c = arms[base]
            if len(c) != 6:
                continue
            sw = {}
            for i, n in enumerate(("K1", "G1", "B1")):
                s = [r[x] for x in ("K1", "G1", "B1")]
                s[i] = c[n]
                sw[f"swap_{n}"] = composite_rel(ms, fid, s, [c[x] for x in ("K1", "G1", "B1")])
            out[f"swaps_against_{base}"] = sw
    # residual delays (the data side), on the rang copy's DATA and MODEL_DATA
    out["residual_delays"] = {}
    for a in ("r0", "tf", "tk", "c0"):
        if len(arms[a]) == 6:
            T = arms[a]
            out["residual_delays"][a] = residual_delays(ms, fid, [T["K1"], T["G1"], T["B1"]], T["K1"])
    out["seconds"] = time.perf_counter() - t0
    C.write(d / "d1-score.json", out)
    brief = {k: {kk: vv.get("median") for kk, vv in v.items() if kk.startswith("KGB")}
             for k, v in out["pairs"].items()}  # fmt: skip
    print(json.dumps(brief, indent=1))
    return 0
