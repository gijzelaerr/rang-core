# SPDX-License-Identifier: GPL-3.0-or-later
"""Chunked reading and solving of the CASA-style terms (task W3b,
research/w3b-chainchunks.md).

`rang.cal_gain`, `rang.cal_delay`, `rang.cal_bandpass`, `rang.cal_pol` and
`rang.cal_fluxscale` solve one field at a time. With a
`core_chunks.ChainBudget` they hold the field's row metadata and the solver's
outputs whole and read the cell arrays (data, model, weights, flags) in
chunks of whole solution intervals:

- `plan(...)`: the chunks of a solve, consecutive intervals with all
  channels, or consecutive channels of one interval for the per-channel
  terms (B, Xf, Df); a solve whose smallest unit does not fit is refused
  (`core_chunks.MemoryLimitError`);
- `load(...)`: one chunk's cell arrays, read through `core_chunks.read_rows`
  and prepared (pre-applied) on whole rows, in blocks of rows when the chunk
  holds some channels only;
- `replayed(...)`: the solver's global stop test (converged fraction over
  every interval of the field) replayed over the chunks in two passes, from
  the counts of the counted kernels (`cal_gain_trace`, `cal_delay_trace`,
  `cal_delay_offset_trace`);
- `gauge(...)`: `rang.cal_pol.unpolarised_gauge` over chunks, its median
  found exactly by histograms of the float32 values' order-preserving keys.

Chunking changes no arithmetic: a chunked solve gives the solutions of the
one-call solve bit for bit (research/w3b-chainchunks.md, section 3).
"""

from dataclasses import dataclass

import numpy as np

from . import core_chunks

# The stop test is off (no fraction reaches it) in both passes of a replay.
STOP_OFF = 2.0


@dataclass(frozen=True)
class Chunk:
    """Intervals [t0, t1) and frequency bins [f0, f1) of one solve: `pos`
    the positions (ascending) of their rows among the field's rows,
    `chans` the channels."""

    pos: np.ndarray
    t0: int
    t1: int
    f0: int
    f1: int
    chans: slice
    whole: bool  # all channels


def plan(time_bin, nchan, ncorr, budget, *, per_channel, what="solve"):
    """The chunks of a solve with interval index `time_bin` per field row,
    and the rows of all channels a block may hold. `budget` None: one
    chunk (the one-call solve). `per_channel`: one frequency bin per
    channel (B, Xf, Df); otherwise one bin over all channels."""
    tb = np.asarray(time_bin, np.int64)
    n = len(tb)
    ntime = int(tb.max()) + 1 if n else 0
    nfreq = int(nchan) if per_channel else 1
    if budget is None:
        return [Chunk(np.arange(n), 0, ntime, 0, nfreq, slice(0, nchan), True)], n
    max_cells, hard, block = budget.plan(n, nchan, ncorr, per_channel)
    rows_of = np.bincount(tb, minlength=ntime)
    unit = int(rows_of.max()) * (1 if per_channel else int(nchan)) * int(ncorr)
    if hard < unit or (per_channel and block < 1):
        need = budget.need_gb(n, max(unit, int(nchan) * int(ncorr)), per_channel)
        limit = (
            ""
            if budget.limit_gb is None
            else f", above data.memory_limit_gb {budget.limit_gb:g}"
        )
        smallest = (
            "one channel of one solution interval"
            if per_channel
            else "one solution interval"
        )
        raise core_chunks.MemoryLimitError(
            f"{what}: {smallest} holds {unit} visibility cells of {n} rows and needs "
            f"{need:.3f} GiB{limit}; raise the limit, or use a shorter solint "
            "(a solution interval is solved whole)"
        )
    order = np.argsort(tb, kind="stable")
    fb = np.arange(nchan) if per_channel else np.zeros(nchan, np.int64)
    chunks, _ = core_chunks.solve_chunks(
        tb[order], fb, max_cells, ncorr, hard_cells=hard
    )
    out = []
    for c in chunks:
        pos = np.sort(order[c.rows])
        whole = c.chans.start == 0 and c.chans.stop == nchan
        out.append(Chunk(pos, c.t0, c.t1, c.f0, c.f1, c.chans, whole))
    return out, max(1, block)


def load(reader, rows, chunk, names, prepare, block_rows):
    """The prepared arrays of `chunk`: column `names` of MS rows
    `rows[chunk.pos]` read from `reader`, passed as `prepare(pos, columns)`,
    which returns a dict of `(row, chan, corr)` arrays and per-row arrays.
    A chunk with some channels only is read and prepared in blocks of
    `block_rows` whole rows, each cut to the chunk's channels."""
    pos = chunk.pos
    if chunk.whole:
        cols = {n: core_chunks.read_rows(reader, n, rows[pos]) for n in names}
        return prepare(pos, cols)
    out = {}
    step = max(1, int(block_rows))
    for b in range(0, len(pos), step):
        part = pos[b : b + step]
        cols = {n: core_chunks.read_rows(reader, n, rows[part]) for n in names}
        got = prepare(part, cols)
        del cols
        for key, value in got.items():
            value = np.asarray(value)
            if value.ndim >= 2:
                value = value[:, chunk.chans]
            if key not in out:
                out[key] = np.empty((len(pos), *value.shape[1:]), value.dtype)
            out[key][b : b + len(part)] = value
        del got
    return out


def replayed(chunks, run, *, max_iterations, stop_fraction):
    """Solve `chunks` with the stop test of the one-call solve.

    `run(chunk, max_iterations, stop_fraction, trace)` solves one chunk and
    returns its result, or with `trace` `(counts, error, ngains)`: the
    per-iteration (converged, flagged) counts (an `(k, 2)` array), the
    `(iteration, message)` of a solver error or None, and the chunk's
    gains. One chunk is one call with the stop test. Otherwise pass 1 sums
    the counts with the stop test off; the stop iteration `j` and the
    converged fraction are the one-call solve's; a solver error is raised
    when no stop comes before the earliest error iteration of any chunk;
    pass 2 solves every chunk for `j + 1` iterations with the stop test off.
    Returns `(results, (iterations, converged fraction) or None)`."""
    if len(chunks) == 1:
        return [run(chunks[0], max_iterations, stop_fraction, False)], None
    totals, ngains, first = None, 0, None
    for c in chunks:
        counts, error, n = run(c, max_iterations, STOP_OFF, True)
        counts = np.asarray(counts, np.int64).reshape(-1, 2)
        ngains += int(n)
        if error is not None and (first is None or error[0] < first[0]):
            first = error
        if totals is None:
            totals = counts
        else:
            k = min(len(totals), len(counts))
            totals = totals[:k] + counts[:k]
    j, fraction = None, 0.0
    for i, (converged, flagged) in enumerate(totals.tolist()):
        solvable = ngains - flagged
        fraction = converged / solvable if solvable > 0 else 0.0
        if fraction >= stop_fraction:
            j = i
            break
    if j is None:
        if first is not None:
            raise ValueError(first[1])
        j = len(totals) - 1
    results = [run(c, j + 1, STOP_OFF, False) for c in chunks]
    return results, (j + 1, float(fraction))


def trace_buffer(max_iterations):
    """The `counts` array of a counted kernel call."""
    return np.zeros(2 * max(int(max_iterations), 1), np.uint64)


# -- Df's gauge test over chunks -----------------------------------------------


def _keys(x):
    """Order-preserving uint32 keys of float32 values."""
    b = np.ascontiguousarray(x, np.float32).view(np.uint32)
    return np.where(b >> np.uint32(31), ~b, b | np.uint32(0x80000000))


def _value(key):
    key = np.uint32(key)
    bits = key & np.uint32(0x7FFFFFFF) if key >> np.uint32(31) else ~key
    return np.array([bits], np.uint32).view(np.float32)[0]


def _ratios(model, flag):
    """`M_YY / M_XX` of the cells `unpolarised_gauge` uses."""
    ok = ~flag[..., 0] & ~flag[..., 3] & (np.abs(model[..., 0]) > 0)
    return model[..., 3][ok] / model[..., 0][ok]


def gauge(chunks, tol=1e-6):
    """`rang.cal_pol.unpolarised_gauge` over the chunks given by `chunks()`
    (a callable yielding `(model, flag)` per chunk, flag already OR'd with
    the row flags), exactly: the median of the real and imaginary parts by
    two histogram passes on 16-bit halves of the keys (NumPy's average of
    the two middle values for an even count), the largest deviation by a
    third pass."""
    count = 0
    nan = [False, False]
    hi = [np.zeros(1 << 16, np.int64), np.zeros(1 << 16, np.int64)]
    for model, flag in chunks():
        rho = _ratios(model, flag)
        count += len(rho)
        for i, part in enumerate((rho.real, rho.imag)):
            nan[i] |= bool(np.isnan(part).any())
            hi[i] += np.bincount(_keys(part) >> np.uint32(16), minlength=1 << 16)
        del rho
    if count == 0:
        return True, 1.0
    ranks = [count // 2] if count % 2 else [count // 2 - 1, count // 2]
    wanted = []  # per part: [(rank, high bin, rank within the bin)]
    for i in range(2):
        cum = np.cumsum(hi[i])
        picks = []
        for r in ranks:
            b = int(np.searchsorted(cum, r, side="right"))
            below = int(cum[b - 1]) if b else 0
            picks.append((b, r - below))
        wanted.append(picks)
    lo = [[np.zeros(1 << 16, np.int64) for _ in ranks] for _ in range(2)]
    for model, flag in chunks():
        rho = _ratios(model, flag)
        for i, part in enumerate((rho.real, rho.imag)):
            k = _keys(part)
            high = k >> np.uint32(16)
            for j, (b, _) in enumerate(wanted[i]):
                sel = k[high == np.uint32(b)]
                lo[i][j] += np.bincount(sel & np.uint32(0xFFFF), minlength=1 << 16)
        del rho
    medians = []
    for i in range(2):
        if nan[i]:
            medians.append(np.float32(np.nan))
            continue
        values = []
        for j, (b, r) in enumerate(wanted[i]):
            low = int(np.searchsorted(np.cumsum(lo[i][j]), r, side="right"))
            values.append(_value((b << 16) | low))
        medians.append(np.median(np.array(values, np.float32)))
    r0 = medians[0] + 1j * medians[1]
    dev = None
    for model, flag in chunks():
        rho = _ratios(model, flag)
        if len(rho):
            d = np.max(np.abs(rho - r0))
            dev = d if dev is None else max(dev, d)
        del rho
    degenerate = bool(dev <= tol * max(1.0, abs(r0)))
    return degenerate, complex(r0)


__all__ = ["STOP_OFF", "Chunk", "gauge", "load", "plan", "replayed", "trace_buffer"]
