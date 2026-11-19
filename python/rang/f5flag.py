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

import math

import numpy as np

from . import core
from . import f3flag as f3
from . import f4flag as f4

LEVEL_INPUTS = {0: 33, 1: 29, 2: 21}
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


def n5_flags(scan, w3, weights, tau, level=0, degree=2, data=None):
    logit = rust_logits(scan, w3, weights, level, degree, data)
    return w3 | (logit > tau), logit


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
