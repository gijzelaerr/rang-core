# SPDX-License-Identifier: MIT
"""F5: the fourth supervised RFI flagger (research/f5-flagger.md).

F3's fifteen planes, F4's eight spectral planes and ten block planes from
order-independent median-polish factorisations per antenna (section 2c:
log amplitude per 2-dump × 8-channel block; section 2d: noise variance from
time and channel differences per time block × 32 channels), the network N5
with a linear stem (section 2e, `rang.f5net`), the fallback W4 (section 3)
and the gates' helpers (section 8). Inference in Rust is
`rang._core.f5flag_logits` (`core/src/f5flag.rs`); the NumPy reference
`features_numpy` is for parity on small scans. Data roles and guards are
F4's (`rang.f4flag`): F5's held-out sets are F4's, unread.

Copyright (C) 2026 Gijs Molenaar. Licensed under the MIT License;
see `LICENSES/MIT.txt`.
"""

import json
import math

import numpy as np

from . import core
from . import f3flag as f3
from . import f4flag as f4

# F6 variants (core/src/f5flag.rs): +10 per-antenna scale, +20 one-step factorisation.
LEVEL_INPUTS = {
    b + 10 * k: n
    for k in (0, 1, 2, 3, 4, 6, 7)  # F7 D9: 60s and 70s (core/src/f5flag.rs dead_zone)
    for b, n in ((0, 33), (1, 29), (2, 21))
}
CELL_PLANES = 14
SPEC_PLANES = 8
AMP_PLANES = 6
VAR_PLANES = 4
AMP_DF = 8
VAR_DF = 32
POLISH_ITERS = 5
MIN_VAR = 64
HUBER_K = 1.345
MAD = 1.4826
FAMILIES = ((0, 3), (1, 2))
KAPPAS = (3.0, 4.0, 5.0, 6.0, 8.0)
DEGREE = None  # fixed at Stage 2 (section 2c step 3), recorded in the weights header

load = f4.load
real_sets = f4.real_sets


def nplanes(level):
    return LEVEL_INPUTS[level]


def weight_count(level):
    from . import f5net

    return f5net.weight_count(nplanes(level), True)


# -- the Rust kernel ----------------------------------------------------------------


def _call(name, scan, flagged, level, degree, *extra, data=None):
    args = f3._args(scan, flagged, data)
    code = getattr(core.extension(), name)(*args, int(level), int(degree), *extra)
    if code:
        raise RuntimeError(f"{name} failed with code {code}")


def rust_features(scan, flagged, select, level=0, degree=2, data=None):
    """(nsel, nt, nc, nplanes(level)) float32 planes of the baselines `select`."""
    args = f3._args(scan, flagged, data)
    select = np.ascontiguousarray(select, np.uint32)
    out = np.empty((len(select), args[2], args[0], nplanes(level)), np.float32)
    _call("f5flag_features", scan, flagged, level, degree, select, out, data=data)
    return out


def rust_logits(scan, flagged, weights, level=0, degree=2, data=None):
    args = f3._args(scan, flagged, data)
    out = np.empty((len(scan["times"]), args[0]), np.float32)
    w = np.require(weights, np.float32, ["C", "A"])
    _call("f5flag_logits", scan, flagged, level, degree, w, out, data=data)
    return out


def rust_anomaly(scan, flagged, level=0, degree=2, data=None):
    args = f3._args(scan, flagged, data)
    out = np.empty((len(scan["times"]), args[0]), np.float32)
    _call("f5flag_anomaly", scan, flagged, level, degree, out, data=data)
    return out


def rust_antenna(scan, flagged, level=0, degree=2, data=None):
    """Per-antenna block quantities: z, q (nta, nja, 2, nant); tt, tf (ntv,
    njv, nant), float64 (NaN without 2d)."""
    args = f3._args(scan, flagged, data)
    nta, nja, ntv, njv = core.extension().f5flag_antenna_shape(args[2], args[0])
    nant = args[3]
    z = np.empty((nta, nja, 2, nant))
    q = np.empty_like(z)
    tt = np.empty((ntv, njv, nant))
    tf = np.empty_like(tt)
    _call("f5flag_antenna", scan, flagged, level, degree, z, q, tt, tf, data=data)
    return {"z": z, "q": q, "tt": tt, "tf": tf}


def n5_flags(scan, w3, weights, tau, level=0, degree=2, data=None):
    logit = rust_logits(scan, w3, weights, level, degree, data)
    return w3 | (logit > tau), logit


def rust_logits_anomaly(scan, flagged, weights, level=0, degree=2, data=None):
    """Logits and W4's anomaly from one preparation pass."""
    args = f3._args(scan, flagged, data)
    logit = np.empty((len(scan["times"]), args[0]), np.float32)
    anom = np.empty_like(logit)
    w = np.require(weights, np.float32, ["C", "A"])
    _call(
        "f5flag_logits_anomaly", scan, flagged, level, degree, w, logit, anom, data=data
    )
    return logit, anom


def method_flags(scan, w3, weights, tau, kappa=None, level=0, degree=2, data=None):
    """The method (section 3): N5 inside W3, OR W4 at kappa when kappa is set."""
    if kappa is None:
        return n5_flags(scan, w3, weights, tau, level, degree, data)[0]
    logit, anom = rust_logits_anomaly(scan, w3, weights, level, degree, data)
    with np.errstate(invalid="ignore"):
        return w3 | (logit > tau) | (anom > kappa)


def w4_flags(scan, w3, kappa, level=0, degree=2, data=None, anomaly=None):
    """W4 (section 3): cross cells whose antenna anomaly exceeds kappa."""
    a = rust_anomaly(scan, w3, level, degree, data) if anomaly is None else anomaly
    with np.errstate(invalid="ignore"):
        return w3 | (a > kappa)


# -- the NumPy reference (section 2) ------------------------------------------------


def _median(v, minimum=1):
    v = v[np.isfinite(v)]
    return float(np.median(v)) if len(v) >= minimum else math.nan


def grid(nt, nc):
    """Block indices per dump and channel: 2c (ta, ja), 2d (tv, jv)."""
    nta = max(nt // 2, 1)
    ta = np.minimum(np.arange(nt) // 2, nta - 1)
    k = max((nt + 5) // 10, 1)
    ln = max(-(-nt // k), 1)
    tv = np.arange(nt) // ln
    return {
        "nta": nta,
        "ta": ta,
        "nja": -(-nc // AMP_DF),
        "ntv": int(tv.max()) + 1,
        "tv": tv,
        "njv": -(-nc // VAR_DF),
    }


def _grid_data(scan, flagged, data):
    ix = f3.index(scan)
    data = scan["data"] if data is None else data
    nbl, nt, nc = len(ix["ubl"]), ix["nt"], data.shape[1]
    vis = np.zeros((nbl, nt, nc, 4), np.complex64)
    fl = np.ones((nbl, nt, nc), bool)
    vis[ix["bl"], ix["t"]] = data
    fin = np.isfinite(data.view(np.float32)).reshape(data.shape[:2] + (8,)).all(-1)
    fl[ix["bl"], ix["t"]] = flagged | ~fin
    return ix, vis, fl


def _sigma2_log(x):
    if len(x) < MIN_VAR:
        return math.nan
    s = MAD * np.median(np.abs(x - np.median(x))) / math.sqrt(2)
    return math.log(s * s) if np.isfinite(s) and s > 0 else math.nan


def block_stats(vis, fl, g, with_var=True):
    """amp (nbl, nta, nja, 4) log median |V|; vt, vf (nbl, ntv, njv) log σ²."""
    nbl, nt, nc, _ = vis.shape
    amp = np.full((nbl, g["nta"], g["nja"], 4), np.nan)
    vt = np.full((nbl, g["ntv"], g["njv"]), np.nan)
    vf = np.full_like(vt, np.nan)
    a = np.abs(vis.astype(np.complex128))
    re = vis.view(np.float32).reshape(nbl, nt, nc, 8).astype(np.float64)
    for b in range(nbl):
        for t_ in range(g["nta"]):
            t0 = 2 * t_
            t1 = nt if t_ + 1 == g["nta"] else t0 + 2
            for j in range(g["nja"]):
                f0, f1 = j * AMP_DF, min(j * AMP_DF + AMP_DF, nc)
                ok = ~fl[b, t0:t1, f0:f1]
                n = int(ok.sum())
                if n == 0 or 2 * n < ok.size:
                    continue
                for c in range(4):
                    m = np.median(a[b, t0:t1, f0:f1, c][ok])
                    if m > 0:
                        amp[b, t_, j, c] = math.log(m)
        if not with_var:
            continue
        for tb in range(g["ntv"]):
            ts = np.flatnonzero(g["tv"] == tb)
            for jb in range(g["njv"]):
                f0, f1 = jb * VAR_DF, min(jb * VAR_DF + VAR_DF, nc)
                dt, df = [], []
                for t in ts:
                    for f in range(f0, f1):
                        if fl[b, t, f]:
                            continue
                        if t + 1 < nt and g["tv"][t + 1] == tb and not fl[b, t + 1, f]:
                            dt.append(re[b, t + 1, f] - re[b, t, f])
                        if f + 1 < f1 and not fl[b, t, f + 1]:
                            df.append(re[b, t, f + 1] - re[b, t, f])
                vt[b, tb, jb] = _sigma2_log(np.concatenate(dt) if dt else np.zeros(0))
                vf[b, tb, jb] = _sigma2_log(np.concatenate(df) if df else np.zeros(0))
    return amp, vt, vf


def polish(y, a1, a2, nant):
    """Section 2c step 2: γ (nant,), s; simultaneous updates."""
    s = _median(y, f3.MIN_AGG)
    if not np.isfinite(s):
        return np.full(nant, np.nan), math.nan
    g = np.zeros(nant)
    for _ in range(POLISH_ITERS):
        g2 = np.full(nant, np.nan)
        for p in range(nant):
            m1, m2 = a1 == p, a2 == p
            v = np.concatenate([y[m1] - s - g[a2[m1]], y[m2] - s - g[a1[m2]]])
            g2[p] = _median(v, f3.MIN_AGG)
        c = _median(g2, 1)
        if np.isfinite(c):
            g2 = g2 - c
        s = _median(y - g2[a1] - g2[a2], f3.MIN_AGG)
        g = g2
        if not np.isfinite(s):
            break
    return g, s


def robust_fit(v, d):
    """Section 2c step 3: Huber IRLS Chebyshev fit of degree d over blocks."""
    n = len(v)
    m = d + 1
    fin = np.isfinite(v)
    if fin.sum() < 2 * m:
        return np.full(n, np.nan)
    x = 2.0 * (np.arange(n) + 0.5) / n - 1.0
    basis = np.polynomial.chebyshev.chebvander(x, d)
    w = np.ones(n)
    fit = np.full(n, np.nan)
    for p in range(4):
        bw = basis[fin] * w[fin, None]
        coef = np.linalg.solve(bw.T @ basis[fin], bw.T @ v[fin])
        fit = basis @ coef
        if p == 3:
            break
        e = v[fin] - fit[fin]
        scale = MAD * np.median(np.abs(e - np.median(e)))
        if not (np.isfinite(scale) and scale > 0):
            break
        r = np.abs(v - fit)
        w = np.where(r <= HUBER_K * scale, 1.0, HUBER_K * scale / np.where(r > 0, r, 1))
    return fit


def _mad_scale(v):
    v = v[np.isfinite(v)]
    return MAD * float(np.median(np.abs(v - np.median(v)))) if len(v) else math.nan


def factorise(y, a1, a2, nant, d, want_q):
    """y (nrow, ncol, nbl) → z (nrow, ncol, nant) and Q (or None)."""
    nrow, ncol, _ = y.shape
    gam = np.full((nrow, ncol, nant), np.nan)
    q = np.full((nrow, ncol, nant), np.nan) if want_q else None
    for r in range(nrow):
        for j in range(ncol):
            g, s = polish(y[r, j], a1, a2, nant)
            gam[r, j] = g
            if want_q:
                res = y[r, j] - g[a1] - g[a2] - s
                for p in range(nant):
                    v = res[(a1 == p) | (a2 == p)]
                    v = v[np.isfinite(v)]
                    q[r, j, p] = _mad_scale(v) if len(v) >= f3.MIN_AGG else math.nan
                q[r, j] = q[r, j] / _median(q[r, j], 1)
    z = np.full_like(gam, np.nan)
    for r in range(nrow):
        an = np.stack(
            [gam[r, :, p] - robust_fit(gam[r, :, p], d) for p in range(nant)], 1
        )
        sig = _mad_scale(an.ravel())
        if np.isfinite(sig) and sig > 0:
            z[r] = an / sig
    return z, q


def antenna_numpy(scan, flagged, level=0, degree=2, data=None):
    """Section 2c-2d per antenna: z, Q (nta, nja, 2, nant); tt, tf (ntv, njv, nant)."""
    ix, vis, fl = _grid_data(scan, flagged, data)
    _, nt, nc, _ = vis.shape
    nant = max(int(scan["nant"]), int(ix["ubl"].max()) + 1)
    g = grid(nt, nc)
    with_var = level == 0
    amp, vt, vf = block_stats(vis, fl, g, with_var)
    a1, a2 = ix["ant1"].astype(int), ix["ant2"].astype(int)
    zc, qc = [], []
    for c in range(4):
        z, q = factorise(np.moveaxis(amp[..., c], 0, -1), a1, a2, nant, degree, True)
        zc.append(z)
        qc.append(q)
    shape = (g["nta"], g["nja"], 2, nant)
    z = np.full(shape, np.nan)
    q = np.full(shape, np.nan)
    for phi, (c0, c1) in enumerate(FAMILIES):
        za, zb = zc[c0], zc[c1]
        pick_b = np.isfinite(zb) & (~np.isfinite(za) | (np.abs(zb) > np.abs(za)))
        z[:, :, phi] = np.where(pick_b, zb, za)
        q[:, :, phi] = np.fmax(qc[c0], qc[c1])
    tt = tf = None
    if with_var:
        tt = factorise(np.moveaxis(vt, 0, -1), a1, a2, nant, degree, False)[0]
        tf = factorise(np.moveaxis(vf, 0, -1), a1, a2, nant, degree, False)[0]
    return {"grid": g, "z": z, "q": q, "tt": tt, "tf": tf, "flagged": fl}


def _ash(z):
    z = np.asarray(z, np.float64)
    ok = np.isfinite(z)
    return np.where(ok, np.arcsinh(np.where(ok, z, 0.0)), 0.0)


def _pair(a, b):
    both = np.isfinite(a) & np.isfinite(b)
    one = np.where(np.isfinite(a), a, b)
    return np.where(both, np.maximum(a, b), one), np.where(both, np.minimum(a, b), one)


def features_numpy(scan, flagged, select, level=0, degree=2, data=None):
    """Section 2 in float64 (slow; parity on small scans)."""
    ix = f3.index(scan)
    old = f4.features_numpy(scan, flagged, select, data)  # F3's 14, F4's 8, mask
    an = antenna_numpy(scan, flagged, level, degree, data)
    g = an["grid"]
    nsel, nt, nc, _ = old.shape
    n = nplanes(level)
    out = np.zeros((nsel, nt, nc, n), np.float32)
    mask = old[..., 22] != 0
    out[..., n - 1] = old[..., 22]
    _, _, _, alive, _ = f4.spectra_numpy(scan, flagged, data)
    ta, tv = g["ta"], g["tv"]
    ja = np.arange(nc) // AMP_DF
    jv = np.arange(nc) // VAR_DF
    for i, b in enumerate(select):
        if not alive[b]:
            continue
        p, q = int(ix["ant1"][b]), int(ix["ant2"][b])
        planes = [old[i, ..., :CELL_PLANES]]
        if level <= 1:
            planes.append(old[i, ..., f4.SPEC0 : f4.SPEC0 + 8])
        blk = []
        for phi in range(2):
            mx, mn = _pair(an["z"][:, :, phi, p], an["z"][:, :, phi, q])
            qmx, _ = _pair(an["q"][:, :, phi, p], an["q"][:, :, phi, q])
            blk += [_ash(mx), _ash(mn), _ash(qmx)]
        planes.append(np.stack([x[ta][:, ja] for x in blk], -1))
        if level == 0:
            vb = []
            for arr in (an["tt"], an["tf"]):
                mx, mn = _pair(arr[:, :, p], arr[:, :, q])
                vb += [_ash(mx), _ash(mn)]
            planes.append(np.stack([x[tv][:, jv] for x in vb], -1))
        h = np.concatenate(planes, -1)
        h[mask[i]] = 0.0
        out[i, ..., : n - 1] = h
    return out


# -- gates (section 8) --------------------------------------------------------------


def relabel(scan, seed):
    """G-perm: antenna labels and the antenna table permuted, rows in place."""
    live = np.unique(np.concatenate([scan["antenna1"], scan["antenna2"]]))
    rng = np.random.default_rng(seed)
    perm = np.arange(max(int(scan["nant"]), int(live.max()) + 1))
    perm[live] = rng.permutation(live)
    out = {k: v for k, v in scan.items() if k != "_index"}
    out["antenna1"] = np.ascontiguousarray(perm[scan["antenna1"]])
    out["antenna2"] = np.ascontiguousarray(perm[scan["antenna2"]])
    pos = np.asarray(scan["antenna_position"])
    new = pos.copy()
    new[perm[live]] = pos[live]
    out["antenna_position"] = new
    return out, perm


def subarray(scan, keep):
    """The rows whose two antennas are in `keep` (G-drop, G-sub)."""
    rows = np.flatnonzero(
        np.isin(scan["antenna1"], keep) & np.isin(scan["antenna2"], keep)
    )
    out = {k: v for k, v in scan.items() if k != "_index"}
    for k in ("data", "input_flags", "antenna1", "antenna2", "times"):
        out[k] = np.ascontiguousarray(scan[k][rows])
    if "weights" in scan:
        out["weights"] = np.ascontiguousarray(scan["weights"][rows])
    return out, rows


def live_antennas(scan):
    return np.unique(np.concatenate([scan["antenna1"], scan["antenna2"]]))


def drop_draw(scan, k, seed):
    """G-drop: the antennas kept after removing k live ones."""
    live = live_antennas(scan)
    gone = np.random.default_rng(seed + 100 * k).choice(live, k, replace=False)
    return np.setdiff1d(live, gone)


def layouts(scan):
    """G-sub: core16 (nearest the median position) and outer32 (farthest)."""
    live = live_antennas(scan)
    pos = np.asarray(scan["antenna_position"], float)[live]
    order = live[
        np.argsort(np.linalg.norm(pos - np.median(pos, 0), axis=1), kind="stable")
    ]
    return {"core16": np.sort(order[:16]), "outer32": np.sort(order[-32:])}


def average_channels(scan, factor=4):
    """G-chan: data mean of `factor` channels, flags OR (synthetic 836 kHz)."""
    out = {k: v for k, v in scan.items() if k != "_index"}
    nr, nc = scan["data"].shape[:2]
    m = nc // factor
    out["data"] = np.ascontiguousarray(
        scan["data"][:, : m * factor].reshape(nr, m, factor, -1).mean(2), np.complex64
    )
    fl = scan["input_flags"]
    out["input_flags"] = np.ascontiguousarray(
        fl[:, : m * factor].reshape((nr, m, factor) + fl.shape[2:]).any(2)
    )
    cf = np.asarray(scan["chan_freq"]).ravel()[: m * factor]
    out["chan_freq"] = cf.reshape(m, factor).mean(1)
    out["chan_width"] = (
        np.asarray(scan["chan_width"]).ravel()[: m * factor].reshape(m, factor).sum(1)
    )
    return out


# -- injections (section 3) ---------------------------------------------------------

TRAIN_MORPHOLOGIES = f4.TRAIN_MORPHOLOGIES + ("T7",)
HELD_OUT = f4.HELD_OUT + ("H4", "H4n")
CODES = TRAIN_MORPHOLOGIES + HELD_OUT
T7_BETA = (0.1, 10.0)
T7_POSITIVE = 0.5
H4N_BETA = 2.0


class Injector(f4.Injector):
    """F4's injector with T7 (noise-like antenna-local, training) and H4, H4n
    (slow ramps, held out). Noise-like events are tracked in `beta`, the
    excess noise variance in units of sigma_b squared, not in `amp`."""

    codes = CODES

    def __init__(self, scan, eligible, sigma, rng, fixed=None):
        super().__init__(scan, eligible, sigma, rng, fixed)
        self.beta = np.zeros(eligible.shape, np.float32)

    def _cells(self, bsel, tsel, chans):
        ix = self.ix
        rows = np.flatnonzero(bsel[ix["bl"]])
        cmask = np.zeros(self.nc, bool)
        cmask[chans] = True
        cells = tsel[ix["t"][rows]][:, None] & cmask[None]
        cells &= self.eligible[rows] & (self.sigma[rows] > 0)[:, None]
        r_, c_ = np.nonzero(cells)
        return rows[r_], c_

    def add_noise(self, code, bsel, tsel, chans, beta, tfac=None):
        """Independent complex Gaussian noise of std sqrt(beta) sigma_b per
        component on the cells; `tfac` (nt,) scales beta per dump (H4n)."""
        rows, c_ = self._cells(bsel, tsel, chans)
        if not len(rows):
            return
        b = beta * (np.ones(self.nt) if tfac is None else tfac)[self.ix["t"][rows]]
        s = (np.sqrt(b) * self.sigma[rows])[:, None]
        z = s * (
            self.rng.normal(0, 1, (len(rows), 4))
            + 1j * self.rng.normal(0, 1, (len(rows), 4))
        )
        self.data[rows, c_] += z.astype(np.complex64)
        new = b > self.beta[rows, c_]
        self.beta[rows, c_] = np.maximum(self.beta[rows, c_], b.astype(np.float32))
        self.morph[rows[new], c_[new]] = 1 + self.codes.index(code)
        self.events.append({"code": code, "cells": len(rows), "beta": float(beta)})

    def add_ramp(self, code, bsel, chans, tfac):
        """Coherent fixed-strength phasor scaled per dump by `tfac` (H4)."""
        rows, c_ = self._cells(bsel, self._all_times(), chans)
        if not len(rows):
            return
        alpha = float(self.fixed) * tfac[self.ix["t"][rows]]
        phase = self.rng.uniform(-np.pi, np.pi) + self.rng.normal(0, 0.15, len(rows))
        w = f3._coupling(self.rng)
        z = (alpha * self.sigma[rows] * np.exp(1j * phase))[:, None] * w[None]
        self.data[rows, c_] += z.astype(np.complex64)
        a = (
            np.abs(self.data[rows, c_] - self.scan["data"][rows, c_]).max(-1)
            / self.sigma[rows]
        ).astype(np.float32)
        new = a > self.amp[rows, c_]
        self.amp[rows, c_] = np.maximum(self.amp[rows, c_], a)
        self.morph[rows[new], c_[new]] = 1 + self.codes.index(code)
        self.events.append({"code": code, "cells": len(rows)})

    def t7(self):
        rng = self.rng
        k = int(rng.choice(self._live_antennas()))
        bsel = (self.ix["ant1"] == k) | (self.ix["ant2"] == k)
        w = f4.t6_width(rng, self.nc)
        c0 = int(rng.integers(0, self.nc - w + 1))
        chans = np.arange(c0, c0 + w)
        if rng.random() < 0.5:
            tm = self._all_times()
        else:
            tm = self._run(min(2, self.nt), self.nt)
        beta = math.exp(rng.uniform(math.log(T7_BETA[0]), math.log(T7_BETA[1])))
        self.add_noise("T7", bsel, tm, chans, beta)
        self.events[-1].update(antenna=k, width=w)

    def training(self):
        super().training()
        for _ in range(self.rng.integers(1, 4)):
            self.t7()

    def _ramp(self):
        rng = self.rng
        t0 = int(rng.integers(0, max(self.nt // 4, 1)))
        t = np.arange(self.nt, dtype=np.float64)
        span = max(self.nt - 1 - t0, 1)
        r = np.clip((t - t0) / span, 0.0, 1.0)
        return r[::-1].copy() if rng.random() < 0.5 else r

    def held_out(self, code):
        if code not in ("H4", "H4n"):
            return super().held_out(code)
        rng = self.rng
        k = int(rng.choice(self._live_antennas()))
        bsel = (self.ix["ant1"] == k) | (self.ix["ant2"] == k)
        lo, hi = max(1, int(0.1 * self.nc)), max(2, int(0.4 * self.nc))
        w = min(int(rng.integers(lo, hi + 1)), self.nc)
        c0 = int(rng.integers(0, self.nc - w + 1))
        chans = np.arange(c0, c0 + w)
        tfac = self._ramp()
        if code == "H4":
            self.add_ramp("H4", bsel, chans, tfac)
        else:
            self.add_noise("H4n", bsel, self._all_times(), chans, H4N_BETA, tfac)
        return None


def r2_case(scan, eligible, sigma, code, seed):
    """R2's held-out case at 10 sigma_b (H4n at beta 2): data, rows, chans of
    the truth cells: A > 0 for H1-H3 (F4's), the label positives for the
    ramps (H4: A >= 3; H4n: beta >= 0.5; Amendment 2)."""
    inj = Injector(
        scan, eligible, sigma, np.random.default_rng(seed), fixed=f3.STRENGTH
    )
    inj.held_out(code)
    if code == "H4n":
        truth = inj.beta >= T7_POSITIVE
    elif code == "H4":
        truth = inj.amp >= 3
    else:
        truth = inj.amp > 0
    rows, chans = np.nonzero(truth)
    return inj.data, rows, chans


# -- labels (section 4) -------------------------------------------------------------


def labels(inj, eligible, t_flag=None, a_flag=None, truth_amp=None, strong=None):
    """Landman's scheme. Positive: injected A >= 3 or T7 beta >= 0.5, or
    simulation truth A >= 3. Ignored: T or A on the uninjected DATA (real
    scans), 0 < A < 3, 0 < beta < 0.5, F. Negative: the rest."""
    pos = (inj.amp >= 3) | (inj.beta >= T7_POSITIVE)
    weak = ((inj.amp > 0) & (inj.amp < 3)) | ((inj.beta > 0) & (inj.beta < T7_POSITIVE))
    if truth_amp is not None:
        pos |= truth_amp >= 3
        weak |= (truth_amp > 0) & (truth_amp < 3)
    lab = np.zeros(eligible.shape, np.int8)
    lab[weak] = -1
    if t_flag is not None:
        lab[(t_flag | a_flag) & ~pos] = -1
    lab[pos] = 1
    if strong is not None:
        # F6's hybrid positives (research/f6-flagger.md, fix 1): native cells T and A
        # both flag with strength s >= 3 on the uninjected DATA.
        native = (inj.amp == 0) & (inj.beta == 0)
        lab[strong & native] = 1
    lab[~eligible] = -1
    return lab


def realise(scan, w3, sigma, seed, augment, t_flag=None, a_flag=None, strong=None):
    """One realisation: (injected DATA, flags before the network, labels,
    Injector, rng)."""
    rng = np.random.default_rng(seed)
    inj = Injector(scan, ~w3, sigma, rng)
    inj.training()
    flags = f3.augment_input_flags(rng, w3, scan) if augment else w3
    elig = ~flags
    if t_flag is None:
        lab = labels(inj, elig, truth_amp=scan["amp"])
    else:
        lab = labels(inj, elig, t_flag, a_flag, strong=strong)
    return inj.data, flags, lab, inj, rng


def hybrid_strong(scan, w3, t_flag, a_flag, bar=3.0, data=None):
    """F6's hybrid-positive cells: T and A both flag, strength s >= bar on the
    uninjected DATA (s as F4: max of the residual and spectral planes)."""
    s = f4.strength_rows(scan, w3, data)
    return t_flag & a_flag & ~w3 & (s >= bar)


def subarray_draw(scan, seed, lo=24):
    """Section 3's sub-array augmentation: a uniform count of lo to nlive - 1
    live antennas, drawn uniformly."""
    live = live_antennas(scan)
    rng = np.random.default_rng(seed)
    n = int(rng.integers(lo, len(live)))
    return np.sort(rng.choice(live, n, replace=False))


# -- arm A on Linux (section 5) -----------------------------------------------------

AO_SIF = (
    None  # set by use_data_root's caller on nash: the SIF of rang-aflag-aoflagger:3.5.0
)


def a_flags(scan, w3, workdir, data=None):
    """Arm A: F3's `a_flags` (W3 OR AOFlagger 3.5.0 generic-default with W3 as
    the input mask, the same container script), through apptainer when
    `AO_SIF` is set (nash, no docker), else F3's WSL docker route."""
    if AO_SIF is None:
        return f3.a_flags(scan, w3, workdir, data)
    import subprocess
    import time
    from pathlib import Path

    ix = f3.index(scan)
    data = scan["data"] if data is None else data
    nbl, nt, nc = len(ix["ubl"]), ix["nt"], data.shape[1]
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    vis = np.lib.format.open_memmap(
        work / "vis.npy", "w+", np.complex64, (nbl, nt, nc, 4)
    )
    vis[:] = 0
    vis[ix["bl"], ix["t"]] = data
    vis.flush()
    del vis
    mask = np.ones((nbl, nt, nc), bool)
    mask[ix["bl"], ix["t"]] = w3
    np.save(work / "mask.npy", mask)
    tools = Path(f3.__file__).resolve().parents[2] / "tools/oracles/aoflagger"
    cmd = [
        "apptainer",
        "exec",
        "--containall",
        "--cleanenv",
        "--env",
        "PYTHONPATH=/usr/lib,OMP_NUM_THREADS=4,OPENBLAS_NUM_THREADS=1,HOME=/tmp",
        "-B",
        f"{work}:/io",
        "-B",
        f"{tools}:/tools:ro",
        str(AO_SIF),
        "python3",
        "/tools/f3_aoflag.py",
        "/io",
    ]
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, capture_output=True)
    wall = time.perf_counter() - t0
    out = np.load(work / "flags.npy")
    rec = json.loads((work / "aoflag.json").read_text(encoding="utf-8"))
    rec["container_wall"] = wall
    flags = out[ix["bl"], ix["t"]] | w3
    for name in ("vis.npy", "mask.npy", "flags.npy"):
        (work / name).unlink()
    return flags, rec


# -- data roots (nash) --------------------------------------------------------------


def use_data_root(root):
    """Point F3's and F4's loaders at a copy of D:/rang laid out the same way
    (`<root>/outputs/...`, `<root>/data/eso137-pilot/...`), e.g. on nash."""
    from pathlib import Path

    root = Path(root)
    out = root / "outputs"
    f3.D_OUT = out
    f3.INPUTS = out / "f3-20261110-02-inputs"
    f3.FETCH = out / "f3-20261110-01-fetch" / "objects"
    f3.ESO = root / "data" / "eso137-pilot" / "ESO137" / "ms1_target.zarr"
    f3.F2_TRAIN = out / "f2-20261106-02-sim-train"
    f3.F2_VAL = out / "f2-20261106-01-sim-v" / "f2sim-v"
    f4.FETCH = out / "f4-20261111-01-fetch" / "objects"
    f4.F4_TEST = out / "f4-20261111-02-sim-test" / "f4sim-t"


# -- the post hoc calibrator arm's held-out groups (Amendment 3) --------------------

RESERVED_GROUPS = ("MAIN_8", "MAIN_9", "MAIN_10", "MAIN_11", "MAIN_13", "MAIN_15")
RESERVED_FETCH = None  # the objects/ directory of examples/f5_fetch.py's run


def load_reserved(group, heldout=False):
    """A reserved LUNO group for N5-ph (Amendment 3): read once, at scoring."""
    if group not in RESERVED_GROUPS:
        raise ValueError(f"{group} is not a reserved group")
    if not heldout:
        raise PermissionError(
            f"{group} is held out for N5-ph; pass heldout=True at scoring"
        )
    if RESERVED_FETCH is None:
        raise RuntimeError(
            "set rang.f5flag.RESERVED_FETCH to the fetch's objects/ directory"
        )
    return f3.read_luno(group, (RESERVED_FETCH, f3.INPUTS))


# -- F6: SARAO archive scans (research/f6-flagger.md, section 1) ---------------------

SARAO_CHANS = slice(
    1024, 3072
)  # LUNO's window of the 4,096-channel L band, 1070-1498 MHz
SARAO_TEACHERS = {
    "T": "rang",
    "A": "aoflagger",
}  # A: AOFlagger 2.13, CARACal's firstpass_QUV


def _unpack_labels(path, nrow, nchan_all, ncorr, chans):
    """C's flag.npy (bit-packed per row over C-order (chan, corr)) as (row, chan)
    bool, any over correlations, cut to `chans`."""
    from pathlib import Path

    packed = np.load(Path(path) / "flag.npy")
    bits = np.unpackbits(packed, axis=1, count=nchan_all * ncorr).astype(bool)
    bits = bits.reshape(nrow, nchan_all, ncorr)[:, chans]
    frow = np.load(Path(path) / "flag_row.npy").astype(bool)
    return bits.any(-1) | frow[:, None]


def load_sarao(
    ms, klass, label_root=None, cbid=None, scan_name=None, chans=SARAO_CHANS
):
    """One SARAO scan (C's frozen MS) as F5's scan dict; with `label_root`, also
    the teachers' flags under scan["teachers"] ({"T", "A"}: (row, chan) bool in
    the dict's rows). Autocorrelations and FLAG_ROW rows are dropped, as for LUNO."""
    from pathlib import Path

    from . import core_ms

    ms = Path(ms)
    if scan_name is not None and str(scan_name).isdigit():
        scan_name = f"scan{int(scan_name):03d}"  # C's manifest gives the number
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        a1 = np.asarray(t.getcol("ANTENNA1"), np.int32)
        a2 = np.asarray(t.getcol("ANTENNA2"), np.int32)
        frow = np.asarray(t.getcol("FLAG_ROW"), bool)
        keep = (a1 != a2) & ~frow
        times = np.asarray(t.getcol("TIME"), np.float64)
        data = np.asarray(t.getcol("DATA", chans=chans), np.complex64)
        flag = np.asarray(t.getcol("FLAG", chans=chans), bool)
    with core_ms.open_table(ms / "ANTENNA") as t:
        pos = np.asarray(t.getcol("POSITION"), np.float64)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq_all = np.asarray(t.getcol("CHAN_FREQ")[0], np.float64)
        width_all = np.asarray(t.getcol("CHAN_WIDTH")[0], np.float64)
    with core_ms.open_table(ms / "POLARIZATION") as t:
        corr = np.asarray(t.getcol("CORR_TYPE")[0], np.int32)
    scan = {
        "data": np.ascontiguousarray(data[keep]),
        "input_flags": np.ascontiguousarray(flag[keep]),
        "antenna1": np.ascontiguousarray(a1[keep]),
        "antenna2": np.ascontiguousarray(a2[keep]),
        "times": np.ascontiguousarray(times[keep]),
        "antenna_position": pos,
        "chan_freq": np.ascontiguousarray(freq_all[chans]),
        "chan_width": np.ascontiguousarray(width_all[chans]),
        "corr_type": corr,
        "nant": len(pos),
        "klass": klass,
        "field": f"SARAO {cbid} {scan_name or ms.name}",
    }
    if label_root is not None:
        scan["teachers"] = {
            k: _unpack_labels(
                Path(label_root) / v / str(cbid) / (scan_name or ms.stem),
                nrow,
                len(freq_all),
                len(corr),
                chans,
            )[keep]
            for k, v in SARAO_TEACHERS.items()
        }
    return scan
