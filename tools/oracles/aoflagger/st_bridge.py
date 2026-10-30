"""SumThreshold bridge kernels for A-FLAG (research/a-flag-aoflagger.md, section 2.3).

NumPy only, so that the same file runs in the worktree venv, in the Tricolour
0.2.1 venv and in the AOFlagger container. Two kernels act on "columns": the
1-D sequences that one SumThreshold pass slides its windows along.

- `tricolour_columns` follows `tricolour.flagging._sum_threshold1d`: windows
  `w` with thresholds `thr / rho**log2(w)`, float64 cumulative sums of the
  float32 values, samples already flagged by this pass clamped to
  +/-threshold, flags smeared over the window (`_convolve_flags`).
- `aoflagger_columns` follows AOFlagger 3.5's `SumThresholdMissing`
  (`algorithms/sumthresholdmissing.cpp`): normalised values, float32 running
  sums, samples flagged by an earlier length excluded from the sum and the
  count, `missing` samples skipped by concatenation. `vertical=True` is
  `VerticalStacked`: the concatenated column is padded at its end with
  zero-valued, unflagged samples up to the full column height, and flags are
  written back only to non-missing positions. `vertical=False` is
  `horizontal`: windows end at the last sample and the flagged span is set in
  the original index, including missing samples inside it.

A column set is `(values, valid, threshold)`: `values` `(ncol, n)` float32,
`valid` `(ncol, n)` bool (False marks positions beyond the column's own
length) and `threshold` `(ncol,)` float32, Tricolour's chi_1 of the column.
"""

import math

import numpy as np

AO_LENGTHS = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def ao_mean_thresholds(lengths=AO_LENGTHS, sens=1.0 / 6.0):
    """`ThresholdConfig::InitializeThresholdsFromFirstThreshold(6, ...)` times
    the absolute factor `sens` (A3), in float32 as `num_t`."""
    out = []
    for length in lengths:
        op = np.float32(6.0 * math.pow(1.5, math.log2(length)) / length)
        out.append(np.float32(op * np.float32(sens)))
    return out


def _convolve_flags(flag, window, n_out):
    """`_convolve_flags` for a `(ncol, n_in)` flag array: OR over windows."""
    ncol, n_in = flag.shape
    cum = np.zeros((ncol, n_in + 2 * window - 1), np.uint32)
    cum[:, window : window + n_in] = np.cumsum(flag, axis=1, dtype=np.uint32)
    cum_size = cum.shape[1]
    cum[:, cum_size - (window - 1) :] = cum[
        :, cum_size - window : cum_size - window + 1
    ]
    return cum[:, window : window + n_out] != cum[:, :n_out]


def tricolour_columns(values, valid, threshold, windows, rho):
    """Tricolour's SumThreshold on each column; returns `(ncol, n)` flags."""
    values = np.asarray(values, np.float32)
    ncol, n = values.shape
    out = np.zeros((ncol, n), bool)
    lengths = valid.sum(axis=1)
    for length in np.unique(lengths):
        rows = np.nonzero(lengths == length)[0]
        length = int(length)
        data = values[rows, :length]
        thr = threshold[rows].astype(np.float32)
        pos = np.zeros((rows.size, length), bool)
        neg = np.zeros((rows.size, length), bool)
        for window in windows:
            window = int(window)
            if window > length:
                continue
            tf = pow(rho, float(np.log2(window)))
            this = thr.astype(np.float64)[:, None] / tf
            clamped = data.astype(np.float64)
            high = pos & (clamped > this)
            low = ~high & neg & (clamped < -this)
            clamped = np.where(high, this, np.where(low, -this, clamped))
            cum = np.zeros((rows.size, length + 1), np.float64)
            cum[:, 1:] = np.cumsum(clamped, axis=1)
            avg = cum[:, window:] - cum[:, :-window]
            scale = np.float32(1.0 / window)
            pos |= _convolve_flags(avg * scale > this, window, length)
            neg |= _convolve_flags(avg * (-scale) > this, window, length)
        out[rows, :length] = pos | neg
    return out


def normalise(values, threshold):
    """Values in units of the column's chi_1, as fed to AOFlagger (float32)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.asarray(values, np.float32) / np.asarray(threshold, np.float32)[:, None]
    return np.where(np.isfinite(z), z, np.float32(0)).astype(np.float32)


def aoflagger_columns(
    z, missing, lengths=AO_LENGTHS, sens=1.0 / 6.0, vertical=True, quirk=True
):
    """AOFlagger 3.5's masked SumThreshold on each column of normalised values
    `z` `(ncol, n)`; `missing` marks removed samples. Returns `(ncol, n)`."""
    if vertical:
        return _vertical_stacked(z, missing, lengths, sens)
    return _horizontal_missing(z, missing, lengths, sens, quirk)


def _compress(z, missing):
    z = np.asarray(z, np.float32)
    n = z.shape[1]
    keep = ~missing
    nc = keep.sum(axis=1)
    order = np.argsort(~keep, axis=1, kind="stable")  # compressed -> original
    comp = np.take_along_axis(np.where(keep, z, np.float32(0)), order, axis=1)
    in_col = np.arange(n)[None, :] < nc[:, None]
    comp = np.where(in_col, comp, np.float32(0)).astype(np.float32)
    return z, keep, nc, order, comp, in_col


def _vertical_stacked(z, missing, lengths, sens):
    """`SumThresholdMissing::VerticalStacked` + `SumThreshold::VerticalLarge`
    (the AVX2 `VerticalAVXDumas` path computes the same windows): the
    concatenated column is padded with zero-valued unflagged samples to the
    full height, and flags go back to the non-missing positions only."""
    z, keep, _, order, comp, _ = _compress(z, missing)
    ncol, n = z.shape
    mask = np.zeros((ncol, n), bool)
    for length, chi in zip(lengths, ao_mean_thresholds(lengths, sens)):
        if length > n:
            continue
        starts = np.zeros((ncol, n), bool)
        acc = np.zeros(ncol, np.float32)
        count = np.zeros(ncol, np.int64)
        for s in range(n):
            add = ~mask[:, s]
            acc = np.where(add, acc + comp[:, s], acc).astype(np.float32)
            count += add
            if s >= length - 1:
                left = s - length + 1
                with np.errstate(divide="ignore", invalid="ignore"):
                    mean = acc / count.astype(np.float32)
                starts[:, left] |= (count > 0) & (np.abs(mean) > chi)
                sub = ~mask[:, left]
                acc = np.where(sub, acc - comp[:, left], acc).astype(np.float32)
                count -= sub
        cum = np.zeros((ncol, n + 1), np.int64)
        cum[:, 1:] = np.cumsum(starts, axis=1)
        lo = np.maximum(np.arange(n) - length + 1, 0)
        mask |= (cum[:, np.arange(n) + 1] - cum[:, lo]) > 0
    inverse = np.argsort(order, axis=1, kind="stable")
    return np.take_along_axis(mask, inverse, axis=1) & keep


def _horizontal_missing(z, missing, lengths, sens, quirk=True):
    """`SumThresholdMissing::horizontal`, transcribed: windows of `length`
    non-missing samples; the flagged span runs from xLeft to xRight in the
    original index (missing samples inside it included).

    With `quirk` (what the 3.5.0 code does): for length >= 2 the initial loop
    leaves xRight one past the (length-1)-th non-missing sample. If that
    position is missing, the main loop adds it anyway (it tests only the
    mask, not `missing`), and since xLeft visits only non-missing samples it
    is never subtracted: it stays in the sum and the count for the rest of
    the row, and every later window holds length-1 non-missing samples plus
    it. `quirk=False` gives the intended semantics.
    """
    z, _, nc, order, comp, in_col = _compress(z, missing)
    ncol, n = z.shape
    cols = np.arange(ncol)
    orig_of = np.where(in_col, order, n)
    mask_orig = np.zeros((ncol, n), bool)
    for length, chi in zip(lengths, ao_mean_thresholds(lengths, sens)):
        if length > n:
            continue
        mask_c = np.take_along_axis(mask_orig, order, axis=1) & in_col
        if quirk and length >= 2:
            r0 = np.where(
                nc >= length - 1, orig_of[cols, min(length - 2, n - 1)] + 1, n
            )
            buggy = (nc >= length - 1) & (r0 < n)
            r0c = np.minimum(r0, n - 1)
            buggy &= missing[cols, r0c]
            extra_on = buggy & ~mask_orig[cols, r0c]
            extra_val = np.where(extra_on, z[cols, r0c], np.float32(0)).astype(
                np.float32
            )
        else:
            buggy = np.zeros(ncol, bool)
            extra_on = buggy
            extra_val = np.zeros(ncol, np.float32)
            r0c = np.zeros(ncol, np.int64)
        off = buggy.astype(np.int64)
        firsts, lasts, owner = [], [], []
        acc = np.zeros(ncol, np.float32)
        count = np.zeros(ncol, np.int64)

        def check(
            active,
            left,
            right_orig,
            chi=chi,
            owner=owner,
            firsts=firsts,
            lasts=lasts,
            mask_c=mask_c,
        ):
            nonlocal acc, count
            with np.errstate(divide="ignore", invalid="ignore"):
                mean = acc / count.astype(np.float32)
            hit = active & (count > 0) & (np.abs(mean) > chi)
            sel = np.nonzero(hit)[0]
            if sel.size:
                owner.append(sel)
                firsts.append(orig_of[sel, left[sel]])
                lasts.append(right_orig[sel])
            li = np.minimum(left, n - 1)
            sub = active & ~mask_c[cols, li]
            acc = np.where(sub, acc - comp[cols, li], acc).astype(np.float32)
            count -= sub

        for s in range(n):
            add = (s < nc) & ~mask_c[:, s]
            acc = np.where(add, acc + comp[:, s], acc).astype(np.float32)
            count += add
            if quirk and length >= 2 and s == length - 2 and buggy.any():
                acc = np.where(extra_on, acc + extra_val, acc).astype(np.float32)
                count += extra_on
                check(buggy, np.zeros(ncol, np.int64), r0c)
            if s >= length - 1:
                left = s - length + 1 + off
                check(s < nc, left, orig_of[:, s])
        if owner:
            o = np.concatenate(owner)
            first = np.concatenate(firsts)
            last = np.concatenate(lasts)
            delta = np.zeros((ncol, n + 2), np.int64)
            np.add.at(delta, (o, first), 1)
            np.add.at(delta, (o, last + 1), -1)
            mask_orig = mask_orig | (np.cumsum(delta, axis=1)[:, :n] > 0)
    return mask_orig


def tricolour_in_ao_units(z, valid, windows, rho):
    """Tricolour's kernel (clamping) on normalised values with chi_1 = 1, for
    the bridge rung K1 (AOFlagger's lengths and rho in Tricolour semantics)."""
    return tricolour_columns(z, valid, np.ones(z.shape[0], np.float32), windows, rho)


def exclusion_columns(z, valid, lengths=AO_LENGTHS, sens=1.0 / 6.0, vertical=True):
    """Rung K2: AOFlagger's exclusion semantics with only the padding missing."""
    return aoflagger_columns(z, ~valid, lengths, sens, vertical)


# ---------------------------------------------------------------- column sets


def time_columns(data, threshold):
    """Time pass: one column per channel, `data` `(ntime, nchan)`."""
    values = np.ascontiguousarray(np.asarray(data, np.float32).T)
    valid = np.ones(values.shape, bool)
    return values, valid, np.asarray(threshold, np.float32).reshape(-1)


def chunk_columns(data, threshold, chunk_ends, max_window):
    """Spectrum and frequency passes: one column per (row, chunk), Tricolour's
    padded slice `[lo - max_window + 1, hi + max_window - 1)` clipped to the
    band. `threshold` is `(nrow, nchunk)`. Returns the column set and, per
    column, `(row, slice start, chunk lo, chunk hi)`."""
    data = np.asarray(data, np.float32)
    nrow, nchan = data.shape
    nchunk = len(chunk_ends) - 1
    spans = []
    for c in range(nchunk):
        lo, hi = int(chunk_ends[c]), int(chunk_ends[c + 1])
        p0 = max(lo - max_window + 1, 0)
        p1 = min(hi + max_window - 1, nchan)
        spans.append((p0, p1, lo, hi))
    width = max(p1 - p0 for p0, p1, _, _ in spans)
    ncol = nrow * nchunk
    values = np.zeros((ncol, width), np.float32)
    valid = np.zeros((ncol, width), bool)
    thr = np.zeros(ncol, np.float32)
    index = []
    for r in range(nrow):
        for c, (p0, p1, lo, hi) in enumerate(spans):
            k = r * nchunk + c
            values[k, : p1 - p0] = data[r, p0:p1]
            valid[k, : p1 - p0] = True
            thr[k] = threshold[r, c]
            index.append((r, p0, lo, hi))
    return values, valid, thr, index


def chunk_flags_back(flags, index, nrow, nchan):
    """Collect each column's own chunk cells into `(nrow, nchan)` flags."""
    out = np.zeros((nrow, nchan), bool)
    for k, (r, p0, lo, hi) in enumerate(index):
        out[r, lo:hi] = flags[k, lo - p0 : hi - p0]
    return out


def chunk_missing(flags, index, width):
    """Input flags of each padded slice, `(ncol, width)` (False beyond)."""
    flags = np.asarray(flags, bool)
    out = np.zeros((len(index), width), bool)
    for k, (r, p0, _lo, _hi) in enumerate(index):
        seg = flags[r, p0 : p0 + width]
        out[k, : seg.size] = seg
    return out


# ------------------------------------------------- Tricolour's post-processing


def smear_and_cut(
    det, time_extend, freq_extend, flag_all_time_frac, flag_all_freq_frac
):
    """`_combine_flags` time smearing and `_unaverage_freq` (average_freq 1):
    box smearing and the row/column fraction cuts on `(ntime, nchan)`."""
    det = np.asarray(det, bool)
    ntime, nchan = det.shape
    cum = np.zeros((ntime + 1, nchan), np.int64)
    cum[1:] = np.cumsum(det, axis=0)
    lo = -(int(time_extend) // 2)
    hi = lo + int(time_extend)
    t = np.arange(ntime)
    t0 = np.clip(t + lo, 0, ntime)
    t1 = np.clip(t + hi, 0, ntime)
    smeared = cum[t0] != cum[t1]
    cumf = np.zeros((ntime, nchan + 1), np.int64)
    cumf[:, 1:] = np.cumsum(smeared, axis=1)
    lo = -(int(freq_extend) // 2)
    hi = lo + int(freq_extend)
    f = np.arange(nchan)
    f0 = np.clip(f + lo, 0, nchan)
    f1 = np.clip(f + hi, 0, nchan)
    smeared = cumf[:, f0] != cumf[:, f1]
    out = smeared.copy()
    out[smeared.sum(axis=1) > flag_all_freq_frac * nchan] = True
    # Column counts come from the smeared flags before the row cut, as in
    # _unaverage_freq.
    out[:, smeared.sum(axis=0) > ntime * flag_all_time_frac] = True
    return out
