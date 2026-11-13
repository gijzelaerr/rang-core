# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA's `flagdata(mode='tfcrop')` (task V8b, research/v8b-flagdata.md).

Per (chunk, baseline, correlation) time-frequency plane of the selected
values (amplitudes for `ABS`), as casadocs 6.7 describes tfcrop: average
along one axis, fit a robust line or piecewise polynomial to the average,
flag the points that deviate from the fit by more than the cutoff times the
standard deviation of (data - fit), up to five iterations; then the other
axis; optional sliding-window statistics. No CASA source was read: each
choice the documentation leaves open is a `TF` entry, set from CASA's output
on probe MSs (section 9 of the note).

`plane` is the NumPy reference; `flag_chunk` runs it over a chunk, or the
Rust kernel `rang._core.tfcrop` when `TF["kernel"] == "rust"`.
"""

from __future__ import annotations

import itertools

import numpy as np

TF = {
    "kernel": "numpy",
    "iterations": 1,
    "sign": "positive",  # "positive": data - fit > cut * sd; "abs": |data - fit|
    "sd": "rms",  # "rms" of (data - fit) over unflagged points, or "std" (mean removed)
    "poly_degree": 3,  # degree of each piece of the piecewise polynomial
    "fit_clip": 3.0,  # robust fit: points beyond fit_clip * sd excluded
    "fit_iterations": 1,
}


def _fit_line(x, y, w):
    if w.sum() < 2:
        return np.full_like(y, np.nan if not w.any() else y[w].mean())
    a = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(a[w], y[w], rcond=None)
    return a @ coef


def _fit_poly(x, y, w, npieces, degree):
    out = np.full_like(y, np.nan)
    n = len(x)
    npieces = max(1, min(int(npieces), n // max(degree + 1, 1)))
    edges = np.linspace(0, n, npieces + 1).round().astype(int)
    for lo, hi in itertools.pairwise(edges):
        xs, ys, ws = x[lo:hi], y[lo:hi], w[lo:hi]
        if ws.sum() <= degree:
            out[lo:hi] = ys[ws].mean() if ws.any() else np.nan
            continue
        coef = np.polyfit(xs[ws], ys[ws], degree)
        out[lo:hi] = np.polyval(coef, xs)
    return out


def robust_fit(y, valid, kind, npieces, cutoff):
    """A fit of `y` (1-D) over `valid` points (`fit_iterations` refits
    after excluding points more than `fit_clip` sd from the fit)."""
    x = np.arange(len(y), dtype=np.float64)
    w = valid.copy()
    fit = np.zeros_like(y)
    for _ in range(TF["fit_iterations"]):
        if kind == "line":
            fit = _fit_line(x, y, w)
        else:
            fit = _fit_poly(x, y, w, npieces, TF["poly_degree"])
        res = y - fit
        if not w.any():
            break
        sd = _sd(res[w])
        new = valid & (np.abs(res) <= TF["fit_clip"] * sd)
        if np.array_equal(new, w):
            break
        w = new
    return fit


def _sd(res):
    if not len(res):
        return 0.0
    if TF["sd"] == "std":
        return float(np.std(res))
    return float(np.sqrt(np.mean(res * res)))


def _pass(a, flag, axis, cutoff, fitkind, npieces, winstats, halfwin):
    """One direction (section 9, F1). axis=0 is 'freq': the mean over time
    of the unflagged points of each channel (the band) is fitted across
    channels; each point's relative deviation r = data / fit - 1 is
    compared with `cutoff` times the rms of r over the unflagged channels of
    its own time row. axis=1 is 'time', the same with the axes exchanged:
    the mean over channels of each time is fitted in time, and the rms is
    over the unflagged times of each channel. Two-sided."""
    new = np.zeros_like(flag)
    for _ in range(TF["iterations"]):
        live = ~(flag | new)
        cnt = live.sum(axis=axis)
        avg = np.where(live, a, 0.0).sum(axis=axis) / np.maximum(cnt, 1)
        valid = cnt > 0
        fit = robust_fit(avg, valid, fitkind, npieces, cutoff)
        model = fit[None, :] if axis == 0 else fit[:, None]
        with np.errstate(invalid="ignore", divide="ignore"):
            res = np.where(model != 0, a / model - 1.0, 0.0)
        other = 1 - axis
        n = live.sum(axis=other, keepdims=True)
        sd = np.sqrt(np.where(live, res * res, 0.0).sum(axis=other, keepdims=True)
                     / np.maximum(n, 1))  # fmt: skip
        hit = live & (np.abs(res) > cutoff * sd) & (n > 0)
        if winstats in ("sum", "both", "std"):
            hit |= live & _window_flags(res, live, axis, cutoff, sd, halfwin, winstats)
        if not hit.any():
            break
        new |= hit
    return new


def _window_flags(res, live, axis, cutoff, sd, halfwin, mode):
    """Sliding windows of 2 * halfwin + 1 points along the axis the fit runs
    over (channels for 'freq', times for 'time'): 'sum' flags a point whose
    window mean of r exceeds cutoff / 2 times the sd, 'std' one whose
    window standard deviation of r does; 'both' either (casadocs)."""
    along = 1 if axis == 0 else 0
    r = np.where(live, res, np.nan)
    n = r.shape[along]
    stack = []
    for k in range(-halfwin, halfwin + 1):
        idx = np.clip(np.arange(n) + k, 0, n - 1)
        valid = (np.arange(n) + k >= 0) & (np.arange(n) + k < n)
        part = np.take(r, idx, axis=along)
        shape = [1, 1]
        shape[along] = n
        stack.append(np.where(valid.reshape(shape), part, np.nan))
    win = np.stack(stack)
    hit = np.zeros(live.shape, bool)
    with np.errstate(invalid="ignore"), _quiet():
        if mode in ("sum", "both"):
            hit |= np.abs(np.nanmean(win, axis=0)) > cutoff / 2.0 * sd
        if mode in ("std", "both"):
            hit |= np.nanstd(win, axis=0) > cutoff / 2.0 * sd
    return hit & live


def _quiet():
    import warnings

    ctx = warnings.catch_warnings()
    ctx.__enter__()
    warnings.simplefilter("ignore", RuntimeWarning)

    class _Done:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            ctx.__exit__(*exc)

    return _Done()


def plane(a, flag, params):
    """New flags of one (time, channel) plane `a` with existing `flag`."""
    dims = params.get("flagdimension", "freqtime")
    order = {"freq": ("freq",), "time": ("time",), "freqtime": ("freq", "time"),
             "timefreq": ("time", "freq")}[dims]  # fmt: skip
    new = np.zeros_like(flag)
    for d in order:
        if d == "freq":
            new |= _pass(a, flag | new, 0, float(params.get("freqcutoff", 3.0)),
                         params.get("freqfit", "poly"), int(params.get("maxnpieces", 7)),
                         params.get("usewindowstats", "none"), int(params.get("halfwin", 1)))  # fmt: skip
        else:
            new |= _pass(a, flag | new, 1, float(params.get("timecutoff", 4.0)),
                         params.get("timefit", "line"), int(params.get("maxnpieces", 7)),
                         params.get("usewindowstats", "none"), int(params.get("halfwin", 1)))  # fmt: skip
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
