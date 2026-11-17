# SPDX-License-Identifier: MIT
"""Scores of research/calchain-floor.md (composites `J_p J_q^*` at every 8th
time of field 0, pooled field map, against truth; residuals; the controls).

    python cf_score.py r                  R: S0f' against e2a-3b-k's S0f (DATA, FLAG, tables, figures)
    python cf_score.py t0 CASE            T0: DATA = corrupt(M_T, J_T) on every row; the model column
    python cf_score.py t1 CASE            T1: truth sampled at lin's K0, G0 TIMEs (nothing solved)
    python cf_score.py arm CASE ARM       T2-T8 readings of one arm
"""

import hashlib
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from rang import cal_apply, core_ms
from rang.formats import caltable

O = Path.home() / "rang-data" / "outputs" / "calchain-floor-20261117"
K = Path.home() / "rang-data" / "outputs" / "e2a-3b-k-20261117"
FCAL = "J1939-6342"
STEP = 8
REF = "m022"
ODD = 50  # m053, |tau| near 2,392 ns
EPS32 = 2.0**-24
DATA_EPS = 2.5e-7
MP = 1e-5  # machine precision, section 4


def stats(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0}
    return {"n": int(x.size), "median": float(np.median(x)), "p95": float(np.percentile(x, 95)),
            "max": float(x.max())}  # fmt: skip


def write(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, default=float) + "\n")


def tab(path):
    return caltable.read(Path(path))


class Rows:
    """Field-0 cross rows at every 8th unique time of one MS."""

    def __init__(self, ms):
        self.ms = Path(ms)
        with core_ms.open_table(self.ms / "FIELD") as t:
            self.fid = [str(x) for x in t.getcol("NAME")].index(FCAL)
        with core_ms.open_table(self.ms) as t:
            c = {
                n: np.asarray(t.getcol(n))
                for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")
            }
        with core_ms.open_table(self.ms / "SPECTRAL_WINDOW") as t:
            self.freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
        with core_ms.open_table(self.ms / "ANTENNA") as t:
            self.names = [str(x) for x in t.getcol("NAME")]
        rows = (c["FIELD_ID"] == self.fid) & (c["ANTENNA1"] != c["ANTENNA2"])
        self.field_rows = np.flatnonzero(rows)
        times = np.unique(c["TIME"][rows])[::STEP]
        rows &= np.isin(c["TIME"], times)
        self.rows = np.flatnonzero(rows)
        self.time = c["TIME"][self.rows]
        self.a1, self.a2 = c["ANTENNA1"][self.rows], c["ANTENNA2"][self.rows]
        self.nant = len(self.names)
        self.ref = self.names.index(REF)

    def col(self, name, ms=None, rows=None):
        with core_ms.open_table(Path(ms or self.ms)) as t:
            return np.asarray(t.getcol_rows(name, self.rows if rows is None else rows))

    def flag(self, ms=None):
        f = self.col("FLAG", ms)
        fr = self.col("FLAG_ROW", ms)
        return (f | fr[:, None, None])[..., (0, 3)]

    def composite(self, tables, interp="linear"):
        ones = np.zeros((len(self.rows), len(self.freq), 4), np.complex64)
        ones[..., 0] = ones[..., 3] = 1
        v, f = cal_apply.apply(ones, np.zeros(ones.shape, bool), self.time, self.a1, self.a2,
                               self.freq, tables, interp=interp, direction="corrupt",
                               nant=self.nant, table_fields=[cal_apply.POOLED] * len(tables))  # fmt: skip
        return v[..., (0, 3)].astype(np.complex128), f[..., (0, 3)]

    def corrupt(self, model, tables, interp="linear"):
        v, f = cal_apply.apply(model, np.zeros(model.shape, bool), self.time, self.a1, self.a2,
                               self.freq, tables, interp=interp, direction="corrupt",
                               nant=self.nant, table_fields=[cal_apply.POOLED] * len(tables))  # fmt: skip
        return v[..., (0, 3)].astype(np.complex128), f[..., (0, 3)]

    def bound(self, ktab):
        """T8's float32 bound per cell (row, chan, hand) from a K table's delays."""
        _times, v = kvals(ktab)
        tau = np.nanmax(np.abs(v), 0)  # (ant, hand), ns
        tau = np.nan_to_num(tau)
        dnu = np.abs(self.freq - ktab.k_reference_frequency(0)) / 1e9  # GHz
        kb = (
            2
            * np.pi
            * EPS32
            * (tau[self.a1][:, None, :] + tau[self.a2][:, None, :])
            * dnu[None, :, None]
        )
        return kb + 4 * EPS32 + DATA_EPS


def rel(a, fa, b, fb, mask, rows, bound=None):
    """Relative |a - b| / |b| on cells unflagged in both and in `mask`."""
    ok = ~fa & ~fb & ~mask & (np.abs(b) > 0)
    r = np.abs(a - b) / np.where(np.abs(b) > 0, np.abs(b), 1)
    keep = (rows.a1 != ODD) & (rows.a2 != ODD)
    out = {"all": stats(r[ok]), "without_id50": stats(r[keep][ok[keep]])}
    if bound is not None:
        lim = np.maximum(MP, 10 * bound)
        out["frac_above_max(1e-5,10b)"] = (
            float((r[ok] > lim[ok]).mean()) if ok.any() else None
        )
        out["bound_median"] = float(np.median(bound[ok])) if ok.any() else None
        m = out["all"].get("median")
        m50 = out["without_id50"].get("median")
        out["machine_precision"] = bool(m is not None and m <= MP and m50 <= MP
                                        and out["frac_above_max(1e-5,10b)"] <= 0.05)  # fmt: skip
    return out


def kvals(t):
    tt = np.round(t.column("TIME"), 3)
    times = np.unique(tt)
    ant = t.column("ANTENNA1")
    nant = int(ant.max()) + 1
    v = np.full((len(times), nant, 2), np.nan)
    f = t.flags[:, 0, :]
    p = t.params[:, 0, :].real.astype(float)
    ti = np.searchsorted(times, tt)
    v[ti, ant] = np.where(f, np.nan, p)
    return times, v


def k_error(arm_k, truth_k, ref):
    """|(tau_p - tau_ref) - (truth_p - truth_ref)| (ns) per solution, truth at
    the dump nearest each solution TIME."""
    ta, va = kvals(arm_k)
    tt, vt = kvals(truth_k)
    near = np.abs(tt[None, :] - ta[:, None]).argmin(1)
    vt = vt[near]
    e = np.abs((va - va[:, ref : ref + 1]) - (vt - vt[:, ref : ref + 1]))
    e[:, ref] = np.nan
    keep = np.ones(e.shape[1], bool)
    keep[ODD] = False
    return {"all": stats(e), "without_id50": stats(e[:, keep]),
            "pivot_hz": [arm_k.k_reference_frequency(0), truth_k.k_reference_frequency(0)]}  # fmt: skip


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


def blocks(n, size=600):
    for i in range(0, n, size):
        yield slice(i, min(n, i + size))


# --------------------------------------------------------------------- R
def r():
    t0 = time.perf_counter()
    new = O / "stepped" / "sim-s0f-u.ms"
    old = K / "sim-s0f-u.ms"
    out = {}
    with core_ms.open_table(new) as tn, core_ms.open_table(old) as to, \
            core_ms.open_table(K / "src.ms") as ts:  # fmt: skip
        n = tn.nrows
        eq = True
        feq = True
        maxd = 0.0
        for s in blocks(n, 2000):
            a = np.asarray(tn.getcol("DATA", s.start, s.stop - s.start))
            b = np.asarray(to.getcol("DATA", s.start, s.stop - s.start))
            eq &= bool(np.array_equal(a, b))
            maxd = max(maxd, float(np.abs(a - b).max()))
            fa = np.asarray(tn.getcol("FLAG", s.start, s.stop - s.start))
            fs = np.asarray(ts.getcol("FLAG", s.start, s.stop - s.start))
            feq &= bool(np.array_equal(fa, fs))
        out["data_bitwise_equal_archived_s0f"] = eq
        out["data_max_abs_diff"] = maxd
        out["flag_equal_src_ms"] = feq
    # tables of the lin arm against archived U
    U = K / "sim-s0f-u.ms.rang-run" / "calibrate"
    L = O / "stepped" / "arm-lin.ms.rang-run" / "calibrate"
    tabs_ = {}
    for name in ("K0", "G0", "B0", "K1", "G1", "B1"):
        a, b = tab(L / name), tab(U / name)
        pa, pb = a.params, b.params
        fa, fb = a.flags, b.flags
        ok = ~fa & ~fb
        if name[0] == "K":
            d = np.abs(pa.real - pb.real)[ok]
        else:
            d = (np.abs(pa - pb) / np.maximum(np.abs(pb), 1e-30))[ok]
        tabs_[name] = {"rows": [a.nrows, b.nrows], "flags_differ": int((fa != fb).sum()),
                       "max": float(d.max()) if d.size else None}  # fmt: skip
    out["tables_lin_vs_archived_u"] = tabs_
    # e2a-3b-k's figures with this scorer, e2a-3b-k's cell set (the arm's own FLAG)
    rows = Rows(new)
    T = [tab(new.parent / "truth-s0f" / n) for n in ("K", "G", "B")]
    lin = O / "stepped" / "arm-lin.ms"
    own = rows.flag(lin)
    tc, tf = rows.composite(T)
    figs = {}
    for label, d, names in (("archived_u", U, ("K0", "G0", "B0", "K1", "G1", "B1")),
                            ("lin", L, ("K0", "G0", "B0", "K1", "G1", "B1"))):  # fmt: skip
        for tg, nn in (("KGB0", names[:3]), ("KGB1", names[3:])):
            a, fa = rows.composite([tab(d / x) for x in nn])
            figs[f"{label} {tg}"] = rel(a, fa, tc, tf, own, rows)["all"]
    out["figures_e2a3bk_cells"] = figs
    out["residual_lin_pass0_own_cells"] = residual(
        rows, lin, L, ("K0", "G0", "B0"), own
    )
    out["seconds"] = time.perf_counter() - t0
    write(O / "score-r.json", out)
    print(json.dumps(out, indent=1))
    return 0


def residual(rows, ms, d, names, mask, interp="linear"):
    m = rows.col("MODEL_DATA", ms)
    v = rows.col("DATA", ms)[..., (0, 3)].astype(np.complex128)
    c, f = rows.corrupt(m, [tab(d / n) for n in names], interp)
    del m
    keep = (rows.a1 != ODD) & (rows.a2 != ODD)
    ok = ~f & ~mask & (np.abs(c) > 0)
    rr = np.abs(v - c) / np.where(np.abs(c) > 0, np.abs(c), 1)
    return {"all": stats(rr[ok]), "without_id50": stats(rr[keep][ok[keep]])}


# --------------------------------------------------------------------- T0
def t0(case):
    t_0 = time.perf_counter()
    d = O / case
    ms = d / "sim-s0f-u.ms"
    T = [tab(d / "truth-s0f" / n) for n in ("K", "G", "B")]
    rows = Rows(ms)
    fr = rows.field_rows
    with core_ms.open_table(ms) as t:
        tm = np.asarray(t.getcol("TIME"))[fr]
        a1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        a2 = np.asarray(t.getcol("ANTENNA2"))[fr]
    _meds, mx, _n = [], 0.0, 0
    ph_max, _tv_max = 0.0, 0.0
    allr = []
    for s in blocks(len(fr), 600):
        idx = fr[s]
        with core_ms.open_table(K / "rang-u.ms") as t:
            m = np.asarray(t.getcol_rows("MODEL_DATA", idx))
        with core_ms.open_table(ms) as t:
            v = np.asarray(t.getcol_rows("DATA", idx))
        c, _ = cal_apply.apply(m, np.zeros(m.shape, bool), tm[s], a1[s], a2[s], rows.freq, T,
                               interp="linear", direction="corrupt", nant=rows.nant,
                               table_fields=[cal_apply.POOLED] * 3)  # fmt: skip
        c = c[..., (0, 3)].astype(np.complex128)
        vv = v[..., (0, 3)].astype(np.complex128)
        ok = np.abs(c) > 0
        rr = (np.abs(vv - c) / np.where(ok, np.abs(c), 1))[ok]
        allr.append(rr.astype(np.float32))
        mx = max(mx, float(rr.max()))
        mp = m[..., (0, 3)]
        nz = np.abs(mp) > 0
        ph_max = max(ph_max, float(np.abs(np.angle(mp[nz])).max()))
    allr = np.concatenate(allr)
    out = {"a_data_vs_corrupt_truth": {"median": float(np.median(allr)), "max": mx, "n": int(allr.size)},
           "c_model_phase_max_rad": ph_max}  # fmt: skip
    # (c) time variation per channel and (b) the column rang wrote on the arm copies
    m0 = rows.col("MODEL_DATA", K / "rang-u.ms")[..., (0, 3)]
    med = np.median(np.abs(m0), 0)
    out["c_model_time_variation_max"] = float(
        np.nanmax(np.abs(np.abs(m0) / np.where(med > 0, med, np.nan) - 1))
    )
    for arm in ("lin", "near", "strict"):
        a = d / f"arm-{arm}.ms"
        if (a / "table.dat").exists() or a.exists():
            try:
                ma = rows.col("MODEL_DATA", a)[..., (0, 3)]
            except Exception as e:  # noqa: BLE001
                out[f"b_model_{arm}"] = str(e)
                continue
            dd = np.abs(ma - m0) / np.where(np.abs(m0) > 0, np.abs(m0), 1)
            out[f"b_model_{arm}_vs_rang_u_max_rel"] = float(dd.max())
    out["seconds"] = time.perf_counter() - t_0
    write(O / f"score-t0-{case}.json", out)
    print(json.dumps(out, indent=1))
    return 0


# --------------------------------------------------------------------- T1
def sampled(truth, like, at=None):
    """A copy of `like` (an arm's K0 or G0) whose values are truth's at the
    dump nearest each row's TIME (or at `at(time) -> time`)."""
    out = deepcopy(like)
    tt = np.round(truth.column("TIME"), 3)
    ta = truth.column("ANTENNA1")
    tp = truth.params
    name = "FPARAM" if like.float_param else "CPARAM"
    times = like.column("TIME")
    if at is not None:
        times = np.array([at(x) for x in times])
        out.main["TIME"] = [float(x) for x in times]
    vals = []
    for t, a in zip(times, like.column("ANTENNA1")):
        sel = np.flatnonzero(ta == a)
        i = sel[np.abs(tt[sel] - t).argmin()]
        vals.append(
            np.asarray(tp[i]).astype(np.float32 if like.float_param else np.complex64)
        )
    out.main[name] = vals
    return out


def t1(case):
    t_0 = time.perf_counter()
    d = O / case
    ms = d / "sim-s0f-u.ms"
    rows = Rows(ms)
    T = [tab(d / "truth-s0f" / n) for n in ("K", "G", "B")]
    L = d / "arm-lin.ms.rang-run" / "calibrate"
    k0, g0 = tab(L / "K0"), tab(L / "G0")
    prim = rows.flag(K / "src.ms")
    tc, tf = rows.composite(T)
    bnd = rows.bound(T[0])
    with core_ms.open_table(ms) as t:
        tm = np.asarray(t.getcol("TIME"))
        sc = np.asarray(t.getcol("SCAN_NUMBER"))
    first = {s: float(tm[sc == s].min()) for s in np.unique(sc)}
    last = {s: float(tm[sc == s].max()) for s in np.unique(sc)}
    scan_of_sol = lambda x: min(first, key=lambda s: abs((first[s] + last[s]) / 2 - x))
    out = {"solution_times": sorted({float(x) for x in k0.column("TIME")}),
           "scan_ranges": {int(s): [first[s], last[s]] for s in first}}  # fmt: skip
    for label, at in (("centroid", None), ("first_dump", lambda x: first[scan_of_sol(x)]),
                      ("last_dump", lambda x: last[scan_of_sol(x)])):  # fmt: skip
        kr, gr = sampled(T[0], k0, at), sampled(T[1], g0, at)
        for part, tl in (("KG", [kr, gr]), ("K", [kr, T[1]]), ("G", [T[0], gr])):
            a, fa = rows.composite(tl)
            out[f"{label} {part}"] = rel(a, fa, tc, tf, prim, rows, bnd)
    # residual of the DATA against R (centroid): model of rang-u.ms
    kr, gr = sampled(T[0], k0), sampled(T[1], g0)
    m = rows.col("MODEL_DATA", K / "rang-u.ms")
    v = rows.col("DATA", ms)[..., (0, 3)].astype(np.complex128)
    c, f = rows.corrupt(m, [kr, gr])
    ok = ~f & ~prim & (np.abs(c) > 0)
    out["centroid residual"] = stats(
        (np.abs(v - c) / np.where(np.abs(c) > 0, np.abs(c), 1))[ok]
    )
    out["seconds"] = time.perf_counter() - t_0
    write(O / f"score-t1-{case}.json", out)
    print(json.dumps(out, indent=1))
    return 0


# --------------------------------------------------------------------- arms
NAMES0 = ("K0", "G0", "B0")
NAMES1 = ("K1", "G1", "B1")


def solvable(rows, ms):
    """(ant, chan, hand): any unflagged flag-stage cell of field 0 on a
    baseline with uv distance > 150 m (U's uvrange)."""
    fr = rows.field_rows
    with core_ms.open_table(ms) as t:
        a1 = np.asarray(t.getcol("ANTENNA1"))[fr]
        a2 = np.asarray(t.getcol("ANTENNA2"))[fr]
        uvw = np.asarray(t.getcol("UVW"))[fr]
    long_ = (np.hypot(uvw[:, 0], uvw[:, 1]) > 150) & (a1 != a2)
    out = np.zeros((rows.nant, len(rows.freq), 2), bool)
    with core_ms.open_table(K / "src.ms") as t:
        for s in blocks(len(fr), 1000):
            idx = fr[s][long_[s]]
            if not idx.size:
                continue
            f = np.asarray(t.getcol_rows("FLAG", idx))[..., (0, 3)]
            fr_ = np.asarray(t.getcol_rows("FLAG_ROW", idx))
            ok = ~(f | fr_[:, None, None])
            aa1 = np.asarray(t.getcol_rows("ANTENNA1", idx))
            aa2 = np.asarray(t.getcol_rows("ANTENNA2", idx))
            for a in np.unique(np.concatenate([aa1, aa2])):
                sel = (aa1 == a) | (aa2 == a)
                out[a] |= ok[sel].any(0)
    return out


def arm(case, name):
    t_0 = time.perf_counter()
    d = O / case
    ms = d / f"arm-{name}.ms"
    rows = Rows(ms)
    interp = "nearest" if name == "near" else "linear"
    T = [tab(d / "truth-s0f" / n) for n in ("K", "G", "B")]
    A = ms.parent / f"{ms.name}.rang-run" / "calibrate"
    prim = rows.flag(K / "src.ms")
    own = rows.flag(ms)
    tc, tf = rows.composite(T)
    bnd = rows.bound(T[0])
    out = {"case": case, "arm": name, "interp": interp}
    summ = json.loads((A / "summary.json").read_text())
    out["steps"] = {s["name"]: ([{k: v for k, v in x.items() if k in ("iterations", "converged_fraction", "used_alternate_refant", "flagged_fraction")}
                                 for x in s.get("solutions", [])] or
                                {"flagged_before": s.get("flagged", {}).get("flagged_before"),
                                 "flagged_after": s.get("flagged", {}).get("flagged_after")})
                    for s in summ["steps"]}  # fmt: skip
    comp = {}
    for tg, nn in (("KGB0", NAMES0), ("KGB1", NAMES1)):
        a, fa = rows.composite([tab(A / x) for x in nn], interp)
        comp[tg] = {"primary": rel(a, fa, tc, tf, prim, rows, bnd),
                    "own_flags": rel(a, fa, tc, tf, own, rows, bnd)}  # fmt: skip
        comp[tg]["_a"] = (a, fa)
    out["against_truth"] = {
        k: {kk: vv for kk, vv in v.items() if kk != "_a"} for k, v in comp.items()
    }
    out["residual"] = {"pass0_primary": residual(rows, ms, A, NAMES0, prim, interp),
                       "pass1_own": residual(rows, ms, A, NAMES1, own, interp),
                       "pass1_primary": residual(rows, ms, A, NAMES1, prim, interp)}  # fmt: skip
    out["k_error_ns"] = {n: k_error(tab(A / n), T[0], rows.ref) for n in ("K0", "K1")}
    # T6: truth's K with the arm's G0, B0
    a, fa = rows.composite([T[0], tab(A / "G0"), tab(A / "B0")], interp)
    out["T6 truthK_armG0B0"] = rel(a, fa, tc, tf, prim, rows, bnd)
    # T6 per term: each of the arm's pass-0 terms alone swapped into truth
    for n, i in (("K0", 0), ("G0", 1), ("B0", 2)):
        tl = list(T)
        tl[i] = tab(A / n)
        a, fa = rows.composite(tl, interp)
        out[f"T6 truth_with_arm_{n}"] = rel(a, fa, tc, tf, prim, rows, bnd)
    # T4: B0 channels solved (data on a > 150 m baseline) for both antennas
    sv = solvable(rows, K / "src.ms")
    both = sv[rows.a1] & sv[rows.a2]  # (row, chan, hand)
    a0, fa0 = comp["KGB0"]["_a"]
    out["T4 KGB0 both_B0_channels_solved"] = rel(
        a0, fa0, tc, tf, prim | ~both, rows, bnd
    )
    out["T4 cells_with_a_filled_channel"] = int((~prim & ~both).sum())
    # T5: flagged solutions of the 15 antennas
    ants = sorted(set(rows.a1) | set(rows.a2))
    flagged = {}
    bad0, bad1 = set(), set()
    for n in ("K0", "G0", "B0", "K1", "G1", "B1"):
        t = tab(A / n)
        a_ = t.column("ANTENNA1")
        f = t.flags
        if n[0] == "B":
            per = {
                int(x): int((f[a_ == x][0] & sv[x]).sum()) for x in ants
            }  # flagged where solvable
        else:
            per = {int(x): int(f[a_ == x].sum()) for x in ants}
        flagged[n] = {k: v for k, v in per.items() if v}
        for k, v in per.items():
            if v:
                (bad0 if n.endswith("0") else bad1).add(k)
    out["T5 flagged_solutions"] = flagged
    for tg, bad in (("KGB0", bad0), ("KGB1", bad1)):
        a, fa = comp[tg]["_a"]
        m = np.isin(rows.a1, list(bad)) | np.isin(rows.a2, list(bad))
        out[f"T5 {tg} without_flagged_antennas"] = {
            "antennas": sorted(bad),
            **rel(a, fa, tc, tf, prim | m[:, None, None], rows, bnd),
        }
    # T7: refant in every table, alternate refant
    refs = {}
    for n in ("K0", "G0", "B0", "K1", "G1", "B1"):
        t = tab(A / n)
        a_ = t.column("ANTENNA1")
        refs[n] = {"refant_rows_flagged": int(t.flags[a_ == rows.ref].any(axis=(1, 2)).sum()),
                   "ANTENNA2": t.reference_antenna}  # fmt: skip
    out["T7 refant"] = refs
    # controls C-S and T7 (on the primary cells)
    out["controls"] = controls(rows, T, tc, tf, prim, bnd)
    out["seconds"] = time.perf_counter() - t_0
    write(O / f"score-arm-{case}-{name}.json", out)
    show = {
        "KGB0 primary": out["against_truth"]["KGB0"]["primary"]["all"].get("median"),
        "KGB1 primary": out["against_truth"]["KGB1"]["primary"]["all"].get("median"),
        "KGB0 own": out["against_truth"]["KGB0"]["own_flags"]["all"].get("median"),
        "KGB1 own": out["against_truth"]["KGB1"]["own_flags"]["all"].get("median"),
        "res0": out["residual"]["pass0_primary"]["all"].get("median"),
        "res1": out["residual"]["pass1_own"]["all"].get("median"),
        "K0 err": out["k_error_ns"]["K0"]["all"].get("median"),
    }
    print(json.dumps(show, indent=1))
    return 0


def controls(rows, T, tc, tf, mask, bnd):
    out = {}
    out["null truth_vs_truth"] = rel(tc, tf, tc, tf, mask, rows)["all"]
    rng = np.random.default_rng(20261117)
    # positive: one antenna's G x (1 + 1e-4)
    g = deepcopy(T[1])
    a_ = g.column("ANTENNA1")
    x = [a for a in sorted(set(rows.a1)) if a != rows.ref][1]
    g.main["CPARAM"] = [np.asarray(c) * np.complex64(1 + 1e-4) if a == x else np.asarray(c)
                        for c, a in zip(g.main["CPARAM"], a_)]  # fmt: skip
    a, fa = rows.composite([T[0], g, T[2]])
    on = (rows.a1 == x) | (rows.a2 == x)
    r_on = rel(a[on], fa[on], tc[on], tf[on], mask[on], _Sub(rows, on))["all"]
    r_off = rel(a[~on], fa[~on], tc[~on], tf[~on], mask[~on], _Sub(rows, ~on))["all"]
    out["positive G(ant %d) x (1+1e-4): on, off" % x] = [r_on, r_off]
    # T7: common phase and common delay
    g = deepcopy(T[1])
    ph = np.complex64(np.exp(1j * rng.uniform(-np.pi, np.pi)))
    g.main["CPARAM"] = [np.asarray(c) * ph for c in g.main["CPARAM"]]
    k = deepcopy(T[0])
    dt = np.float32(rng.uniform(-5, 5))
    k.main["FPARAM"] = [np.asarray(c) + dt for c in k.main["FPARAM"]]
    a, fa = rows.composite([k, g, T[2]])
    out[f"T7 common phase and delay {dt:.3f} ns"] = rel(a, fa, tc, tf, mask, rows)[
        "all"
    ]
    g = deepcopy(T[1])
    phs = {
        int(x): np.complex64(np.exp(1j * 1e-3 * rng.choice([-1, 1]))) for x in set(a_)
    }
    g.main["CPARAM"] = [
        np.asarray(c) * phs[int(a)] for c, a in zip(g.main["CPARAM"], a_)
    ]
    a, fa = rows.composite([T[0], g, T[2]])
    out["T7 per-antenna phase +-1e-3 rad (not blind)"] = rel(a, fa, tc, tf, mask, rows)[
        "all"
    ]
    return out


class _Sub:
    def __init__(self, rows, sel):
        self.a1, self.a2 = rows.a1[sel], rows.a2[sel]


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    fn = {"r": r, "t0": t0, "t1": t1, "arm": arm}.get(step)
    if not fn:
        sys.exit(__doc__)
    sys.exit(fn(*args))
