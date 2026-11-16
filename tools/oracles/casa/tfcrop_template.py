# SPDX-License-Identifier: GPL-3.0-or-later
"""Candidate models of CASA's tfcrop band template (research/v8c-tfcrop-poly.md,
section 3), parametrised so that probe readouts can rank them. Not the
reference (that is rang.tfcrop); a search space.
"""

import itertools

import numpy as np


def smooth_inplace(y, hw=2):
    """Running mean of 2*hw+1 points over channels hw..n-hw-1 in increasing
    order, in place: already smoothed values enter later windows (c06)."""
    y = np.array(y, float)
    n = len(y)
    w = 2 * hw + 1
    for f in range(hw, n - hw):
        y[f] = y[f - hw : f + hw + 1].sum() / w
    return y


def lsq(x, y, w, deg):
    k = int(w.sum())
    if k == 0:
        return np.zeros_like(y)
    deg = min(deg, k - 1)
    return np.polyval(np.polyfit(x[w], y[w], deg), x)


OPTS = {"overlap": 1, "overlap_left": 0, "edges": "centred"}


def piece_edges(n, npieces):
    """c05: pieces of floor(n / npieces) channels, the remainder split
    floor/ceil between the first and the last piece (7 pieces of 256:
    0, 38, 74, ..., 218, 256; 3 pieces: 0, 85, 170, 256)."""
    if OPTS["edges"] == "round":
        return np.linspace(0, n, npieces + 1).round().astype(int)
    w = n // npieces
    off = (n - npieces * w) // 2
    return np.array([0] + [off + k * w for k in range(1, npieces)] + [n])


def pieces(y, w, npieces, deg):
    """Cubics on pieces [lo, hi) (edges round(k n / npieces)); each piece's
    fit also uses OPTS['overlap'] channels past its right edge (c06)."""
    n = len(y)
    x = np.arange(n, dtype=float)
    out = np.empty(n)
    edges = piece_edges(n, npieces)
    ov = OPTS["overlap"]
    for lo, hi in itertools.pairwise(edges):
        h = min(n, hi + ov)
        l0 = max(0, lo - OPTS["overlap_left"])
        xs, ys, ws = x[l0:h], y[l0:h], w[l0:h]
        last = OPTS.get("last", "none")
        if hi == n and last != "none":
            if last == "drop1":
                xs, ys, ws = xs[:-1], ys[:-1], ws[:-1]
            elif last.startswith("phantom"):
                val = {"phantom0": 0.0, "phantomlast": y[n - 1]}[last]
                xs, ys, ws = np.r_[xs, n], np.r_[ys, val], np.r_[ws, True]
            elif last == "left1":
                xs, ys, ws = x[l0 - 1:h], y[l0 - 1:h], w[l0 - 1:h]
        c = np.polyfit(xs[ws], ys[ws], min(deg, int(ws.sum()) - 1)) if ws.any() else np.zeros(1)
        out[lo:hi] = np.polyval(c, x[lo:hi])
    return out


def schedule(kind, maxnp, rule):
    if kind == "line":
        return [(1, 1)] * 5
    m = max(1, int(maxnp))
    if rule == "full":
        return list(OPTS["sched_full"][m])
    if rule == "custom":
        return [(1, 1)] * OPTS.get("nline", 1) + [(p, 3) for p in OPTS["sched"][m]]
    if rule == "line-then-max":
        return [(1, 1)] + [(m, 3)] * 4
    if rule == "inc":  # 1 (line), then 1, 2, ..., m cubic pieces
        return [(1, 1)] + [(min(m, s), 3) for s in range(1, 12)]
    if rule == "inc0":  # line, then 2, 3, ... pieces
        return [(1, 1)] + [(min(m, s + 1), 3) for s in range(1, 5)]
    if rule == "lin":  # pieces grow linearly to m over the 5 stages
        return [(1, 1)] + [(max(1, round(m * s / 4)), 3) for s in range(1, 5)]
    raise ValueError(rule)


def template(avg, valid, kind="poly", maxnp=7, rule="inc", clip=2.0, stop=0.1,
             stoprel=True, resid="abs", sdabout="zero", smooth=True, smooth_each=True,
             nstages=5, sd_over="kept", excl="drop", resid_of="F", keep_prev=False,
             cum=False):
    n = len(avg)
    x = np.arange(n, dtype=float)
    w = valid.copy()
    prev = None
    F = np.zeros(n)
    y = np.array(avg, float)
    Fold = F
    sch = schedule(kind, maxnp, rule)
    sch = (sch + [sch[-1]] * 12)[:nstages]
    for s, (p, deg) in enumerate(sch):
        if excl == "replace":
            fitw, yy = valid, y
        else:
            fitw, yy = w, avg
        P = lsq(x, yy, fitw, deg) if p == 1 else pieces(yy, fitw, p, deg)
        Fold = F
        F = smooth_inplace(P) if (smooth and (smooth_each or s == nstages - 1)) else P
        G = F if resid_of == "F" else P
        r = avg - G if resid == "abs" else np.where(G != 0, avg / G - 1, 0.0)
        sel = w if sd_over == "kept" else valid
        if not sel.any():
            break
        rr = r[sel]
        sd = float(np.sqrt(np.mean(rr**2))) if sdabout == "zero" else float(np.std(rr))
        if prev is not None:
            ch = abs(sd - prev)
            if (ch < stop * prev) if stoprel else (ch < stop):
                if keep_prev:
                    F = Fold
                break
        prev = sd
        thr = clip * sd
        if OPTS.get("sd_scope", "global") == "piece" and p > 1:
            e = piece_edges(n, p)
            thr = np.empty(n)
            ovr = OPTS["overlap"] if OPTS.get("sd_overlap", True) else 0
            for lo, hi in itertools.pairwise(e):
                h = min(n, hi + ovr)
                ww = sel[lo:h] if isinstance(sel, np.ndarray) else np.ones(h - lo, bool)
                rr2 = r[lo:h][ww]
                thr[lo:hi] = clip * (np.sqrt(np.mean(rr2**2)) if len(rr2) else 0.0)
        w = (w if cum else valid) & (r <= thr)
        if excl == "replace":
            y = np.where(w, avg, G)
        elif excl == "replace-cum":
            y = np.where(w, y, G)
    if smooth and not smooth_each:
        F = smooth_inplace(F)
    return F
