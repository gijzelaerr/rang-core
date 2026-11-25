# SPDX-License-Identifier: MIT
"""Empirical re-weighting after apply (issue #55, research/apply-reweight.md):
a statwt-like stage, `apply.reweight`, off by default.

Per baseline, time block (a scan, or `timebin` seconds within one) and block of
`chanbin` channels, the variance of the noise is estimated from CORRECTED_DATA:

- `stokes_v`: V = (XY - YX) / (2i), pure noise on linear feeds with an empty V
  sky; the per-correlation variance is `2 var(V)`, one weight for all four;
- `residual`: CORRECTED_DATA - MODEL_DATA per correlation, as CASA's
  `statwt(datacolumn='residual')`.

A block's variance is `(var_re + var_im) / 2` (statwt's), by `classic` (statwt's
estimator, divisor N), `mad` (`(1.4826 MAD)^2`, robust to RFI residue) or
`clipped` (issue #48, research/weights-48.md: an iteratively 3-sigma clipped
variance with the exact truncation factor, as efficient as `classic` on
Gaussian noise and robust to large outliers), in the Rust core
(`rang_core::reweight`). Blocks with fewer than `minsamp` valid samples are
filled, in order: when `smooth > 0`, a running median of width `smooth` over the
group's blocks, then the group's median; when `fill` (issue #48), the same
baseline and channel block pooled over the field's scans (the count-weighted
mean of their estimates, when the pooled count reaches `minsamp`), then the
median over the scan's baselines of that channel block. What stays empty gets
weight 0. Weights `1 / variance` go to WEIGHT_SPECTRUM, and WEIGHT gets each
correlation's median over the row's weighted channels; flags are not changed
(statwt flags empty blocks).
"""

import time
import warnings
from dataclasses import dataclass

import numpy as np

MODES = ("off", "residual", "stokes_v")
STATISTICS = ("classic", "mad", "clipped")
XY, YX = 1, 2


@dataclass(frozen=True)
class Settings:
    mode: str = "off"
    chanbin: int = 16
    timebin: str = "scan"
    statistic: str = "clipped"
    minsamp: int = 200
    smooth: int = 5
    fill: bool = True

    @classmethod
    def of(cls, cfg):
        s = cls(**{k: cfg[k] for k in cls.__dataclass_fields__ if k in cfg})
        s.check()
        return s

    def check(self):
        if self.mode not in MODES:
            raise ValueError(f"reweight.mode must be one of {MODES}")
        if self.statistic not in STATISTICS:
            raise ValueError(f"reweight.statistic must be one of {STATISTICS}")
        if int(self.chanbin) < 1 or int(self.minsamp) < 1 or int(self.smooth) < 0:
            raise ValueError(
                "reweight: chanbin and minsamp at least 1, smooth at least 0"
            )
        self.timebin_s()

    def timebin_s(self):
        """None for one block per scan, else the block length in seconds."""
        if self.timebin == "scan":
            return None
        text = str(self.timebin).removesuffix("s")
        try:
            value = float(text)
        except ValueError:
            raise ValueError(
                f"reweight.timebin {self.timebin!r}: scan or seconds, such as 120s"
            ) from None
        if not value > 0:
            raise ValueError("reweight.timebin must be positive")
        return value


def block_variances(values, valid, group, ngroup, chanbin, statistic, minsamp):
    """`(var, count)` of shape `(ngroup, nblock)` from complex `values`
    `(row, chan)`, boolean `valid` and `group` per row (the Rust kernel)."""
    from . import core

    ext = core.extension()
    values = np.ascontiguousarray(values, np.complex64)
    nchan = values.shape[1]
    nblock = -(-nchan // int(chanbin))
    var = np.zeros(ngroup * nblock, np.float64)
    count = np.zeros(ngroup * nblock, np.uint64)
    ext.reweight_variances(
        nchan, int(chanbin), int(ngroup), values.view(np.float32).reshape(-1),
        np.ascontiguousarray(valid, np.uint8).reshape(-1),
        np.ascontiguousarray(group, np.uint32), statistic, int(minsamp), var, count,
    )  # fmt: skip
    return var.reshape(ngroup, nblock), count.reshape(ngroup, nblock)


def regularise(var, smooth):
    """Fill NaN blocks along the channel axis: a running median of width
    `smooth` (NaNs ignored), then each group's median; `smooth == 0` leaves
    them NaN (weight 0). Groups without any finite block stay NaN."""
    if not smooth:
        return var
    out = var.copy()
    n = var.shape[1]
    half = int(smooth) // 2
    for g in range(var.shape[0]):
        row = var[g]
        if not np.isfinite(row).any():
            continue
        sm = np.array(
            [_nanmedian(row[max(0, i - half) : i + half + 1]) for i in range(n)]
        )
        sm = np.where(np.isfinite(sm), sm, np.nanmedian(row))
        # Issue #48 revision R1 (research/weights-48.md section 9): only the NaN
        # blocks are filled, as this docstring says; #55's code replaced every
        # block by the running median, which flattens the channel shape.
        out[g] = np.where(np.isfinite(row), row, sm)
    return out


def _nanmedian(x):
    x = x[np.isfinite(x)]
    return np.median(x) if x.size else np.nan


def _groups(ms_rows, a1, a2, times, scans, timebin, fields=None):
    """Group index per row: (scan, time block, baseline) in sorted order, the
    number of groups, and the groups' keys `(ngroup, 5)`: field (0 without
    `fields`), scan, time block, antenna, antenna."""
    if timebin is None:
        tblock = np.zeros(len(times), np.int64)
    else:
        tblock = np.zeros(len(times), np.int64)
        for s in np.unique(scans):
            m = scans == s
            tblock[m] = np.floor((times[m] - times[m].min()) / timebin).astype(np.int64)
    lo, hi = np.minimum(a1, a2), np.maximum(a1, a2)
    key = np.stack([scans, tblock, lo, hi], 1)
    uniq, inverse = np.unique(key, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    fld = np.zeros(len(uniq), np.int64)
    if fields is not None and len(key):
        fld[inverse] = np.asarray(fields, np.int64)
    keys = np.concatenate([fld[:, None], uniq.reshape(-1, 4).astype(np.int64)], 1)
    ngroup = int(inverse.max()) + 1 if len(key) else 0
    return inverse.astype(np.uint32), ngroup, keys


def estimate(read, rows, settings, nchan, fit=None, chans_per_read=None, details=False):
    """Variances per (group, block[, correlation]) for the MS `rows` (one
    scan or several; groups never cross scans).

    `read(name, rows, chans)` reads a column, `chans` a slice of channels;
    the data are read `chans_per_read` channels at a time (a multiple of
    `chanbin`; default all). `fit` (research: held-out tests) is a boolean per
    row of the rows the statistics may use (default all). Returns
    `(group per row, var)`: var `(ngroup, nblock)` for `stokes_v` (the
    per-correlation variance `2 var(V)`) or `(ngroup, nblock, 4)` for
    `residual`, after `regularise`. With `details`, a third item: a dict with
    the groups' `keys` (`_groups`), the `raw` estimate of every block with a
    sample and its `count`, for `fill`."""
    rows = np.asarray(rows, np.int64)
    a1, a2 = read("ANTENNA1", rows, None), read("ANTENNA2", rows, None)
    times, scans = read("TIME", rows, None), read("SCAN_NUMBER", rows, None)
    fields = read("FIELD_ID", rows, None) if details else None
    group, ngroup, keys = _groups(rows, a1, a2, times, scans, settings.timebin_s(),
                                  fields)  # fmt: skip
    flag_row = read("FLAG_ROW", rows, None).astype(bool) | (a1 == a2)
    if fit is not None:
        flag_row = flag_row | ~np.asarray(fit, bool)
    cb, stat, ms_ = int(settings.chanbin), settings.statistic, int(settings.minsamp)
    step = nchan if not chans_per_read else max(cb, int(chans_per_read) // cb * cb)
    parts, counts = [], []
    for c0 in range(0, nchan, step):
        chans = slice(c0, min(nchan, c0 + step))
        corrected = read("CORRECTED_DATA", rows, chans)
        flag = read("FLAG", rows, chans).astype(bool) | flag_row[:, None, None]
        if settings.mode == "stokes_v":
            v = (corrected[..., XY] - corrected[..., YX]) / 2j
            ok = ~(flag[..., XY] | flag[..., YX])
            var, count = block_variances(v, ok, group, ngroup, cb, stat, 1)
            parts.append(2.0 * var)
            counts.append(count)
            continue
        res = corrected - read("MODEL_DATA", rows, chans)
        per, cnt = [], []
        for c in range(res.shape[-1]):
            var, count = block_variances(
                res[..., c], ~flag[..., c], group, ngroup, cb, stat, 1
            )
            per.append(var)
            cnt.append(count)
        parts.append(np.stack(per, -1))
        counts.append(np.stack(cnt, -1))
    raw = np.concatenate(parts, axis=1)
    count = np.concatenate(counts, axis=1)
    var = np.where(count >= max(1, ms_), raw, np.nan)
    if var.ndim == 2:
        var = regularise(var, settings.smooth)
    else:
        var = np.stack(
            [regularise(var[..., c], settings.smooth) for c in range(var.shape[-1])],
            -1,
        )
    if details:
        return group, var, {"keys": keys, "raw": raw, "count": count}
    return group, var


def fill(var, keys, raw, count, minsamp):
    """Fill the NaN blocks of `var` (the groups of several scans,
    concatenated; `keys` as `_groups`') in order: (1) the same field,
    baseline and channel block pooled over its groups in every scan and time
    block, the count-weighted mean of their `raw` estimates, when the pooled
    `count` reaches `minsamp`; (2) the median over the baselines of the same
    scan and time block of the finite values of that channel block. Returns
    `(var, filled)`, `filled` the number of blocks (per correlation) filled at
    each step."""
    var = var.copy()
    count = np.asarray(count)
    raw = np.where((count > 0) & np.isfinite(raw), raw, 0.0)
    filled = {"pooled": 0, "array": 0}
    if not len(keys):
        return var, filled
    _, bl = np.unique(keys[:, [0, 3, 4]], axis=0, return_inverse=True)
    bl = bl.reshape(-1)
    shape = (int(bl.max()) + 1, *var.shape[1:])
    wsum, csum = np.zeros(shape), np.zeros(shape)
    np.add.at(wsum, bl, raw * count)
    np.add.at(csum, bl, count.astype(np.float64))
    with np.errstate(invalid="ignore", divide="ignore"):
        pooled = np.where(csum >= max(1, int(minsamp)), wsum / csum, np.nan)
    hole = ~np.isfinite(var)
    take = hole & np.isfinite(pooled[bl])
    var[take] = pooled[bl][take]
    filled["pooled"] = int(take.sum())
    _, tb = np.unique(keys[:, [1, 2]], axis=0, return_inverse=True)
    tb = tb.reshape(-1)
    for t in np.unique(tb):
        m = tb == t
        block = var[m]
        hole = ~np.isfinite(block)
        if not hole.any():
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(block, axis=0)
        take = hole & np.isfinite(med)[None]
        block[take] = np.broadcast_to(med, block.shape)[take]
        var[m] = block
        filled["array"] += int(take.sum())
    return var, filled


def estimate_rows(read, rows, settings, nchan, fit=None, chans_for_scan=None):
    """`estimate` scan by scan over `rows`, then `fill` across the scans when
    `settings.fill`. `chans_for_scan(nrow)` gives the channels per read for a
    scan of `nrow` rows (default all); `fit` as `estimate`'s, per row of
    `rows`. Returns `(gid, var, filled)`: `gid` the group of each of `rows` (in
    `rows`' order) in the concatenated `var`."""
    rows = np.asarray(rows, np.int64)
    scans = read("SCAN_NUMBER", rows, None)
    gid = np.zeros(len(rows), np.int64)
    tables, keys, raws, counts, offset = [], [], [], [], 0
    for s in np.unique(scans):
        sel = np.flatnonzero(scans == s)
        step = chans_for_scan(len(sel)) if chans_for_scan else None
        group, var, extra = estimate(
            read, rows[sel], settings, nchan,
            fit=None if fit is None else np.asarray(fit, bool)[sel],
            chans_per_read=step, details=True,
        )  # fmt: skip
        gid[sel] = group.astype(np.int64) + offset
        offset += var.shape[0]
        tables.append(var)
        keys.append(extra["keys"])
        raws.append(extra["raw"])
        counts.append(extra["count"])
    filled = {"pooled": 0, "array": 0}
    if not tables:
        return gid, np.zeros((0, 1)), filled
    var = np.concatenate(tables, 0)
    if settings.fill:
        var, filled = fill(var, np.concatenate(keys, 0), np.concatenate(raws, 0),
                           np.concatenate(counts, 0), settings.minsamp)  # fmt: skip
    return gid, var, filled


def weights_of(var, group, nchan, chanbin, ncorr=4):
    """WEIGHT_SPECTRUM `(row, chan, corr)` float32 from `var` per group and
    block (`stokes_v`: one value for every correlation): `1 / var`, 0 where the
    variance is not finite or not positive."""
    with np.errstate(divide="ignore", invalid="ignore"):
        w = np.where(np.isfinite(var) & (var > 0), 1.0 / var, 0.0)
    block = np.arange(nchan) // int(chanbin)
    per = w[group][:, block]  # (row, chan[, corr])
    if per.ndim == 2:
        per = np.repeat(per[..., None], ncorr, axis=2)
    return per.astype(np.float32)


def row_weight(wsp, flag):
    """WEIGHT per row and correlation as CASA's statwt sets it: the median of
    the row's new weights over its unflagged channels with a positive weight
    (0 when none)."""
    use = (wsp > 0) & ~np.asarray(flag, bool)
    x = np.where(use, wsp.astype(np.float64), np.nan)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(x, axis=1)
    return np.where(use.any(1), med, 0.0).astype(np.float32)


# Bytes per cell-correlation an estimate holds at once (CORRECTED and MODEL
# complex64, FLAG, the residual or V), for sizing the channel slices.
READ_BYTES = 40


def chans_for(nrow, nchan, ncorr, chanbin, budget_bytes):
    """Channels per read so that one scan's slice fits `budget_bytes` (a
    multiple of `chanbin`, at least one block)."""
    if not budget_bytes:
        return nchan
    per_chan = max(1, nrow * ncorr * READ_BYTES)
    n = int(budget_bytes // per_chan) // int(chanbin) * int(chanbin)
    return max(int(chanbin), min(nchan, n))


def stage(w, rows, settings, chunk_rows, chans_per_read=None, budget_bytes=None):
    """The re-weighting stage on the MS rows `rows` through the write-back
    session `w`, one scan at a time, each read in channel slices that fit
    `budget_bytes` (or `chans_per_read` channels); returns a summary. Rows
    outside `rows` keep their weights."""
    started = time.perf_counter()
    rows = np.unique(np.asarray(rows, np.int64))
    nchan, ncorr = w.cell

    def step(nrow):
        return chans_per_read or chans_for(nrow, nchan, ncorr, settings.chanbin,
                                           budget_bytes)  # fmt: skip

    gid, var, filled = estimate_rows(w.read_rows, rows, settings, nchan,
                                     chans_for_scan=step)  # fmt: skip
    w.ensure_column("WEIGHT_SPECTRUM")
    pos = np.full(w.nrows, -1, np.int64)
    pos[rows] = np.arange(len(rows))
    written = zero_unflagged = 0
    for start, n in w.chunks(chunk_rows):
        here = pos[start : start + n]
        mine = here >= 0
        if not mine.any():
            continue
        ws = w.read("WEIGHT_SPECTRUM", start, n)
        wt = w.read("WEIGHT", start, n)
        new = weights_of(var, gid[here[mine]], nchan, settings.chanbin, ncorr)
        ws[mine] = new
        flag = np.asarray(w.read("FLAG", start, n)[mine], bool)
        wt[mine] = row_weight(new, flag)
        zero_unflagged += int(np.count_nonzero((new == 0) & ~flag))
        w.write("WEIGHT_SPECTRUM", start, ws)
        w.write("WEIGHT", start, wt)
        written += int(mine.sum())
    finite = np.isfinite(var) & (var > 0)
    return {
        "mode": settings.mode,
        "chanbin": int(settings.chanbin),
        "timebin": settings.timebin,
        "statistic": settings.statistic,
        "minsamp": int(settings.minsamp),
        "smooth": int(settings.smooth),
        "fill": bool(settings.fill),
        "filled_blocks": filled,
        "unflagged_cells_at_weight_0": zero_unflagged,
        "rows": written,
        "groups": int(var.shape[0]),
        "blocks_with_weight": float(finite.mean()) if finite.size else 0.0,
        "wall_seconds": time.perf_counter() - started,
    }


def session_rows(w, fields, scans=None):
    """The MS rows of `fields` (FIELD_ID values), and of `scans` when given,
    read through the write-back session `w` (a second reader would drop its
    lock)."""
    fid = w.read("FIELD_ID", 0, w.nrows)
    keep = np.isin(fid, list(fields))
    if scans:
        keep &= np.isin(w.read("SCAN_NUMBER", 0, w.nrows), list(scans))
    return np.flatnonzero(keep)
