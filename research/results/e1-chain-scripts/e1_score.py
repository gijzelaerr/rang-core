"""E1's scorer (research/e1-chain.md, section 4): every frozen measure of one
run, written to RUN/result.json.

    python e1_score.py chain RUN [--tricolour TRI_RUN] [--version full]
    python e1_score.py twin RUN [--version small]

`chain` scores the m32 run (flags, terms, image, residual, polarisation,
self-calibration); `twin` the noise-free tier on the small twin (terms only).
Thermal standard errors are Fisher predictions on the truth (4.1): a gain
factor's relative error per real part has variance sigma^2 / sum |V|^2 over
the cells it is solved from, V the truth's corrupted visibility.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
sys.path.insert(0, str(HERE))

import e1_run
from rang import cal_apply, cal_selfcal, core_ms, simtruth
from rang.formats import caltable, flagversions

FCAL, XCAL, GCAL, TARGET = "J1939-6342", "3C286-SIM", "SIM-GCAL", "SIM-TARGET"
UVMIN = 150.0  # calibrate.uvrange '>150' (metres)
TWO_PI = 2 * math.pi
# 4.3: isolated points (no other component within 40" + its FWHM), from truth.json.
ISOLATED = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
            21, 22, 23, 24, 25, 26, 28, 29, 30, 32, 33, 34, 35, 37, 38, 39]  # fmt: skip
POLARISED = [0, 17, 23, 30, 37, 40]  # 4.5: p >= 1 %
CHUNK = 20160


def stats(x):
    x = np.asarray(x, float).ravel()
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0}
    return {"n": int(x.size), "median": float(np.median(x)),
            "p95": float(np.percentile(x, 95)), "max": float(x.max())}  # fmt: skip


def ratio_gate(e, s, complex_err):
    """4.1's class T: median(|e| / s) <= 3, with bias and scatter beside."""
    e = np.asarray(e)
    s = np.asarray(s, float)
    ok = np.isfinite(s) & (s > 0) & np.isfinite(np.abs(e))
    e, s = e[ok], s[ok]
    if not e.size:
        return {"n": 0, "pass": None}
    z = e / s
    out = {"n": int(e.size), "median_abs_over_s": float(np.median(np.abs(z))),
           "abs_e": stats(np.abs(e)), "s": stats(s)}  # fmt: skip
    if complex_err:
        out["bias_re"] = float(np.median(z.real))
        out["bias_im"] = float(np.median(z.imag))
        out["std_re"] = float(np.std(z.real))
        out["std_im"] = float(np.std(z.imag))
        out["rayleigh_median"] = 1.1774
    else:
        out["bias"] = float(np.median(z))
        out["std"] = float(np.std(z))
        out["halfnormal_median"] = 0.6745
    out["pass"] = bool(out["median_abs_over_s"] <= 3.0)
    return out


class Ctx:
    def __init__(self, run, version):
        self.run = Path(run)
        self.ms = e1_run.ms_of(self.run)
        self.rr = Path(str(self.ms) + ".rang-run")
        self.version = version
        self.d = simtruth.design(version)
        self.sigma = float(self.d.sigma)
        self.npz, self.truth = e1_run.load_truth(version)
        self.gauge = {k[len("gauge0_"):]: self.npz[k] for k in self.npz.files
                      if k.startswith("gauge0_")}  # fmt: skip
        self.tj = json.loads((e1_run.A1 / version / "truth.json").read_text())
        with core_ms.open_table(self.ms) as t:
            self.c = {n: t.getcol(n) for n in
                      ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "UVW")}  # fmt: skip
        with core_ms.open_table(self.ms / "SPECTRAL_WINDOW") as t:
            self.freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
        with core_ms.open_table(self.ms / "FIELD") as t:
            self.fields = {str(n): i for i, n in enumerate(t.getcol("NAME"))}
        self.nchan = len(self.freq)
        self.nant = len(self.d.antennas)
        self.a1 = self.c["ANTENNA1"].astype(np.int64)
        self.a2 = self.c["ANTENNA2"].astype(np.int64)
        self.tindex = e1_run.truth_index(self.c["TIME"], self.npz["time"])
        self.uvdist = np.hypot(self.c["UVW"][:, 0], self.c["UVW"][:, 1])
        self.versions = [n for n, _ in flagversions.versions(self.ms)]
        self.cal = self.npz["calibrator_stokes"]  # (field, chan, 4)

    def version_name(self, prefix):
        found = [n for n in self.versions if n.startswith(prefix)]
        return found[-1] if found else None

    def rows(self, name):
        return np.flatnonzero(self.c["FIELD_ID"] == self.fields[name])

    def table(self, name):
        return caltable.read(self.rr / "calibrate" / name)

    def jamp(self, rows, hand, selfcal=False):
        """|J_p||J_q| (row, chan) of the truth's diagonal for one hand."""
        b = np.abs(self.truth["bandpass"][..., hand])
        g = np.abs(self.truth["gain"][..., hand])
        t = self.tindex[rows]
        p, q = self.a1[rows], self.a2[rows]
        amp = b[p] * b[q] * (g[t, p] * g[t, q])[:, None]
        if selfcal:
            s = np.abs(self.truth["selfcal"])
            amp = amp * (s[t, p] * s[t, q])[:, None]
        return amp

    def fisher_gain(self, rows, flag_cells, model_amp, hand, keys, nkeys, per_chan):
        """sum |V|^2 per (key, antenna[, chan]) for a gain factor; keys per row."""
        v2 = (self.jamp(rows, hand) * model_amp) ** 2
        v2 = np.where(flag_cells, 0.0, v2)
        shape = (nkeys, self.nant, self.nchan) if per_chan else (nkeys, self.nant)
        acc = np.zeros(shape)
        add = v2 if per_chan else v2.sum(1)
        for ant in (self.a1[rows], self.a2[rows]):
            np.add.at(acc, (keys, ant), add)
        return acc


def cell_flags(ms, name, rows):
    """(row, chan) flags of version `name` (or FLAG when None) on `rows`."""
    lo, hi = int(rows[0]), int(rows[-1]) + 1
    if name is None:
        with core_ms.open_table(ms) as t:
            f = t.getcol("FLAG", lo, hi - lo)
    else:
        f = flagversions.load(ms, name, lo, hi - lo)[0]
    return f.any(-1)[rows - lo]


# -- 4.2 flags ---------------------------------------------------------------------


M32_MASK = Path(r"D:\rang\outputs\e1-20261109-02-data\a1-full-m32.rfi_mask.npz")


def score_flags(ctx, tricolour_run, src=M32_MASK):
    mask = np.load(src)
    assert mask["any"].shape[0] == len(ctx.c["TIME"])
    nchan = int(mask["nchan"])
    any_m = np.unpackbits(mask["any"], axis=1)[:, :nchan].astype(bool)
    a5 = np.unpackbits(mask["above_5sigma"], axis=1)[:, :nchan].astype(bool)
    after = ctx.version_name("rang_calibrate_")
    fl = flagversions.load(ctx.ms, after)[0]
    cell = fl.any(-1)
    out = {"version": after, "mask": str(src), "cells": int(cell.size),
           "above_5sigma": int(a5.sum()), "any": int(any_m.sum())}  # fmt: skip
    out["recall"] = float((cell & a5).sum() / a5.sum())
    out["false_positives"] = int((cell & ~any_m).sum())
    out["flagged"] = int(cell.sum())
    out["corr_consistent"] = bool(np.array_equal(fl.all(-1), cell))
    out["recall_pass"] = bool(out["recall"] >= 0.90)
    per = {}
    final = None
    with core_ms.open_table(ctx.ms) as t:
        final = t.getcol("FLAG").any(-1)
    applyv = ctx.version_name("rang_apply_")
    after_cal = flagversions.load(ctx.ms, applyv)[0].any(-1) if applyv else None
    for name, fid in ctx.fields.items():
        r = ctx.c["FIELD_ID"] == fid
        per[name] = {"after_flag": float(cell[r].mean()),
                     "after_calibrate": None if after_cal is None else float(after_cal[r].mean()),
                     "final": float(final[r].mean()),
                     "injected_any": float(any_m[r].mean()),
                     "injected_above_5sigma": float(a5[r].mean())}  # fmt: skip
    out["fractions"] = per
    if tricolour_run:
        tms = e1_run.ms_of(tricolour_run)
        with core_ms.open_table(tms) as t:
            tf = t.getcol("FLAG")
        tcell = tf.any(-1)
        out["tricolour"] = {
            "ms": str(tms),
            "flagged": int(tcell.sum()),
            "recall": float((tcell & a5).sum() / a5.sum()),
            "false_positives": int((tcell & ~any_m).sum()),
            "cells_differ": int((tcell != cell).sum()),
            "elements_differ": int((tf != fl).sum()),
        }
        agree = 1 - out["tricolour"]["cells_differ"] / cell.size
        out["tricolour"]["agree_fraction"] = float(agree)
        out["fp_equal"] = out["false_positives"] == out["tricolour"]["false_positives"]
        out["gate_3a_exact"] = out["tricolour"]["elements_differ"] == 0
        out["fp_pass"] = bool(out["fp_equal"] and out["gate_3a_exact"])
    else:
        out["fp_pass"] = None  # not checked
    return out


# -- 4.1 terms ---------------------------------------------------------------------


def k_term(ctx, twin):
    t = ctx.table("K")
    tau = t.params[:, 0, :].astype(float)  # ns
    flg = t.flags[:, 0, :]
    ant = t.column("ANTENNA1")
    times = t.column("TIME")
    truth = ctx.gauge["tau_ns"]
    rows_f = ctx.rows(FCAL)
    after = ctx.version_name("rang_calibrate_")
    fc = (
        cell_flags(ctx.ms, after, rows_f)
        if after
        else np.zeros((len(rows_f), ctx.nchan), bool)
    )
    scans = ctx.c["SCAN_NUMBER"][rows_f]
    e_all, s_all = [], []
    per = []
    for tm in np.unique(times):
        k = times == tm
        scan = int(t.column("SCAN_NUMBER")[k][0])
        rsel = scans == scan
        rows = rows_f[rsel]
        for h in range(2):
            good = ~flg[k, h]
            a = ant[k][good]
            v = tau[k, h][good]
            e = (v - v.mean()) - (truth[a, h] - truth[a, h].mean())
            # Fisher: I = (2 pi)^2 sum (nu - nubar)^2 |V|^2 / sigma^2 per antenna.
            amp = ctx.jamp(rows, h) * ctx.cal[0, :, 0][None]
            w = np.where(fc[rsel], 0.0, amp**2) / ctx.sigma**2
            s0 = np.zeros(ctx.nant)
            s1 = np.zeros(ctx.nant)
            s2 = np.zeros(ctx.nant)
            for an in (ctx.a1[rows], ctx.a2[rows]):
                np.add.at(s0, an, w.sum(1))
                np.add.at(s1, an, (w * ctx.freq).sum(1))
                np.add.at(s2, an, (w * ctx.freq**2).sum(1))
            info = TWO_PI**2 * (s2 - s1**2 / np.where(s0 > 0, s0, 1))
            s = 1e9 / np.sqrt(np.where(info > 0, info, np.nan))
            e_all.append(e)
            s_all.append(s[a])
            per.append({"scan": scan, "hand": h, "abs_e_ns": stats(np.abs(e))})
    e = np.concatenate(e_all)
    s = np.concatenate(s_all)
    out = {"per_solution": per}
    if twin:
        out["max_abs_e_ns"] = float(np.abs(e).max())
        out["pass"] = bool(out["max_abs_e_ns"] <= 1e-4)
    else:
        out.update(ratio_gate(e, s, False))
    return out


def composite(ctx, rows, tables, table_fields, interp):
    """J_p J_q* (row, chan, 2) of `tables` applied as `corrupt` to unit data,
    and its flags (cal_apply, as check_c2e.composite)."""
    ones = np.zeros((len(rows), ctx.nchan, 4), np.complex64)
    ones[..., 0] = ones[..., 3] = 1
    v, f = cal_apply.apply(
        ones, np.zeros(ones.shape, bool), ctx.c["TIME"][rows], ctx.a1[rows], ctx.a2[rows],
        ctx.freq, tables, interp=interp, direction="corrupt",
        table_fields=table_fields, nant=ctx.nant,
    )  # fmt: skip
    return v[..., (0, 3)].astype(np.complex128), f[..., (0, 3)]


def truth_product(ctx, rows, selfcal=False):
    truth = dict(ctx.truth)
    if not selfcal:
        truth["selfcal"] = np.ones_like(truth["selfcal"])
    r = simtruth.Rows(ctx.tindex[rows], ctx.a1[rows], ctx.a2[rows])
    gp, gq = simtruth.diagonal(truth, ctx.d, r)
    return gp * np.conj(gq)


def gain_variances(ctx):
    """4.1's v for B (per antenna, chan, hand; from J1939-6342) and F (per
    gain-calibrator scan, antenna, hand; from SIM-GCAL), relative, per real
    part."""
    after = ctx.version_name("rang_calibrate_")
    applyv = ctx.version_name("rang_apply_")
    rf = ctx.rows(FCAL)
    rf = rf[ctx.uvdist[rf] > UVMIN]
    ff = (
        cell_flags(ctx.ms, after, rf) if after else np.zeros((len(rf), ctx.nchan), bool)
    )
    vb = np.zeros((ctx.nant, ctx.nchan, 2))
    for h in range(2):
        acc = ctx.fisher_gain(rf, ff, ctx.cal[0, :, 0][None], h,
                              np.zeros(len(rf), int), 1, True)[0]  # fmt: skip
        vb[..., h] = ctx.sigma**2 / np.where(acc > 0, acc, np.nan)
    rg = ctx.rows(GCAL)
    rg = rg[ctx.uvdist[rg] > UVMIN]
    fg = (
        cell_flags(ctx.ms, applyv, rg)
        if applyv
        else np.zeros((len(rg), ctx.nchan), bool)
    )
    scans = ctx.c["SCAN_NUMBER"][rg]
    uniq = np.unique(scans)
    key = np.searchsorted(uniq, scans)
    vf = np.zeros((len(uniq), ctx.nant, 2))
    for h in range(2):
        acc = ctx.fisher_gain(rg, fg, ctx.cal[2, :, 0][None], h, key, len(uniq), False)
        vf[..., h] = ctx.sigma**2 / np.where(acc > 0, acc, np.nan)
    times = np.array([ctx.c["TIME"][rg][scans == s].mean() for s in uniq])
    return vb, vf, times


def interp_var(vf, times, t):
    """Variance at times t of a linear interpolation between scan solutions."""
    j = np.clip(np.searchsorted(times, t), 1, len(times) - 1)
    t1, t2 = times[j - 1], times[j]
    w = np.clip((t - t1) / (t2 - t1), 0.0, 1.0)
    return (1 - w)[:, None, None] ** 2 * vf[j - 1] + w[:, None, None] ** 2 * vf[j]


def composites(ctx, twin):
    K, G, B, F = (ctx.table(n) for n in ("K", "G", "B", "F"))
    fid = ctx.fields
    lin = ["linear"] * 3
    out = {}
    applyv = ctx.version_name("rang_apply_")
    vb, vf, ftimes = (None, None, None) if twin else gain_variances(ctx)
    # Gated: the target's 1GC composite K F B (gainfield fcal, gcal, fcal).
    rows_t = ctx.rows(TARGET)
    e_all, s_all = [], []
    for lo in range(0, len(rows_t), CHUNK):
        rows = rows_t[lo : lo + CHUNK]
        pc, pf = composite(ctx, rows, [K, F, B], [fid[FCAL], fid[GCAL], fid[FCAL]], lin)
        pt = truth_product(ctx, rows)
        fl = (
            cell_flags(ctx.ms, applyv, rows) if applyv else np.zeros(pf.shape[:2], bool)
        )
        ok = ~pf & ~fl[..., None]
        eps = pc / pt - 1
        if not twin:
            vt = interp_var(vf, ftimes, ctx.c["TIME"][rows])  # (row, ant, 2)
            n = np.arange(len(rows))
            s2 = (vb[ctx.a1[rows]] + vb[ctx.a2[rows]]
                  + vt[n, ctx.a1[rows]][:, None, :] + vt[n, ctx.a2[rows]][:, None, :])  # fmt: skip
            s_all.append(np.sqrt(s2)[ok])
        e_all.append(eps[ok])
    e = np.concatenate(e_all)
    tgt = {"abs_rel_error": stats(np.abs(e))}
    if twin:
        tgt["pass"] = bool(np.abs(e).max() <= 1e-5)
    else:
        tgt.update(ratio_gate(e, np.concatenate(s_all), True))
    out["target_1gc"] = tgt
    # Reported: the calibrator fields' own composites.
    gpol = ctx.table("Gpol")
    for name, tabs, flds in (
        (FCAL, [K, G, B], [fid[FCAL]] * 3),
        (GCAL, [K, F, B], [fid[FCAL], fid[GCAL], fid[FCAL]]),
        (XCAL, [K, G, B, gpol], [fid[FCAL]] * 3 + [fid[XCAL]]),
    ):
        rows = ctx.rows(name)
        pc, pf = composite(ctx, rows, tabs, flds, ["linear"] * len(tabs))
        pt = truth_product(ctx, rows)
        fl = (
            cell_flags(ctx.ms, applyv, rows) if applyv else np.zeros(pf.shape[:2], bool)
        )
        ok = ~pf & ~fl[..., None]
        out[name] = {"abs_rel_error": stats(np.abs(pc / pt - 1)[ok]), "reported": True}
    return out


def xcal_visibilities(ctx, rows):
    """|V_XY|^2 + |V_YX|^2 (row, chan) of the truth's corrupted polcal source."""
    r = simtruth.Rows(ctx.tindex[rows], ctx.a1[rows], ctx.a2[rows])
    m = simtruth.stokes_coherency(ctx.cal[1])[None].repeat(len(rows), 0)
    v = simtruth.corrupt(m, ctx.truth, ctx.d, r, ctx.npz["parallactic_angle"])
    return np.abs(v[..., 1]) ** 2 + np.abs(v[..., 2]) ** 2


def crosshand(ctx, twin):
    kc = ctx.table("Kcross")
    xf = ctx.table("Xf")
    nu0 = kc.k_reference_frequency(0)
    ktimes = kc.column("TIME")
    kscans = kc.column("SCAN_NUMBER")
    kv = kc.params[:, 0, 0].astype(float)
    kflag = kc.flags[:, 0, 0]
    xv = xf.params[:, :, 0].astype(np.complex128)
    xflag = xf.flags[:, :, 0]
    x_chain = np.array([xv[~xflag[:, c], c][0] if (~xflag[:, c]).any() else np.nan
                        for c in range(ctx.nchan)])  # fmt: skip
    truth_c = ctx.gauge["kcross"] * ctx.gauge["xf"]
    tau_eff = float(ctx.tj["gauge"]["tau_c_ns_casa_gauge"])
    # Fisher per scan and channel from the polcal source's cross hands.
    rows_x = ctx.rows(XCAL)
    rows_x = rows_x[ctx.uvdist[rows_x] > UVMIN]
    applyv = ctx.version_name("rang_apply_")
    after = ctx.version_name("rang_calibrate_")
    flg_name = after if after else None
    scans_x = ctx.c["SCAN_NUMBER"][rows_x]
    per_scan = {}
    a_total = np.zeros(ctx.nchan)
    for s in np.unique(scans_x):
        rows = rows_x[scans_x == s]
        fl = (
            cell_flags(ctx.ms, applyv, rows)
            if applyv
            else np.zeros((len(rows), ctx.nchan), bool)
        )
        a = np.where(fl, 0.0, xcal_visibilities(ctx, rows)).sum(0)  # (chan,)
        per_scan[int(s)] = a
        a_total += a
    del flg_name
    s_x = ctx.sigma / np.sqrt(np.where(a_total > 0, a_total, np.nan))  # Xf, rad
    e_comb, s_comb, e_k, s_k = [], [], [], []
    for tm in np.unique(ktimes):
        k = (ktimes == tm) & ~kflag
        if not k.any():
            continue
        scan = int(kscans[ktimes == tm][0])
        tau = float(np.median(kv[k]))
        a = per_scan[scan]
        w = a / ctx.sigma**2
        nub = (w * ctx.freq).sum() / w.sum()
        info = TWO_PI**2 * (w * (ctx.freq - nub) ** 2).sum()
        st = 1 / math.sqrt(info)  # s
        chain_c = np.exp(2j * math.pi * tau * 1e-9 * (ctx.freq - nu0)) * x_chain
        e_comb.append(np.angle(chain_c / truth_c))
        s_comb.append(np.sqrt(s_x**2 + (TWO_PI * (ctx.freq - nub) * st) ** 2))
        e_k.append(tau - tau_eff)
        s_k.append(st * 1e9)
    e_comb = np.concatenate(e_comb)
    s_comb = np.concatenate(s_comb)
    e_x = np.angle(x_chain / ctx.gauge["xf"])
    out = {"kcross_ns": [float(v) for v in e_k], "kcross_truth_eff_ns": tau_eff,
           "kcross_reference_hz": nu0}  # fmt: skip
    if twin:
        out["combined"] = {"max_abs_rad": float(np.nanmax(np.abs(e_comb)))}
        out["combined"]["pass"] = bool(out["combined"]["max_abs_rad"] <= 1e-5)
        out["kcross"] = {"max_abs_ns": float(np.max(np.abs(e_k))), "reported": True}
        out["xf"] = {"max_abs_rad": float(np.nanmax(np.abs(e_x))), "reported": True}
    else:
        out["combined"] = ratio_gate(e_comb, s_comb, False)
        out["kcross"] = ratio_gate(np.array(e_k), np.array(s_k), False)
        out["xf"] = ratio_gate(e_x, s_x, False)
    return out


def df_term(ctx, twin):
    t = ctx.table("Df")
    d = t.params.astype(np.complex128)  # (row, chan, 2)
    flg = t.flags
    ant = t.column("ANTENNA1")
    e = d - ctx.gauge["leakage"][ant]
    ok = ~flg
    if twin:
        out = {"max_abs": float(np.abs(e[ok]).max())}
        out["pass"] = bool(out["max_abs"] <= 1e-5)
        return out
    rows = ctx.rows(FCAL)
    rows = rows[ctx.uvdist[rows] > UVMIN]
    applyv = ctx.version_name("rang_apply_")
    fl = (
        cell_flags(ctx.ms, applyv, rows)
        if applyv
        else np.zeros((len(rows), ctx.nchan), bool)
    )
    amp = np.sqrt(ctx.jamp(rows, 0) * ctx.jamp(rows, 1)) * ctx.cal[0, :, 0][None]
    v2 = np.where(fl, 0.0, amp**2)
    acc = np.zeros((ctx.nant, ctx.nchan))
    for an in (ctx.a1[rows], ctx.a2[rows]):
        np.add.at(acc, an, v2)
    s = ctx.sigma / np.sqrt(np.where(acc > 0, acc, np.nan))  # per real part
    s = np.repeat(s[ant][..., None], 2, -1)
    return ratio_gate(e[ok], s[ok], True)


def fluxes(ctx):
    path = ctx.rr / "calibrate" / "summary.json"
    s = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for step in s.get("steps", []):
        if step.get("type") == "F":
            out = {k: v for k, v in step.items() if k in ("fluxscale", "fluxd", "flux")}
    nu = ctx.freq
    out["truth_gcal_jy_at_1284mhz"] = float(np.interp(1.284e9, nu, ctx.cal[2, :, 0]))
    return out


# -- 4.3, 4.4 image and residual ----------------------------------------------------


def _beam_sigma(h):
    k = 1 / (2 * math.sqrt(2 * math.log(2)))
    pix = abs(h["CDELT2"])
    return h["BMAJ"] * k / pix, h["BMIN"] * k / pix, math.radians(h["BPA"])


def fit_point(img, h, wcs, ra, dec):
    from scipy.optimize import least_squares

    x0, y0 = wcs.celestial.world_to_pixel_values(ra, dec)
    ix, iy = round(float(x0)), round(float(y0))
    cut = img[iy - 4 : iy + 5, ix - 4 : ix + 5].astype(float)
    yy, xx = np.mgrid[iy - 4 : iy + 5, ix - 4 : ix + 5]
    smaj, smin, pa = _beam_sigma(h)

    def model(p):
        a, dx, dy = p
        u = (xx - dx) * -math.sin(pa) + (yy - dy) * math.cos(pa)
        w = (xx - dx) * math.cos(pa) + (yy - dy) * math.sin(pa)
        return a * np.exp(-(u**2) / (2 * smaj**2) - w**2 / (2 * smin**2))

    r = least_squares(lambda p: (model(p) - cut).ravel(),
                      [float(img[iy, ix]), float(x0), float(y0)])  # fmt: skip
    a, fx, fy = r.x
    wra, wdec = wcs.celestial.pixel_to_world_values(fx, fy)
    return float(a), float(wra), float(wdec)


def _open(path):
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(path) as f:
        h = f[0].header
        data = np.asarray(f[0].data, float)
    return data.reshape(data.shape[-2:]), h, WCS(h)


def offsource(images, bmaj_pix):
    from scipy import ndimage

    mean = np.mean(images, axis=0)
    sig = 1.4826 * np.median(np.abs(mean - np.median(mean)))
    mask = mean > 5 * sig
    r = math.ceil(2 * bmaj_pix)
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    mask = ndimage.binary_dilation(mask, structure=(xx**2 + yy**2) <= r * r)
    return mask, float(sig)


def score_image(ctx, chain_dir, control_dir, channels_out=8):
    from astropy.coordinates import SkyCoord

    comps = ctx.tj["target_components"]
    mfs = {k: _open(Path(p) / "image-MFS-image.fits")
           for k, p in (("chain", chain_dir), ("control", control_dir))}  # fmt: skip
    h = mfs["control"][1]
    bmaj_pix = h["BMAJ"] / abs(h["CDELT2"])
    mask, sig_mean = offsource([mfs["chain"][0], mfs["control"][0]], bmaj_pix)
    rms = {k: float(np.sqrt(np.mean(v[0][~mask] ** 2))) for k, v in mfs.items()}
    out = {"offsource_mask_fraction": float(mask.mean()), "mean_image_sigma": sig_mean,
           "rms": rms, "beam_arcsec": {k: [v[1]["BMAJ"] * 3600, v[1]["BMIN"] * 3600]
                                       for k, v in mfs.items()}}  # fmt: skip
    out["residual"] = {"ratio": rms["chain"] / rms["control"]}
    out["residual"]["pass"] = bool(out["residual"]["ratio"] <= 1.1)
    group = ctx.nchan // channels_out
    sel = []
    for k in ISOLATED:
        c = comps[k]
        s_nu = c["flux"] * (ctx.freq / c["ref_freq_hz"]) ** c["alpha"]
        s_c = s_nu.reshape(channels_out, group).mean(1)
        if s_c.mean() >= 50 * rms["control"]:
            sel.append((k, s_c))
    out["sources"] = [k for k, _ in sel]
    for arm, where in (("chain", chain_dir), ("control", control_dir)):
        chans = [
            _open(Path(where) / f"image-{c:04d}-image.fits")
            for c in range(channels_out)
        ]
        img, hh, w = mfs[arm]
        bmaj = hh["BMAJ"] * 3600
        rec = []
        for k, s_c in sel:
            c = comps[k]
            f = [
                fit_point(ci, hi, wi, c["ra_deg"], c["dec_deg"])[0]
                for ci, hi, wi in chans
            ]
            _, ra, dec = fit_point(img, hh, w, c["ra_deg"], c["dec_deg"])
            sep = SkyCoord(ra, dec, unit="deg").separation(
                SkyCoord(c["ra_deg"], c["dec_deg"], unit="deg")).arcsec  # fmt: skip
            rec.append({"index": k, "flux_jy": c["flux"], "ratio": float(sum(f) / s_c.sum()),
                        "offset_beam": float(sep / bmaj)})  # fmt: skip
        r = np.array([x["ratio"] for x in rec])
        off = np.array([x["offset_beam"] for x in rec])
        med = float(np.median(r))
        scat = float(1.4826 * np.median(np.abs(r - med)))
        res = {"n": len(rec), "median_ratio": med, "robust_scatter": scat,
               "offset_beam": stats(off), "per_source": rec}  # fmt: skip
        res["pass"] = bool(abs(med - 1) <= 0.01 and scat <= 0.01 and off.max() <= 0.1)
        res["validates_scorer"] = bool(abs(med - 1) <= 0.005 and scat <= 0.005)
        out[arm] = res
    rc = {x["index"]: x["ratio"] for x in out["control"]["per_source"]}
    q = np.array([x["ratio"] / rc[x["index"]] for x in out["chain"]["per_source"]])
    out["chain_over_control_secondary"] = {"median": float(np.median(q)),
                                           "robust_scatter": float(1.4826 * np.median(np.abs(q - np.median(q))))}  # fmt: skip
    return out


# -- 4.5, 4.6 polarisation and self-calibration (one pass over the target) ----------


def _stokes4(v):
    return ((v[..., 0] + v[..., 3]) / 2, (v[..., 0] - v[..., 3]) / 2,
            (v[..., 1] + v[..., 2]) / 2, (v[..., 1] - v[..., 2]) / 2j)  # fmt: skip


def target_pass(ctx, columns, leak_points):
    comps = ctx.tj["target_components"]
    fit = POLARISED + leak_points
    rows_t = ctx.rows(TARGET)
    selfv = ctx.version_name("rang_selfcal_")
    blocks = ctx.npz["raw_selfcal_block"]
    ub = np.unique(blocks[ctx.tindex[rows_t]])
    nb = len(ub)
    fisher = np.zeros((nb, ctx.nant, 2))
    acc = {
        col: {k: np.zeros((5, ctx.nchan), np.complex128) for k in fit}
        for col in columns
    }
    with core_ms.open_table(ctx.ms) as t:
        for lo in range(0, len(rows_t), CHUNK):
            rows = rows_t[lo : lo + CHUNK]
            r0, n = int(rows[0]), len(rows)
            uvw = ctx.c["UVW"][rows]
            full = simtruth.target_coherency(uvw, ctx.freq, comps)
            flag = t.getcol("FLAG", r0, n).any(-1)
            ok = ~flag
            sfl = flagversions.load(ctx.ms, selfv, r0, n)[0].any(-1) if selfv else flag
            key = np.searchsorted(ub, blocks[ctx.tindex[rows]])
            for h, corr in ((0, 0), (1, 3)):
                v2 = (np.abs(full[..., corr]) * ctx.jamp(rows, h, selfcal=True)) ** 2
                v2 = np.where(sfl, 0.0, v2).sum(1)
                for an in (ctx.a1[rows], ctx.a2[rows]):
                    np.add.at(fisher[..., h], (key, an), v2)
            data = {col: t.getcol(col, r0, n).astype(np.complex128) for col in columns}
            for k in fit:
                tk = simtruth.target_coherency(uvw, ctx.freq, [comps[k]])
                shape = (tk[..., 0] + tk[..., 3]) / 2
                w = np.where(ok, np.abs(shape) ** 2, 0.0)
                for col in columns:
                    resid = data[col] - full + tk
                    a = acc[col][k]
                    a[0] += w.sum(0)
                    for j, s in enumerate(_stokes4(resid)):
                        a[j + 1] += np.where(ok, np.conj(shape) * s, 0).sum(0)
    lam2 = (simtruth.C / ctx.freq) ** 2
    pol = {}
    for col in columns:
        pol[col] = {}
        for k in fit:
            a = acc[col][k]
            den = a[0].real
            good = den > 0
            a_i, a_q, a_u, a_v = (
                (a[j + 1] / np.where(good, den, 1)).real for j in range(4)
            )
            c = comps[k]
            wt = den[good]
            i_mean = float((wt * a_i[good]).sum() / wt.sum())
            rec = {
                "index": k,
                "flux_jy": c["flux"],
                "p_true": c["p"],
                "i_scale": i_mean,
            }
            if c["p"] > 0:
                chi_t = math.radians(c["chi0_deg"]) + c["rm"] * lam2
                z = (a_q + 1j * a_u) * np.exp(-2j * chi_t)
                r = (wt * z[good]).sum() / wt.sum()
                var = (wt**2 * np.abs(z[good] - r) ** 2).sum() / wt.sum() ** 2
                rec.update(p_meas=float(abs(r) / i_mean), dp=float(abs(r) / i_mean - c["p"]),
                           dchi_deg=float(np.degrees(np.angle(r)) / 2),
                           snr=float(abs(r) / math.sqrt(var)),
                           sigma_chi_deg=float(np.degrees(math.sqrt(var) / (2 * abs(r)))))  # fmt: skip
            else:
                q, u, v = ((wt * x[good]).sum() / wt.sum() for x in (a_q, a_u, a_v))
                rec.update(q=float(q / i_mean), u=float(u / i_mean), v=float(v / i_mean),
                           leak=float(math.sqrt(q * q + u * u + v * v) / i_mean))  # fmt: skip
            pol[col][k] = rec
    return pol, fisher, ub


def point_field(ctx, name, column):
    rows = ctx.rows(name)
    lo, hi = int(rows[0]), int(rows[-1]) + 1
    with core_ms.open_table(ctx.ms) as t:
        v = t.getcol(column, lo, hi - lo)[rows - lo].astype(np.complex128)
        f = t.getcol("FLAG", lo, hi - lo)[rows - lo].any(-1)
    ok = ~f
    n = ok.sum(0)
    mean = [np.where(ok, s, 0).sum(0) / np.maximum(n, 1) for s in _stokes4(v)]
    i, q, u, vv = (m.real for m in mean)
    return i, q, u, vv, n


def score_pol(ctx, pol):
    out = {"columns": {}}
    ctrl = pol.get(e1_run.CONTROL_COLUMN, {})
    gated = [k for k in POLARISED if k in ctrl and ctrl[k].get("snr", 0) >= 50]
    out["gated_polarised"] = gated
    for col, recs in pol.items():
        o = {"components": list(recs.values())}
        pp = [recs[k] for k in gated]
        o["polarised_pass"] = (None if not pp else
                               bool(all(abs(r["dp"]) <= 0.002 and abs(r["dchi_deg"]) <= 1.0
                                        for r in pp)))  # fmt: skip
        lp = [r for r in recs.values() if r["p_true"] == 0]
        o["leak_targets_pass"] = (
            bool(all(r["leak"] <= 1e-3 for r in lp)) if lp else None
        )
        out["columns"][col] = o
    i, q, u, v, n = point_field(ctx, GCAL, "CORRECTED_DATA")
    good = n > 0
    leak = np.sqrt(q**2 + u**2 + v**2) / np.where(i != 0, i, 1)
    out["gcal_leak"] = stats(leak[good])
    out["gcal_leak"]["pass"] = bool(np.median(leak[good]) <= 1e-3)
    i, q, u, v, n = point_field(ctx, XCAL, "CORRECTED_DATA")
    good = n > 0
    p = np.hypot(q, u) / np.where(i != 0, i, 1)
    chi = np.degrees(np.arctan2(u, q)) / 2
    out["xcal_reported"] = {"p_median": float(np.median(p[good])),
                            "abs_chi_minus_33": stats(np.abs(chi[good] - 33.0))}  # fmt: skip
    i, q, u, v, n = point_field(ctx, FCAL, "CORRECTED_DATA")
    good = n > 0
    out["fcal_leak_reported"] = stats(
        (np.sqrt(q**2 + u**2 + v**2) / np.where(i != 0, i, 1))[good]
    )
    tg = out["columns"].get("CORRECTED_DATA", {})
    out["pass"] = bool(tg.get("polarised_pass") is not False
                       and tg.get("leak_targets_pass") is not False
                       and out["gcal_leak"]["pass"])  # fmt: skip
    return out


def score_selfcal(ctx, fisher, ub):
    s_true = ctx.truth["selfcal"]
    blocks = ctx.npz["raw_selfcal_block"]
    ttime = ctx.npz["time"]
    tgt = np.flatnonzero(ctx.npz["field"] == ctx.fields[TARGET])
    out = {}
    base = ctx.rr / "selfcal" / TARGET
    for rnd, name in ((1, "Sp"), (2, "Sa")):
        store = base / f"round-{rnd}" / "gains.qc"
        g, f, gt, _, _ = cal_selfcal.read_store(store, name)
        g = g[:, 0]  # (bin, ant, hand)
        f = f[:, 0]
        e_all, s_all, ph, amp = [], [], [], []
        for b in range(len(gt)):
            ii = tgt[np.argmin(np.abs(ttime[tgt] - gt[b]))]
            blk = blocks[ii]
            kb = int(np.searchsorted(ub, blk))
            st = s_true[ii]
            for h in range(2):
                okp = ~f[b]
                p, q = np.triu_indices(ctx.nant, 1)
                sel = okp[p] & okp[q]
                p, q = p[sel], q[sel]
                pc = g[b, p, h] * np.conj(g[b, q, h])
                ptr = st[p] * np.conj(st[q])
                v = ctx.sigma**2 / fisher[kb, :, h]
                s = np.sqrt(v[p] + v[q])
                if rnd == 1:
                    e = np.angle(pc / ptr)
                else:
                    e = pc / ptr - 1
                e_all.append(e)
                s_all.append(s)
                ph.append(np.degrees(np.abs(np.angle(pc / ptr))))
                amp.append(np.abs(np.abs(pc) / np.abs(ptr) - 1))
        e = np.concatenate(e_all)
        s = np.concatenate(s_all)
        o = ratio_gate(e, s, rnd == 2)
        o["phase_deg"] = stats(np.concatenate(ph))
        o["amp_rel"] = stats(np.concatenate(amp))
        o["uncorrected_amp_median"] = float(np.median(np.abs(np.abs(s_true[tgt]) - 1)))
        out[f"round{rnd}_{name}"] = o
    r1, r2 = out["round1_Sp"], out["round2_Sa"]
    out["c5_t2_reported"] = {
        "round1_phase": r1["phase_deg"]["median"] <= 1.0
        and r1["phase_deg"]["p95"] <= 3.0,
        "round2_phase": r2["phase_deg"]["median"] <= 0.5
        and r2["phase_deg"]["p95"] <= 1.5,
        "round2_amp": r2["amp_rel"]["median"] <= 0.01 and r2["amp_rel"]["p95"] <= 0.03,
    }
    out["pass"] = bool(r1["pass"] and r2["pass"])
    return out


def leak_points(ctx):
    comps = ctx.tj["target_components"]
    return [k for k in ISOLATED if comps[k]["p"] == 0 and comps[k]["flux"] >= 0.05]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("chain", "twin"))
    p.add_argument("run")
    p.add_argument("--version", default=None)
    p.add_argument("--tricolour", default=None)
    p.add_argument("--only", default="")
    p.add_argument("--mask", default=str(M32_MASK))
    p.add_argument("--quiet", action="store_true", help="execution test: no output")
    a = p.parse_args(argv)
    twin = a.mode == "twin"
    ctx = Ctx(a.run, a.version or ("small" if twin else "full"))
    only = set(a.only.split(",")) - {""}
    want = lambda k: not only or k in only
    path = Path(a.run) / ("result-twin.json" if twin else "result.json")
    res = json.loads(path.read_text(encoding="utf-8")) if path.exists() and only else {}
    res.update({"mode": a.mode, "version": ctx.version, "ms": str(ctx.ms)})
    terms = res.setdefault("terms", {})
    if want("k"):
        terms["K"] = k_term(ctx, twin)
    if want("composite"):
        terms["composite"] = composites(ctx, twin)
    if want("crosshand"):
        terms["crosshand"] = crosshand(ctx, twin)
    if want("df"):
        terms["Df"] = df_term(ctx, twin)
    if want("flux"):
        terms["F"] = fluxes(ctx)
    if not twin:
        if want("flags"):
            res["flags"] = score_flags(ctx, a.tricolour, Path(a.mask))
        if want("image"):
            res["image"] = score_image(
                ctx,
                ctx.rr / "selfcal" / TARGET / "final",
                Path(a.run) / "control" / "image",
            )
        if want("target"):
            cols = ["CORRECTED_DATA", "CORRECTED_1GC", e1_run.CONTROL_COLUMN]
            pol, fisher, ub = target_pass(ctx, cols, leak_points(ctx))
            res["polarisation"] = score_pol(ctx, pol)
            res["selfcal"] = score_selfcal(ctx, fisher, ub)
    e1_run.write_json(path, res)
    if not a.quiet:
        print(json.dumps(res, indent=1, default=e1_run._default)[:20000])


if __name__ == "__main__":
    main()
