# SPDX-License-Identifier: MIT
"""DD9: the O-X rate, a constraint on the weak facet d3, and a robust held-out
score (research/dd9-solver.md).

    python tools/oracles/dd9/dd9.py sums RUN MODEL OUT.npz        # predict + compress
    python tools/oracles/dd9/dd9.py gate ROOT                      # gate GR (reference vs Rust)
    python tools/oracles/dd9/dd9.py parta ROOT                     # section 4: runs, history
    python tools/oracles/dd9/dd9.py jac ROOT BASE                  # section 4: linearised rates
    python tools/oracles/dd9/dd9.py partb ROOT                     # section 5 (O and O-H arms)
    python tools/oracles/dd9/dd9.py partc ROOT                     # section 6 (validation, real arms)
    python tools/oracles/dd9/dd9.py rustbm ROOT                    # the one Rust point (bM on O)
    python tools/oracles/dd9/dd9.py dd8robust ROOT                 # section 6, post hoc re-read

Every solve is the numpy reference of rang's `diag_complex` DD kernel
(core/src/cal/diag_dd.rs) on per-(4-integration block, baseline, hand) sums
A_dd' = sum w conj(M_d) M_d', b_d = sum w conj(M_d) V, which the kernel's
update depends on exactly (section 3). DD7's and DD8's roots are read only.
"""

import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DD7_ROOT = Path("D:/rang/outputs/dd7-20261125")
DD8_ROOT = Path("D:/rang/outputs/dd8-20261125")
BLOCK = 4  # integrations per sums block (the truth block and the 4 x 8 s interval)
STOP = 1e-7
STOP_FRACTION = 0.99
NUMBNESS = 1e-6
TREND_LIMIT = 1e-6
DET_LIMIT = 1e-6
SIGMA_A = 0.2  # bR's amplitude prior (section 5)
COND_LIMIT = 1e12  # I3's fallback to the diagonal update
BOOT = {"n": 2000, "seed": 9901, "level": 0.99}
TRIM = 0.10


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dd8():
    return _load("dd8", HERE.parent / "dd8" / "dd8.py")


# -- sums -----------------------------------------------------------------------------


def baseline_index(a1, a2):
    """Baselines in the rows' own orientation (p = ANTENNA1, q = ANTENNA2)."""
    key = a1.astype(np.int64) * 100000 + a2
    ukey, inv = np.unique(key, return_inverse=True)
    p, q = (ukey // 100000).astype(int), (ukey % 100000).astype(int)
    swapped = np.isin(q * 100000 + p, ukey) & (p != q)
    assert not swapped.any(), "a baseline appears in both orientations"
    return inv, p, q


def kept_cells(data, weights, flag, flag_row):
    """crate::solve::data_flags, negated: (rows, chans) bool."""
    bad = flag.any(-1) | flag_row.astype(bool)[:, None]
    for c in (0, 3):
        bad |= (data[..., c].real == 0) & (data[..., c].imag == 0)
        bad |= weights[..., c] == 0
    return ~bad


def compress(data, weights, keep, vis, block, inv, nblock, nbl, chunk=20000):
    """Per (block, baseline, hand): A (D x D), b (D), s = sum w|V|^2, n cells.
    data, weights: (rows, chans, 4); vis: list of D arrays (rows, chans) (the
    facet predicts, the same for both hands)."""
    ndir = len(vis)
    A = np.zeros((nblock * nbl, 2, ndir, ndir), complex)
    b = np.zeros((nblock * nbl, 2, ndir), complex)
    s = np.zeros((nblock * nbl, 2))
    n = np.zeros((nblock * nbl, 2))
    cell = block * nbl + inv
    nrow = data.shape[0]
    for j in range(0, nrow, chunk):
        r = slice(j, min(j + chunk, nrow))
        idx = cell[r]
        M = np.stack([v[r].astype(np.complex128) for v in vis], -1)  # (r, c, D)
        k = keep[r]
        for h, corr in enumerate((0, 3)):
            w = np.where(k, weights[r, :, corr].astype(np.float64), 0.0)
            D = data[r, :, corr].astype(np.complex128)
            wM = w[..., None] * np.conj(M)
            Ar = np.einsum("rcd,rce->rde", wM, M)
            br = np.einsum("rcd,rc->rd", wM, D)
            sr = (w * (D.real**2 + D.imag**2)).sum(1)
            nr = k.sum(1).astype(float)
            m = nblock * nbl
            for d in range(ndir):
                b[:, h, d] += np.bincount(idx, br[:, d].real, m) + 1j * np.bincount(
                    idx, br[:, d].imag, m
                )
                for e in range(ndir):
                    A[:, h, d, e] += np.bincount(
                        idx, Ar[:, d, e].real, m
                    ) + 1j * np.bincount(idx, Ar[:, d, e].imag, m)
            s[:, h] += np.bincount(idx, sr, m)
            n[:, h] += np.bincount(idx, nr, m)
    sh = (nblock, nbl, 2)
    return (A.reshape(sh + (ndir, ndir)), b.reshape(sh + (ndir,)), s.reshape(sh),
            n.reshape(sh))  # fmt: skip


def sums(run, model, out):
    """Section 3: predict MODEL's four facets on RUN's MS and compress."""
    dd8 = _dd8()
    dd4, dd6 = dd8.dd4, dd8.dd6
    run, out = Path(run), Path(out)
    t0 = time.perf_counter()
    st = json.loads((run / "setup.json").read_text())
    c = dd4.read_sub(st["subms"])
    idx = dd6.facet_idx(run)
    m = np.load(model)
    vis = [dd8.facet_vis(c["UVW"], c["freq"], idx, m, f) for f in range(4)]
    t1 = time.perf_counter()
    keep = kept_cells(c["DATA"], c["WEIGHT_SPECTRUM"], c["FLAG"], c["FLAG_ROW"])
    tindex = np.unique(c["TIME"], return_inverse=True)[1]
    block = tindex // BLOCK
    nblock = int(block.max()) + 1
    inv, p, q = baseline_index(c["ANTENNA1"], c["ANTENNA2"])
    A, b, s, n = compress(
        c["DATA"], c["WEIGHT_SPECTRUM"], keep, vis, block, inv, nblock, len(p)
    )
    nint_per_block = np.bincount(block, minlength=nblock) // max(len(p), 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, A=A, b=b, s=s, n=n, p=p, q=q, nant=len(c["ant_names"]),
             rows_per_block=np.bincount(block, minlength=nblock), nint_per_block=nint_per_block)  # fmt: skip
    rec = {"run": str(run), "model": str(model), "nblock": nblock, "nbl": len(p),
           "kept_cells": int(keep.sum()), "seconds_predict": t1 - t0,
           "seconds": time.perf_counter() - t0}  # fmt: skip
    out.with_suffix(".json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec), flush=True)


class Sums:
    """A sums file, optionally with baselines removed (held-out or bad) and a
    direction transform T (merge: new columns = T @ old)."""

    def __init__(self, path, drop=None, T=None):
        z = np.load(path)
        self.A, self.b, self.s, self.n = z["A"], z["b"], z["s"], z["n"]
        self.p, self.q, self.nant = z["p"], z["q"], int(z["nant"])
        if T is not None:
            T = np.asarray(T, float)
            self.A = np.einsum("ik,xyhkl,jl->xyhij", T, self.A, T)
            self.b = np.einsum("ik,xyhk->xyhi", T, self.b)
        if drop is not None:
            self.A = self.A.copy()
            self.b = self.b.copy()
            self.n = self.n.copy()
            self.A[:, drop] = 0
            self.b[:, drop] = 0
            self.n[:, drop] = 0
        self.nblock, self.nbl = self.n.shape[:2]
        self.ndir = self.A.shape[-1]

    def mask_of(self, pairs):
        key = {(int(a), int(b)) for a, b in pairs} | {
            (int(b), int(a)) for a, b in pairs
        }
        return np.array(
            [(int(a), int(b)) in key for a, b in zip(self.p, self.q, strict=True)]
        )


def merge_matrix(ndir, src, dst):
    """Rows: the new directions (src's column added to dst's, src dropped)."""
    T = np.eye(ndir)
    T[dst, src] = 1.0
    return np.delete(T, src, axis=0)


# -- the reference solver -------------------------------------------------------------


def _scatter(index, values, size):
    return np.bincount(index, values.real, size) + 1j * np.bincount(
        index, values.imag, size
    )


class Problem:
    """The solve on blocks `blocks` of a Sums, direction d's interval
    `blocks // m[d]` (relative to the first block)."""

    def __init__(self, S, blocks, m, pinned=(), lam=None):
        self.S = S
        self.blocks = np.asarray(blocks)
        self.A = S.A[self.blocks]
        self.bv = S.b[self.blocks]
        self.nb = len(self.blocks)
        self.D = S.ndir
        self.m = list(m)
        rel = self.blocks - self.blocks[0]
        self.iv = [rel // mm for mm in self.m]
        self.nint = [int(iv.max()) + 1 for iv in self.iv]
        self.pinned = np.zeros(self.D, bool)
        self.pinned[list(pinned)] = True
        self.lam = np.zeros(self.D) if lam is None else np.asarray(lam, float)
        nant, p, q = S.nant, S.p, S.q
        active = S.n[self.blocks].sum(-1) > 0  # (nb, nbl)
        self.unflagged0 = []
        for d in range(self.D):
            u = np.zeros(self.nint[d] * nant, bool)
            for side in (p, q):
                ix = self.iv[d][:, None] * nant + side[None, :]
                u[ix[active]] = True
            self.unflagged0.append(u.reshape(self.nint[d], nant))
        # flat scatter indices per direction: (nb, nbl) -> iv * nant + ant
        self.ip = [
            (self.iv[d][:, None] * nant + p[None, :]).ravel() for d in range(self.D)
        ]
        self.iq = [
            (self.iv[d][:, None] * nant + q[None, :]).ravel() for d in range(self.D)
        ]

    def coeffs(self, g):
        p, q = self.S.p, self.S.q
        gp = [g[d][self.iv[d]][:, p] for d in range(self.D)]  # (nb, nbl, 2)
        gq = [g[d][self.iv[d]][:, q] for d in range(self.D)]
        C = np.stack(
            [gp[d] * np.conj(gq[d]) for d in range(self.D)], -1
        )  # (nb, nbl, 2, D)
        return gp, gq, C

    def normal(self, g, dirs=None, joint=False):
        """Per direction: jhr, jhj (nint, nant, 2) at gains g (list of
        (nint_d, nant, 2) arrays); `joint` also the per-antenna direction
        block H (nint, nant, 2, D, D) (common interval only)."""
        nant = self.S.nant
        gp, gq, C = self.coeffs(g)
        dirs = range(self.D) if dirs is None else dirs
        out = {}
        for d in dirs:
            R = self.bv[..., d] - np.einsum("xyhe,xyhe->xyh", self.A[..., d, :], C)
            size = self.nint[d] * nant
            jhr = np.empty((size, 2), complex)
            jhj = np.empty((size, 2))
            Add = self.A[..., d, d].real
            for h in range(2):
                jhr[:, h] = _scatter(
                    self.ip[d], (gq[d][..., h] * R[..., h]).ravel(), size
                ) + _scatter(
                    self.iq[d], (gp[d][..., h] * np.conj(R[..., h])).ravel(), size
                )
                jhj[:, h] = np.bincount(self.ip[d], (np.abs(gq[d][..., h]) ** 2 * Add[..., h]).ravel(), size) + np.bincount(
                    self.iq[d], (np.abs(gp[d][..., h]) ** 2 * Add[..., h]).ravel(), size
                )  # fmt: skip
            out[d] = (
                jhr.reshape(self.nint[d], nant, 2),
                jhj.reshape(self.nint[d], nant, 2),
            )
        if joint:
            assert len(set(self.m)) == 1
            size = self.nint[0] * nant
            H = np.zeros((size, 2, self.D, self.D), complex)
            for d in range(self.D):
                for e in range(self.D):
                    for h in range(2):
                        vp = (
                            gq[d][..., h]
                            * np.conj(gq[e][..., h])
                            * self.A[..., h, d, e]
                        )
                        vq = (
                            gp[d][..., h]
                            * np.conj(gp[e][..., h])
                            * np.conj(self.A[..., h, d, e])
                        )
                        H[:, h, d, e] = _scatter(
                            self.ip[0], vp.ravel(), size
                        ) + _scatter(self.iq[0], vq.ravel(), size)
            out["H"] = H.reshape(self.nint[0], nant, 2, self.D, self.D)
        return out


def _update(jhr, jhj, g, lam):
    """Non-generalised invert (no update below det 1e-6) on one direction,
    with the amplitude prior lam (0: none)."""
    if lam:
        a = np.abs(g)
        jhr = jhr + lam * g * (1.0 / np.where(a > 0, a, 1.0) - 1.0)
        jhj = jhj + lam
    det = jhj[..., 0] * jhj[..., 1]
    ok = det >= DET_LIMIT
    u = np.where(ok[..., None], jhr / np.where(jhj != 0, jhj, 1.0), 0.0)
    return u


class State:
    def __init__(self, P, init=None):
        self.g = [np.ones((P.nint[d], P.S.nant, 2), complex) for d in range(P.D)]
        if init is not None:
            self.g = [np.array(x, complex) for x in init]
        self.km1 = [x.copy() for x in self.g]
        self.km1_diff = [np.zeros(x.shape[:2]) for x in self.g]
        self.trend = [np.zeros(x.shape[:2]) for x in self.g]
        self.flag = [np.where(u, 0, 1).astype(np.int8) for u in P.unflagged0]

    def snapshot(self):
        """finalize_gain_flags on a copy: (gains, flags) lists."""
        gs, fs = [], []
        for d in range(len(self.g)):
            f = self.flag[d].copy()
            g = self.g[d].copy()
            hard = self.trend[d] > TREND_LIMIT
            f[hard] = 1
            f[(~hard) & (f == -1)] = 0
            g[f == 1] = 1.0
            gs.append(g)
            fs.append(f)
        return gs, fs


def ladder(st, d, loop_idx, stop2=STOP * STOP):
    """update_gain_flags on direction d (after the gain update); returns the
    converged mask and the flagged mask."""
    g, f = st.g[d], st.flag[d]
    pre = f == 1
    km1_abs2 = (np.abs(st.km1[d]) ** 2).sum(-1)
    km0_diff = (np.abs(st.km1[d] - g) ** 2).sum(-1)
    zero = (~pre) & (km1_abs2 == 0)
    f[zero] = 1
    act = (~pre) & (~zero)
    old_diff = st.km1_diff[d].copy()
    st.km1_diff[d] = np.where(act, km0_diff, st.km1_diff[d])
    conv = np.zeros(f.shape, bool)
    if loop_idx >= 2:
        km1_trend = st.trend[d]
        km0_trend = km1_trend + km0_diff - old_diff
        st.trend[d] = np.where(act, km0_trend, km1_trend)
        rel = km0_diff / np.where(km1_abs2 > 0, km1_abs2, 1.0)
        c1 = act & (rel < stop2)
        c2 = act & ~c1 & (km0_trend < km1_trend) & (km1_trend < NUMBNESS)
        c3 = act & ~c1 & ~c2 & (km0_trend > km1_trend) & (km1_trend > NUMBNESS)
        f[c1 | c2] = 0
        f[c3] = np.where(f[c3] != 0, 1, -1)
        conv = c1
    flagged = f == 1
    g[flagged] = 1.0
    return conv, flagged


def iterate(P, st, loop_idx, variant="default"):
    """One iteration of the kernel (or a section-4 intervention) in place;
    returns (converged, flagged) counts and per-direction converged masks."""
    D = P.D
    if variant == "I1":
        alpha = 1.0 if loop_idx % 2 == 1 else 0.5
    else:
        alpha = 0.5
    if variant == "I2":  # Gauss-Seidel over directions
        for d in range(D):
            jhr, jhj = P.normal(st.g, dirs=[d])[d]
            _apply(P, st, d, _update(jhr, jhj, st.g[d], P.lam[d]), alpha)
    elif variant == "I3":
        ne = P.normal(st.g, joint=True)
        u = _joint_update(P, st, ne)
        for d in range(D):
            _apply(P, st, d, u[d], alpha)
    else:
        ne = P.normal(st.g)
        us = [_update(*ne[d], st.g[d], P.lam[d]) for d in range(D)]
        for d in range(D):
            _apply(P, st, d, us[d], alpha)
    conv_n = flag_n = 0
    convs = []
    for d in range(D):
        c, x = ladder(st, d, loop_idx)
        conv_n += int(c.sum())
        flag_n += int(x.sum())
        convs.append(c)
    for d in range(D):
        st.km1[d] = st.g[d].copy()
    return conv_n, flag_n, convs


def _apply(P, st, d, u, alpha):
    if P.pinned[d]:
        return
    g = st.g[d]
    fl = st.flag[d] == 1
    g += alpha * u
    g[fl] = 1.0


def _joint_update(P, st, ne):
    """I3: per antenna and hand u = H^-1 jhr over the directions whose diagonal
    update is not suppressed (det test) and whose gain is not flagged."""
    H = ne["H"]  # (nint, nant, 2, D, D)
    D = P.D
    jhr = np.stack([ne[d][0] for d in range(D)], -1)  # (nint, nant, 2, D)
    jhj = np.stack([ne[d][1] for d in range(D)], -1)
    det = jhj[:, :, 0, :] * jhj[:, :, 1, :]  # (nint, nant, D)
    free = (det >= DET_LIMIT) & np.stack([st.flag[d] != 1 for d in range(D)], -1)
    free &= ~P.pinned[None, None, :]
    fm = free[:, :, None, :] & free[:, :, None, :]  # per hand the same
    Hm = np.where(fm[..., :, None] & fm[..., None, :], H, 0.0)
    eye = np.eye(D)[None, None, None]
    Hm = Hm + np.where(fm[..., :, None] & fm[..., None, :], 0.0, eye)
    rhs = np.where(fm, jhr, 0.0)
    cond = np.linalg.cond(Hm)
    bad = ~np.isfinite(cond) | (cond > COND_LIMIT)
    Hs = np.where(bad[..., None, None], np.where(np.eye(D, dtype=bool), Hm, 0.0), Hm)
    u = np.linalg.solve(Hs, rhs[..., None])[..., 0]
    u = np.where(fm, u, 0.0)
    return [u[..., d] for d in range(D)]


def run(
    P,
    checkpoints,
    variant="default",
    stop_fraction=STOP_FRACTION,
    init=None,
    history=False,
):
    """Iterate to max(checkpoints) + 1 (or a global stop); per checkpoint K
    the result after min(K, stop) iterations and one iteration more, both
    finalized. `history`: per iteration, interval and direction the
    converged count, unflagged count and median step (common interval)."""
    st = State(P, init)
    ngains = sum(int(np.prod(x.shape[:2])) for x in st.g)
    kmax = max(checkpoints)
    snaps, stopped_at, it = {}, None, 0
    hist = {"conv": [], "unfl": [], "step": [], "fraction": []}
    while True:
        prev = [x.copy() for x in st.g] if history else None
        c, x, convs = iterate(P, st, it, variant)
        it += 1
        frac = c / (ngains - x) if ngains - x > 0 else 0.0
        hist["fraction"].append(frac)
        if history:
            hist["conv"].append(
                np.stack([cv.sum(1) for cv in convs], -1).astype(np.int16)
            )
            hist["unfl"].append(
                np.stack([(f != 1).sum(1) for f in st.flag], -1).astype(np.int16)
            )
            steps = []
            for d in range(P.D):
                rel = (np.abs(st.g[d] - prev[d]) ** 2).sum(-1) / np.maximum(
                    (np.abs(prev[d]) ** 2).sum(-1), 1e-300
                )
                rel = np.where(st.flag[d] != 1, rel, np.nan)
                steps.append(
                    np.nanmedian(
                        np.where(np.isnan(rel).all(1, keepdims=True), 0, rel), axis=1
                    )
                )
            hist["step"].append(np.stack(steps, -1).astype(np.float32))
        if stopped_at is None and frac >= stop_fraction:
            stopped_at = it
        for K in checkpoints:
            k_eff = min(K, stopped_at) if stopped_at is not None else K
            if it == k_eff:
                snaps.setdefault(K, {})["first"] = st.snapshot() + (it, frac)
            if it == k_eff + 1:
                snaps.setdefault(K, {})["second"] = st.snapshot()
        done = all("second" in snaps.get(K, {}) for K in checkpoints)
        if done or it > kmax + 1:
            break
    out = {K: {"g": snaps[K]["first"][0], "f": snaps[K]["first"][1], "iterations": snaps[K]["first"][2],
               "fraction": snaps[K]["first"][3], "g2": snaps[K]["second"][0], "f2": snaps[K]["second"][1]}
           for K in checkpoints}  # fmt: skip
    if history:
        out["history"] = {k: np.array(v) for k, v in hist.items()}
    out["stopped_at"] = stopped_at
    return out


def converged_cells(g1, g2, f1, f2, stop=STOP):
    d2 = (np.abs(g2 - g1) ** 2).sum(-1)
    n2 = (np.abs(g1) ** 2).sum(-1)
    ok = (f1 == 0) & (f2 == 0) & (n2 > 0)
    return ok & (d2 < stop * stop * np.where(n2 > 0, n2, 1.0))


def perdir(res):
    """Per direction: converged fraction (DD4c) and converged masks."""
    fr, masks = [], []
    for g1, g2, f1, f2 in zip(res["g"], res["g2"], res["f"], res["f2"], strict=True):
        cv = converged_cells(g1, g2, f1, f2)
        ok = (f1 == 0) & (f2 == 0)
        fr.append(float(cv.sum() / max(ok.sum(), 1)))
        masks.append(cv)
    return fr, masks


# -- truth error ----------------------------------------------------------------------


def truth_products(truth, m, nint, nb_total):
    """P-bar per (interval, pair, hand) for one direction's truth gains
    (nblock, nant, 2), m blocks per interval (DD5: mean over the truth
    blocks inside the interval)."""
    nant = truth.shape[1]
    p, q = np.triu_indices(nant, 1)
    pt = truth[:, p] * np.conj(truth[:, q])  # (nblock, npair, 2)
    out = np.zeros((nint,) + pt.shape[1:], complex)
    for j in range(nint):
        out[j] = pt[j * m : min((j + 1) * m, nb_total)].mean(0)
    return out


def e_dir(g, f, truth_d, m, conv=None):
    """DD5's e_d for one solved direction against one truth direction:
    median |P - P-bar| / |P-bar| over unflagged (and, with conv, converged in
    both antennas) cells, pairs and hands."""
    nint, nant = g.shape[:2]
    p, q = np.triu_indices(nant, 1)
    pbar = truth_products(truth_d, m, nint, truth_d.shape[0])
    ps = g[:, p] * np.conj(g[:, q])
    rel = np.abs(ps - pbar) / np.abs(pbar)
    ok = (f[:, p] == 0) & (f[:, q] == 0)
    if conv is not None:
        ok &= conv[:, p] & conv[:, q]
    v = rel[np.broadcast_to(ok[..., None], rel.shape)]
    return float(np.median(v)) if v.size else float("nan")


def ehat_dir(S, blocks, m, d, k):
    """DD5's e-hat from the sums: Var g_p = 1 / sum A_dd/(2k) over p's
    baselines in the interval; 0.83 x median sqrt(Var p + Var q)."""
    nant = S.nant
    rel = np.asarray(blocks) - blocks[0]
    iv = rel // m
    nint = int(iv.max()) + 1
    info = np.zeros((nint, nant, 2))
    Add = S.A[blocks][..., d, d].real  # (nb, nbl, 2)
    for side in (S.p, S.q):
        for h in range(2):
            np.add.at(info[:, :, h], (iv[:, None].repeat(S.nbl, 1), np.broadcast_to(side, (len(blocks), S.nbl))),
                      Add[..., h] / (2 * k))  # fmt: skip
    var = np.where(info > 0, 1.0 / np.where(info > 0, info, 1.0), np.inf)
    p, q = np.triu_indices(nant, 1)
    e = np.sqrt(var[:, p] + var[:, q])
    e = e[np.isfinite(e)]
    return float(0.83 * np.median(e)) if e.size else float("nan")


def amp_tail(g, f):
    a = np.abs(g)[np.broadcast_to((f == 0)[..., None], g.shape)]
    return {
        "p99": float(np.percentile(a, 99)),
        "max": float(a.max()),
        "cells_gt10": int((a > 10).sum()),
    }


# -- the robust held-out score --------------------------------------------------------


def predicted_power(S, blocks, sol_g, sol_m, bl):
    """Per (block, held-out baseline, hand): sum w|r|^2 from the sums at the
    gains (list per direction, flagged already 1)."""
    A = S.A[blocks][:, bl]
    bv = S.b[blocks][:, bl]
    s = S.s[blocks][:, bl]
    rel = np.asarray(blocks) - blocks[0]
    C = []
    for d in range(S.ndir):
        iv = np.minimum(rel // sol_m[d], sol_g[d].shape[0] - 1)
        gp, gq = sol_g[d][iv][:, S.p[bl]], sol_g[d][iv][:, S.q[bl]]
        C.append(gp * np.conj(gq))
    C = np.stack(C, -1)  # (nb, nbh, 2, D)
    cross = (np.conj(C) * bv).sum(-1).real
    quad = np.einsum("xyhd,xyhde,xyhe->xyh", np.conj(C), A, C).real
    return s - 2 * cross + quad


def gain_valid(S, blocks, sol_f, sol_m, bl):
    rel = np.asarray(blocks) - blocks[0]
    ok = np.ones((len(blocks), len(bl)), bool)
    for d in range(len(sol_f)):
        iv = np.minimum(rel // sol_m[d], sol_f[d].shape[0] - 1)
        fl = sol_f[d][iv] != 0
        ok &= ~fl[:, S.p[bl]] & ~fl[:, S.q[bl]]
    return ok


def bootstrap_median(diff, n=BOOT["n"], seed=BOOT["seed"], level=BOOT["level"]):
    """Median of per-baseline differences and its percentile bootstrap
    interval over baselines; significant if the interval excludes 0."""
    diff = np.asarray(diff, float)
    diff = diff[np.isfinite(diff)]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diff), (n, len(diff)))
    meds = np.median(diff[idx], axis=1)
    lo, hi = np.percentile(meds, [50 * (1 - level), 100 - 50 * (1 - level)])
    return {"median": float(np.median(diff)), "lo": float(lo), "hi": float(hi),
            "significant": bool(lo > 0 or hi < 0)}  # fmt: skip


def trimmed_mean(x, cut=TRIM):
    x = np.sort(np.asarray(x, float)[np.isfinite(x)])
    k = math.floor(cut * len(x))
    return float(x[k : len(x) - k].mean()) if len(x) > 2 * k else float("nan")


def robust_score(S_score, blocks, sols, held_bl, k):
    """Section 6: sols {name: (g list, f list, m list)} on the same cells;
    per-baseline H_b, its median and trimmed mean, and pair readings."""
    valid = np.ones((len(blocks), len(held_bl)), bool)
    for g, f, m in sols.values():
        valid &= gain_valid(S_score, blocks, f, m, held_bl)
    n = S_score.n[blocks][:, held_bl] * valid[..., None]
    N = n.sum((0, 2))
    keepb = N > 0
    Hb = {}
    for name, (g, f, m) in sols.items():
        g1 = [
            np.where((ff != 0)[..., None], 1.0, gg) for gg, ff in zip(g, f, strict=True)
        ]
        pw = predicted_power(S_score, blocks, g1, m, held_bl) * valid[..., None]
        Hb[name] = (pw.sum((0, 2)) / (2 * k))[keepb] / N[keepb]
    rec = {
        "baselines": int(keepb.sum()),
        "blocks_dropped_fraction": float(1 - valid.mean()),
        "solutions": {},
        "pairs": {},
    }
    for name, h in Hb.items():
        rec["solutions"][name] = {"median": float(np.median(h)), "trimmed_mean": trimmed_mean(h),
                                  "mean": float(h.mean())}  # fmt: skip
    names = list(Hb)
    for i, a in enumerate(names):
        for bname in names[i + 1 :]:
            r = bootstrap_median(Hb[a] - Hb[bname])
            r["reading"] = (f"{bname} predicts better" if r["significant"] and r["median"] > 0
                            else f"{a} predicts better" if r["significant"] else "no difference")  # fmt: skip
            rec["pairs"][f"{a} - {bname}"] = r
    return rec, Hb


# -- linearised rate (section 4) ------------------------------------------------------


class Local:
    """One interval and hand of a common-interval Problem, as a batched map
    F(g) on the free gains (flagged fixed at 1)."""

    def __init__(self, P, j, h, free):
        S = P.S
        sel = P.iv[0] == j
        self.A = P.A[sel][..., h, :, :]  # (nbk, nbl, D, D)
        self.b = P.bv[sel][..., h, :]
        self.p, self.q, self.nant, self.D = S.p, S.q, S.nant, P.D
        self.free = free  # (nant, D) bool
        nbl = len(S.p)
        self.Ep = np.zeros((self.nant, nbl))
        self.Eq = np.zeros((self.nant, nbl))
        self.Ep[S.p, np.arange(nbl)] = 1
        self.Eq[S.q, np.arange(nbl)] = 1

    def normal(self, G, dirs=None):
        """G (K, nant, D): jhr, jhj (K, nant, D) for the directions `dirs`."""
        gp, gq = G[:, self.p], G[:, self.q]  # (K, nbl, D)
        C = gp * np.conj(gq)
        dirs = range(self.D) if dirs is None else dirs
        jhr = np.zeros(G.shape, complex)
        jhj = np.zeros(G.shape)
        for d in dirs:
            R = self.b[None, ..., d] - np.einsum("xye,kye->kxy", self.A[..., d, :], C)
            Rs = R.sum(1)  # sum over blocks with gains common: R (K, nbk, nbl)
            Add = self.A[..., d, d].real.sum(0)  # (nbl,)
            jhr[..., d] = (gq[..., d] * Rs) @ self.Ep.T + (
                gp[..., d] * np.conj(Rs)
            ) @ self.Eq.T
            jhj[..., d] = (np.abs(gq[..., d]) ** 2 * Add) @ self.Ep.T + (
                np.abs(gp[..., d]) ** 2 * Add
            ) @ self.Eq.T
        return jhr, jhj

    def F(self, G, variant="default"):
        G = G.copy()
        if variant == "I2":
            for d in range(self.D):
                jhr, jhj = self.normal(G, [d])
                u = jhr[..., d] / np.where(jhj[..., d] > 0, jhj[..., d], 1)
                G[..., d] = np.where(
                    self.free[None, :, d], G[..., d] + 0.5 * u, G[..., d]
                )
            return G
        jhr, jhj = self.normal(G)
        if variant == "I3":
            H = self.joint(G)
            fm = self.free[None]
            Hm = np.where(fm[..., :, None] & fm[..., None, :], H, 0.0) + np.where(
                fm[..., :, None] & fm[..., None, :], 0.0, np.eye(self.D)
            )
            u = np.linalg.solve(Hm, np.where(fm, jhr, 0.0)[..., None])[..., 0]
        else:
            u = jhr / np.where(jhj > 0, jhj, 1)
        return np.where(self.free[None], G + 0.5 * u, G)

    def joint(self, G):
        gp, gq = G[:, self.p], G[:, self.q]
        As = self.A.sum(0)  # (nbl, D, D)
        vp = gq[..., :, None] * np.conj(gq[..., None, :]) * As[None]
        vq = gp[..., :, None] * np.conj(gp[..., None, :]) * np.conj(As)[None]
        out = np.tensordot(self.Ep, vp, axes=([1], [1])) + np.tensordot(
            self.Eq, vq, axes=([1], [1])
        )  # (nant, K, D, D)
        return out.transpose(1, 0, 2, 3)


def jacobian(loc, g0, variant="default", rel_step=1e-6, chunk=64):
    """Real Jacobian of F at g0 (nant, D) on the free gains, central
    differences; coordinates [Re g_free, Im g_free]."""
    fi = np.flatnonzero(loc.free.ravel())
    nf = len(fi)
    x0 = g0.ravel()
    J = np.zeros((2 * nf, 2 * nf))
    hs = rel_step * np.maximum(np.abs(x0[fi]), 1.0)
    cols = [(k, 1.0) for k in range(nf)] + [(k, 1j) for k in range(nf)]
    for c0 in range(0, 2 * nf, chunk):
        batch = cols[c0 : c0 + chunk]
        Gp = np.repeat(x0[None], len(batch), 0)
        Gm = Gp.copy()
        for i, (k, unit) in enumerate(batch):
            Gp[i, fi[k]] += unit * hs[k]
            Gm[i, fi[k]] -= unit * hs[k]
        shape = (len(batch),) + g0.shape
        Fp = loc.F(Gp.reshape(shape), variant).reshape(len(batch), -1)[:, fi]
        Fm = loc.F(Gm.reshape(shape), variant).reshape(len(batch), -1)[:, fi]
        for i, (k, _) in enumerate(batch):
            dv = (Fp[i] - Fm[i]) / (2 * hs[k])
            J[:nf, c0 + i] = dv.real
            J[nf:, c0 + i] = dv.imag
    return J, fi


def gauge_projector(g0, fi, D):
    """Projector off the per-direction phase gauges i g_.,d (real coords)."""
    x = g0.ravel()[fi]
    nf = len(fi)
    dirs = fi % D
    V = []
    for d in range(D):
        v = np.where(dirs == d, 1j * x, 0)
        if np.any(v):
            V.append(np.concatenate([v.real, v.imag]))
    V = np.array(V).T
    return np.eye(2 * nf) - V @ np.linalg.pinv(V)


def spectral_radius(J, P):
    ev = np.linalg.eigvals(P @ J @ P)
    return float(np.abs(ev).max())


# -- io -------------------------------------------------------------------------------


def write_json(path, rec):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, default=float))


def k_noise():
    return json.loads((DD7_ROOT / "b" / "setup.json").read_text())["dd5"]["k"]


def stack_sol(g, f):
    """Common-interval lists -> Rust layout (nint, 1, nant, D, 2), (nint, 1, nant, D)."""
    return np.stack(g, -2)[:, None], np.stack(f, -1)[:, None]


def from_rust(npz):
    z = np.load(npz)
    g, f = np.asarray(z["gains"])[:, 0], np.asarray(z["flags"])[:, 0]
    conv = np.asarray(z["converged"])[:, 0] if "converged" in z.files else None
    return g, f, conv


def product_diff(ga, gb, ca, cb):
    """max |g_p conj g_q (a) - (b)| per direction on cells converged in both
    (both antennas, both solutions); median too."""
    nant = ga.shape[1]
    p, q = np.triu_indices(nant, 1)
    out = []
    for d in range(ga.shape[2]):
        pa = ga[:, p, d] * np.conj(ga[:, q, d])
        pb = gb[:, p, d] * np.conj(gb[:, q, d])
        ok = ca[:, p, d] & ca[:, q, d] & cb[:, p, d] & cb[:, q, d]
        v = np.abs(pa - pb)[np.broadcast_to(ok[..., None], pa.shape)]
        out.append({"max": float(v.max()) if v.size else None, "median": float(np.median(v)) if v.size else None,
                    "p99": float(np.percentile(v, 99)) if v.size else None, "cells": int(ok.sum())})  # fmt: skip
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "sums":
        sums(argv[1], argv[2], argv[3])
    else:
        runs = _load("dd9_runs", HERE / "runs.py")
        getattr(runs, cmd)(*argv[1:])


if __name__ == "__main__":
    main()
