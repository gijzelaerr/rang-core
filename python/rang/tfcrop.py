# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA's `flagdata(mode='tfcrop')` (research/v8-tfcrop.md; V8b's first
attempt in research/v8b-flagdata.md, section 9.3).

Per (chunk, baseline, correlation) time-frequency plane of the selected
values (amplitudes for `ABS`), as casadocs 6.7 describes tfcrop: average the
unflagged values along one axis, fit a robust line or piecewise polynomial
to the average ("the base of RFI spikes"), divide it out, and flag the
points whose relative deviation exceeds the cutoff times the per-row
standard deviation; then the other axis. No CASA source was read: every
choice the documentation leaves open is set from CASA's output on probe MSs
and is named in section 7 of the note (D1, D2, ...).

`plane` is the NumPy reference; `flag_chunk` runs it over a chunk, or the
Rust kernel `rang._core.tfcrop` when `TF["kernel"] == "rust"`.
"""

from __future__ import annotations

import itertools

import numpy as np

# tfcrop is not at parity with CASA (research/v8-tfcrop.md, section 5):
# rang.tasks.flagdata refuses mode='tfcrop' unless this is set True (the
# probe and gate harnesses do; nothing else should).
ENABLED = False

TF = {
    "kernel": "numpy",
    # D2: the robust line is a least-squares line refitted LINE_FITS - 1
    # times to the points whose residual is at most FIT_CLIP times the rms
    # residual (one-sided: points above the fit are left out).
    "line_fits": 3,
    "fit_clip": 2.0,
    # The piecewise polynomial (not identified yet): stage schedule.
    "poly_degree": 3,
    # D1: per-row passes stop when the sd changes by less than this
    # (absolute; the previous sd starts at 0); at most `passes`.
    "row_tol": 0.1,
    "passes": 5,
}


def _lsq(x, y, w, deg):
    n = int(w.sum())
    if n == 0:
        return np.zeros_like(y)
    deg = min(deg, n - 1)
    co = np.polyfit(x[w], y[w], deg)
    return np.polyval(co, x)


def _pieces(y, w, npieces, deg):
    n = len(y)
    x = np.arange(n, dtype=np.float64)
    out = np.empty(n)
    edges = np.linspace(0, n, npieces + 1).round().astype(int)
    for lo, hi in itertools.pairwise(edges):
        out[lo:hi] = _lsq(x[lo:hi], y[lo:hi], w[lo:hi], deg)
    return out


def _schedule(kind, maxnpieces):
    """(npieces, degree) of each fit stage."""
    if kind == "line":
        return [(1, 1)] * TF["line_fits"]
    deg = TF["poly_degree"]
    return [(1, 1)] + [(max(1, int(maxnpieces)), deg)] * (TF["line_fits"] - 1)


def robust_fit(avg, valid, kind, maxnpieces):
    """The band template of a 1-D average `avg` over its `valid` points
    (D2 for 'line'; the 'poly' schedule is provisional)."""
    x = np.arange(len(avg), dtype=np.float64)
    w = valid.copy()
    fit = np.zeros_like(avg)
    for p, deg in _schedule(kind, maxnpieces):
        fit = _lsq(x, avg, w, deg) if p == 1 else _pieces(avg, w, p, deg)
        res = avg - fit
        if not w.any():
            break
        sd = float(np.sqrt(np.mean(res[w] ** 2)))
        w = valid & (res <= TF["fit_clip"] * sd)
    return fit


def row_flags(u, live, cut):
    """D1: per row of `u` (relative deviations), sd = sqrt(mean u^2) over
    its live points; flag |u| > cut * sd; repeat on the rest, a row
    stopping when its sd changes by less than `row_tol` (absolute) from the
    previous pass, the previous value starting at 0."""
    new = np.zeros(u.shape, bool)
    done = np.zeros((u.shape[0], 1), bool)
    prev = np.zeros((u.shape[0], 1))
    for _ in range(TF["passes"]):
        ok = live & ~new
        cnt = ok.sum(axis=1, keepdims=True)
        sd = np.sqrt(np.where(ok, u * u, 0.0).sum(axis=1, keepdims=True)
                     / np.maximum(cnt, 1))  # fmt: skip
        new |= ok & (np.abs(u) > cut * sd) & ~done & (cnt > 0)
        done |= np.abs(sd - prev) < TF["row_tol"]
        prev = sd
        if done.all():
            break
    return new


def _pass(a, flag, axis, cutoff, fitkind, npieces):
    """One direction. axis=0 is 'freq': the mean over time of the unflagged
    points of each channel (the band) is fitted across channels and the
    rows are times; axis=1 is 'time', the same with the axes exchanged."""
    if axis == 1:
        return _pass(a.T, flag.T, 0, cutoff, fitkind, npieces).T
    live = ~flag
    cnt = live.sum(axis=0)
    avg = np.where(live, a, 0.0).sum(axis=0) / np.maximum(cnt, 1)
    fit = robust_fit(avg, cnt > 0, fitkind, npieces)
    with np.errstate(invalid="ignore", divide="ignore"):
        u = np.where(fit[None, :] != 0, a / fit[None, :] - 1.0, 0.0)
    return row_flags(u, live, cutoff)


def plane(a, flag, params):
    """New flags of one (time, channel) plane `a` with existing `flag`."""
    if params.get("usewindowstats", "none") not in ("none", None, ""):
        # Window statistics are not identified (research/v8-tfcrop.md,
        # section 7): refuse rather than ignore them.
        raise NotImplementedError("tfcrop: usewindowstats is not identified yet")
    dims = params.get("flagdimension", "freqtime")
    order = {"freq": ("freq",), "time": ("time",), "freqtime": ("freq", "time"),
             "timefreq": ("time", "freq")}[dims]  # fmt: skip
    new = np.zeros_like(flag)
    for d in order:
        if d == "freq":
            new |= _pass(a, flag | new, 0, float(params.get("freqcutoff", 3.0)),
                         params.get("freqfit", "poly"), int(params.get("maxnpieces", 7)))  # fmt: skip
        else:
            new |= _pass(a, flag | new, 1, float(params.get("timecutoff", 4.0)),
                         params.get("timefit", "line"), int(params.get("maxnpieces", 7)))  # fmt: skip
    return new


def flag_chunk(values, flag, cells, a1, a2, time, chunk, params):
    """New flags (bool, like `flag`) of the rows of one batch of whole
    chunks: every (chunk, baseline) group in time order, every selected
    correlation, the selected channels."""
    out = np.zeros_like(flag)
    key = np.stack([chunk, a1, a2], axis=1)
    _, group = np.unique(key, axis=0, return_inverse=True)
    group = group.reshape(-1)
    chans = cells.any(axis=(0, 2))
    corrs = cells.any(axis=(0, 1))
    for g in range(group.max() + 1 if len(group) else 0):
        rows = np.flatnonzero(group == g)
        rows = rows[np.argsort(time[rows], kind="stable")]
        for c in np.flatnonzero(corrs):
            a = np.asarray(values[rows][:, chans, c], np.float64)
            f = flag[rows][:, chans, c] | ~np.isfinite(a)
            a = np.where(np.isfinite(a), a, 0.0)
            new = plane(a, f, params)
            sub = out[rows]
            sub[:, np.flatnonzero(chans), c] |= new
            out[rows] = sub
    return out
