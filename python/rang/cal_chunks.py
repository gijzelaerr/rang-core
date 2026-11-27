# SPDX-License-Identifier: MIT
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
  found exactly by histograms of the float32 values' order-preserving keys;
- `Average`, `load_averaged(...)` (task E2, `calibrate.average_time`):
  CASA's time pre-averaging within each solution interval, the source rows
  streamed in blocks, prepared per row, then accumulated per (interval,
  baseline, channel, correlation); the solve is on the averages.

Chunking changes no arithmetic: a chunked solve gives the solutions of the
one-call solve bit for bit (research/w3b-chainchunks.md, section 3).
Averaging changes the estimator (CASA's); it is off unless asked for.
"""

import contextlib
import contextvars
import hashlib
import itertools
import weakref
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


def plan(time_bin, nchan, ncorr, budget, *, per_channel, what="solve", average=None):
    """The chunks of a solve with interval index `time_bin` per field row,
    and the rows of all channels a block may hold. `budget` None: one
    chunk (the one-call solve). `per_channel`: one frequency bin per
    channel (B, Xf, Df); otherwise one bin over all channels.

    `average` (an `Average`, task E2, `calibrate.average_time`): the solve
    is on the field's time-averaged rows and `time_bin` is
    `average.time_bin` (one per averaged row). The memory goes half to a
    chunk of averaged rows and half to a read block of whole source rows
    (`AVERAGE_BLOCK_SHARE` of that half in rows, for the accumulation's
    temporaries); the metadata of the source and the averaged rows is
    held."""
    tb = np.asarray(time_bin, np.int64)
    n = len(tb)
    ntime = int(tb.max()) + 1 if n else 0
    nfreq = int(nchan) if per_channel else 1
    if budget is None:
        block = n if average is None else average.nsource
        return [Chunk(np.arange(n), 0, ntime, 0, nfreq, slice(0, nchan), True)], block
    held = n if average is None else n + average.nsource
    split = per_channel or average is not None
    max_cells, hard, block = budget.plan(held, nchan, ncorr, split)
    if average is not None:
        block = int(block * AVERAGE_BLOCK_SHARE)
    rows_of = np.bincount(tb, minlength=ntime)
    unit = int(rows_of.max()) * (1 if per_channel else int(nchan)) * int(ncorr)
    if hard < unit or (split and block < 1):
        row = int(nchan) * int(ncorr)
        least = row if average is None else int(np.ceil(row / AVERAGE_BLOCK_SHARE))
        need = budget.need_gb(held, max(unit, least), split)
        limit = (
            ""
            if budget.limit_gb is None
            else ", above data.memory_limit_gb "
            + (budget.limit_text or f"{budget.limit_gb:g}")
        )
        smallest = (
            "one channel of one solution interval"
            if per_channel
            else "one solution interval"
        )
        if average is not None:
            smallest += ", time-averaged,"
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

    A chunk with some channels only reads only its channels of the columns
    that have a channel axis (research/sliced-read.md) and is prepared on
    them, `prepare(pos, columns, chans=chunk.chans)`, which pre-applies on
    that window of the band (`rang.cal_apply.apply(channels=)`). Each row's
    weight sum `row_w` is a sum over all channels after the pre-apply's
    flags, so it comes from whole rows: read and prepared in blocks of
    `block_rows` rows once per set of rows and reused by the other channel
    chunks of the interval and by the second pass of a replay."""
    pos = chunk.pos
    if chunk.whole:
        cols = {n: core_chunks.read_rows(reader, n, rows[pos]) for n in names}
        return prepare(pos, cols)
    cols = {
        n: core_chunks.read_rows(
            reader, n, rows[pos], chunk.chans if _has_channels(reader, n) else None
        )
        for n in names
    }
    got = prepare(pos, cols, chans=chunk.chans)
    del cols
    out = {}
    for key, value in got.items():
        value = np.asarray(value)
        out[key] = np.ascontiguousarray(value) if value.ndim >= 2 else value
    del got
    if "row_w" in out:
        task = _TASK.get()
        if task is not None and task[1]:
            # The counted pass of a chunk task: its row weights are not used
            # (only pass 2's are), so the whole rows are not read for them.
            del out["row_w"]
        else:
            out["row_w"] = whole_row_weights(
                reader, rows, pos, names, prepare, block_rows,
                task_key=None if task is None else task[0],
            )  # fmt: skip
    return out


# Per field (the owner of its `prepare`), the rows' weight sums of whole
# rows by the set of rows they were taken over: 8 bytes a row.
_ROW_WEIGHTS = weakref.WeakKeyDictionary()
# The same in a worker, where each chunk task builds its field anew: by
# recipe (`task_key`), the most recent few kept (research/chunk-task-api-1b.md
# section 6: without it every channel chunk re-read the whole field).
_TASK_ROW_WEIGHTS = {}
_TASK_ROW_WEIGHTS_KEEP = 4
# (recipe key, counted pass) of the chunk task running in this worker, or None.
_TASK = contextvars.ContextVar("rang_chain_task", default=None)


def whole_row_weights(reader, rows, pos, names, prepare, block_rows, task_key=None):
    """`row_w` of field rows `pos` from whole rows (all channels), read and
    prepared in blocks of `block_rows` rows as the one-call solve prepares
    them; memoised per field and set of rows (in a chunk task, per recipe
    `task_key`)."""
    key = (len(pos), hashlib.sha256(np.ascontiguousarray(pos, np.int64)).hexdigest())
    if task_key is not None:
        memo = _TASK_ROW_WEIGHTS.setdefault(task_key, {})
        while len(_TASK_ROW_WEIGHTS) > _TASK_ROW_WEIGHTS_KEEP:
            _TASK_ROW_WEIGHTS.pop(next(iter(_TASK_ROW_WEIGHTS)))
    else:
        owner = getattr(prepare, "__self__", prepare)
        try:
            memo = _ROW_WEIGHTS.setdefault(owner, {})
        except TypeError:  # an owner without weak references: no memo
            memo = {}
    if key in memo:
        return memo[key]
    row_w = np.empty(len(pos))
    step = max(1, int(block_rows))
    for b in range(0, len(pos), step):
        part = pos[b : b + step]
        cols = {n: core_chunks.read_rows(reader, n, rows[part]) for n in names}
        row_w[b : b + len(part)] = prepare(part, cols)["row_w"]
        del cols
    memo[key] = row_w
    return row_w


def _has_channels(reader, name):
    """True when column `name` has a channel axis (a cell of two axes or
    more, `(row, chan, corr)` in NumPy): only those are read sliced."""
    columns = getattr(reader, "columns", None)
    if columns is not None and name in columns:
        ndim = int(columns[name].get("ndim", -1))
        if ndim > 0:
            return ndim >= 2
    return np.ndim(reader.getcol(name, 0, 1)) >= 3


# -- time pre-averaging within solution intervals (task E2) ----------------------

# The share of a read block's memory (in rows) left to the source rows when
# they are averaged: the rest holds the accumulation's temporaries (the
# masked weights and the weighted data and model in double precision).
AVERAGE_BLOCK_SHARE = 0.5

# Task xf-avg-fix (research/xf-avg-fix.md section 2): a solve on a model
# rotated by P averages no samples of two scans, nor samples whose parallactic
# angles span more than this (degrees).
PSI_TOL_DEG = 5.0


def psi_groups(time_bin, scan, psi, tol_deg=None):
    """The averaging groups of a P-rotated solve (task xf-avg-fix,
    research/xf-avg-fix.md section 2). Per (interval, scan) of the rows,
    `psi` (rad, P's angle of each row's ANTENNA1) is taken as the circular
    difference from the first row's and its span cut into n = max(1,
    ceil(span / tol)) equal pieces; a group is one (interval, scan, piece).
    Returns the group of each row (dense, ascending in that order), or None
    when every interval is one group (the averaging is then the one without
    groups, unchanged)."""
    tol = np.radians(PSI_TOL_DEG if tol_deg is None else float(tol_deg))
    tb = np.asarray(time_bin, np.int64)
    sc = np.asarray(scan, np.int64)
    psi = np.asarray(psi, float)
    if not len(tb):
        return None
    _, first, part = np.unique(
        np.stack([tb, sc]), axis=1, return_index=True, return_inverse=True
    )
    part = part.ravel()
    d = np.angle(np.exp(1j * (psi - psi[first[part]])))  # (-pi, pi]
    piece = np.zeros(len(tb), np.int64)
    order = np.argsort(part, kind="stable")
    bounds = np.flatnonzero(np.r_[True, np.diff(part[order]) != 0, True])
    for b0, b1 in itertools.pairwise(bounds):
        rows = order[b0:b1]
        lo = d[rows].min()
        span = d[rows].max() - lo
        n = max(1, int(np.ceil(span / tol)))
        if n > 1:
            piece[rows] = np.minimum(
                np.floor((d[rows] - lo) / (span / n)).astype(np.int64), n - 1
            )
    _, group = np.unique(np.stack([tb, sc, piece]), axis=1, return_inverse=True)
    group = group.ravel().astype(np.int64)
    per_interval = np.bincount(np.unique(np.stack([tb, group]), axis=1)[0])
    if (per_interval <= 1).all():
        return None
    return group


class Average:
    """CASA's time pre-averaging within solution intervals (task E2,
    `calibrate.average_time`): one averaged row per (interval, baseline)
    of the field's cross-correlation rows, in the order of (interval,
    ANTENNA1, ANTENNA2). `skip` marks the source rows that contribute
    nothing (FLAG_ROW, outside `uvrange`, autocorrelations); an averaged
    row whose source rows are all skipped is flagged as a row.

    `group` (task xf-avg-fix, `psi_groups`): each source row's averaging
    group, ascending with the interval; then one averaged row per (group,
    baseline), in the order of (interval, group, ANTENNA1, ANTENNA2), each
    with its group's interval. None: one group per interval.

    `inverse` is each source row's averaged row (-1 for autocorrelations),
    `time_bin`, `antenna1`, `antenna2`, `flag_row` the averaged rows'."""

    def __init__(self, time_bin, antenna1, antenna2, skip, group=None):
        tb = np.asarray(time_bin, np.int64)
        a1 = np.asarray(antenna1, np.int64)
        a2 = np.asarray(antenna2, np.int64)
        skip = np.asarray(skip, bool)
        self.nsource = len(tb)
        self.skip = skip
        cross = a1 != a2
        nant = int(max(a1.max(), a2.max())) + 1 if len(a1) else 1
        outer = tb
        if group is not None:
            # The group ascends with the interval, so it alone orders
            # (interval, group); each group keeps its interval.
            outer = np.asarray(group, np.int64)
            interval_of = np.zeros(int(outer.max()) + 1, np.int64)
            interval_of[outer] = tb
        key = (outer * nant + a1) * nant + a2
        uniq, inv = np.unique(key[cross], return_inverse=True)
        self.inverse = np.full(len(tb), -1, np.int64)
        self.inverse[cross] = inv.ravel()
        self.time_bin = uniq // (nant * nant)
        if group is not None:
            self.time_bin = interval_of[self.time_bin]
        self.antenna1 = (uniq // nant) % nant
        self.antenna2 = uniq % nant
        live = np.bincount(self.inverse[cross & ~skip], minlength=len(uniq))
        self.flag_row = live == 0

    def __len__(self):
        return len(self.time_bin)

    def sources(self, pos):
        """The source rows (positions among the field's rows, ascending)
        of averaged rows `pos`, and each one's index into `pos`."""
        local = np.full(len(self) + 1, -1, np.int64)
        local[np.asarray(pos, np.int64)] = np.arange(len(pos))
        loc = local[self.inverse]  # -1 (the extra slot) for autocorrelations
        src = np.flatnonzero(loc >= 0)
        return src, loc[src]


def load_averaged(reader, rows, chunk, names, prepare, block_rows, average):
    """The time-averaged arrays of `chunk` (a chunk of `average`'s rows):
    the source rows of its averaged rows are read in blocks of
    `block_rows` whole rows, prepared by `prepare` (pre-applies and P, per
    row), cut to the chunk's channels and accumulated per (averaged row,
    channel, correlation): with `w` the weight of an unflagged cell of a
    row not skipped, the data and model become `sum(w d) / sum(w)` and
    `sum(w m) / sum(w)`, the weight `sum(w)`; a cell with `sum(w) = 0` (no
    unflagged sample of positive weight) is flagged, with data and model 0.
    Also returns `src` (the source positions read) and their `row_w`
    (`prepare`'s per-row weight sums for the solution times)."""
    src, loc = average.sources(chunk.pos)
    nloc = len(chunk.pos)
    chans = chunk.chans
    sw = swd = swm = None
    row_w = np.zeros(len(src))
    step = max(1, int(block_rows))
    for b in range(0, len(src), step):
        part = src[b : b + step]
        cols = {n: core_chunks.read_rows(reader, n, rows[part]) for n in names}
        got = prepare(part, cols)
        del cols
        row_w[b : b + len(part)] = got.pop("row_w")
        data = np.asarray(got["data"])[:, chans]
        model = np.broadcast_to(np.asarray(got["model"]), np.shape(got["data"]))
        model = model[:, chans]
        weights = np.broadcast_to(np.asarray(got["weights"]), np.shape(got["data"]))
        weights = weights[:, chans]
        flag = np.asarray(got["flag"], bool)[:, chans]
        del got
        used = ~flag & ~average.skip[part][:, None, None]
        del flag
        w = np.where(used, weights.astype(np.float64), 0.0)
        wd = w * np.where(used, data, 0).astype(np.complex128)
        wm = w * np.where(used, model, 0).astype(np.complex128)
        del used, data, model, weights
        if sw is None:
            shape = (nloc, *w.shape[1:])
            sw = np.zeros(shape)
            swd = np.zeros(shape, np.complex128)
            swm = np.zeros(shape, np.complex128)
        here = loc[b : b + len(part)]
        order = np.argsort(here, kind="stable")
        sorted_loc = here[order]
        starts = np.flatnonzero(np.r_[True, sorted_loc[1:] != sorted_loc[:-1]])
        targets = sorted_loc[starts]
        sw[targets] += np.add.reduceat(w[order], starts, axis=0)
        swd[targets] += np.add.reduceat(wd[order], starts, axis=0)
        swm[targets] += np.add.reduceat(wm[order], starts, axis=0)
        del w, wd, wm
    if sw is None:  # no source rows: cannot happen for a planned chunk
        raise ValueError("an averaged chunk without source rows")
    good = sw > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        data = np.where(good, swd / np.where(good, sw, 1.0), 0).astype(np.complex64)
        del swd
        model = np.where(good, swm / np.where(good, sw, 1.0), 0).astype(np.complex64)
        del swm
    return {
        "data": data,
        "model": model,
        "weights": sw.astype(np.float32),
        "flag": ~good,
        "src": src,
        "row_w": row_w,
    }


# -- chunk tasks of a replayed solve (research/chunk-task-api-1b.md 1.2) ---------


@dataclass
class Dispatch:
    """Set (`dispatching`) around a chain solve in the parent: the first
    replayed solve of more than one chunk inside it sends its chunks to
    `executor` as `chain-chunk` tasks of `recipe` (a JSON-able description
    of the solve, `rang.cal_chain.recipe`); later replayed solves run
    here."""

    executor: object
    recipe: dict


@dataclass
class Only:
    """Set in a worker running a `chain-chunk` task: the first replayed
    solve runs chunk `index` only, for `max_iterations` with
    `stop_fraction` (`trace`: counted) and raises `ChunkDone`."""

    index: int
    max_iterations: int | list  # a list: one count per run (K's zero_start)
    stop_fraction: float
    trace: bool
    key: str = ""  # the recipe's identity (the worker's row-weight memo)


class ChunkDone(Exception):
    """The result of the one chunk an `Only` asked for."""

    def __init__(self, result):
        super().__init__("chunk done")
        self.result = result


_DISPATCH = contextvars.ContextVar("rang_chain_dispatch", default=None)


@contextlib.contextmanager
def dispatching(value):
    """`value` (a `Dispatch`, an `Only` or None) for the replayed solves
    inside the block."""
    token = _DISPATCH.set(value)
    try:
        yield value
    finally:
        _DISPATCH.reset(token)


# Fill of a worker's row-weight array before its chunk runs: a NaN payload
# no arithmetic produces, so the positions the chunk wrote are exactly those
# whose bits differ from it.
_UNWRITTEN = np.array([0x7FF8DEAD0000BEEF], np.uint64).view(np.float64)[0]


def _written(row_w):
    bits = np.asarray(row_w, np.float64).view(np.uint64)
    return np.flatnonzero(bits != np.uint64(0x7FF8DEAD0000BEEF))


def _dispatched(d, nchunks, max_iterations, stop_fraction, trace):
    """The partials of every chunk of `d`'s solve, run by its executor in
    chunk order."""
    from . import core_tasks

    specs = [
        core_tasks.chain_chunk_spec(d.recipe, i, max_iterations, stop_fraction, trace)
        for i in range(nchunks)
    ]
    return list(d.executor.map(specs))


def _only(only, chunks, run, row_w):
    """In a worker: run the chunk `only` names and raise its result."""
    chunk = chunks[only.index]
    token = _TASK.set((only.key or None, bool(only.trace)))
    try:
        if only.trace:
            raise ChunkDone(run(chunk, only.max_iterations, only.stop_fraction, True))
        if row_w is None:
            raise ValueError("a dispatched chunk needs the solve's row weights")
        row_w[:] = _UNWRITTEN
        result = run(chunk, only.max_iterations, only.stop_fraction, False)
    finally:
        _TASK.reset(token)
    pos = _written(row_w)
    raise ChunkDone((result, pos, np.array(row_w[pos])))


def replayed(chunks, run, *, max_iterations, stop_fraction, row_w=None):
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
    A solve of two runs (K with `zero_start`, research/k-ambiguity.md
    section 10) traces a list of two: each run's stop is found the same
    way, in run order, and pass 2 gets the list of counts; the returned
    iterations and fraction are the first run's, as in the one call.
    Returns `(results, (iterations, converged fraction) or None)`.

    Chunk tasks (research/chunk-task-api-1b.md 1.2): inside `dispatching`
    of a `Dispatch`, the first call of more than one chunk runs both passes'
    chunks as `chain-chunk` tasks of the executor, and `row_w` (the solve's
    row-weight array, which `run` fills in pass 2) receives each chunk's
    row weights from its task; inside an `Only` (a worker), the first call
    runs one chunk and raises `ChunkDone`."""
    d = _DISPATCH.get()
    if d is not None:
        _DISPATCH.set(None)  # later replayed solves of the recipe run here
    if isinstance(d, Only):
        _only(d, chunks, run, row_w)
    if len(chunks) == 1:
        return [run(chunks[0], max_iterations, stop_fraction, False)], None
    if isinstance(d, Dispatch) and d.executor.inline:
        d = None
    if d is not None and row_w is None:
        raise ValueError("a dispatched solve needs its row weights (row_w)")
    if d is None:
        traced = (run(c, max_iterations, STOP_OFF, True) for c in chunks)
    else:
        traced = _dispatched(d, len(chunks), max_iterations, STOP_OFF, True)
    runs = None  # per run of the solve: [summed counts, gains, first error]
    multi = False
    for item in traced:
        multi = isinstance(item, list)
        parts = item if multi else [item]
        if runs is None:
            runs = [[None, 0, None] for _ in parts]
        for acc, (counts, error, n) in zip(runs, parts, strict=True):
            counts = np.asarray(counts, np.int64).reshape(-1, 2)
            acc[1] += int(n)
            if error is not None and (acc[2] is None or error[0] < acc[2][0]):
                acc[2] = error
            if acc[0] is None:
                acc[0] = counts
            else:
                k = min(len(acc[0]), len(counts))
                acc[0] = acc[0][:k] + counts[:k]
    stops = [
        _stop(totals, ngains, first, stop_fraction) for totals, ngains, first in runs
    ]
    iters = [j + 1 for j, _ in stops] if multi else stops[0][0] + 1
    if d is None:
        results = [run(c, iters, STOP_OFF, False) for c in chunks]
    else:
        results = []
        for result, pos, values in _dispatched(d, len(chunks), iters, STOP_OFF, False):
            row_w[pos] = values
            results.append(result)
    j, fraction = stops[0]
    return results, (j + 1, float(fraction))


def _stop(totals, ngains, first, stop_fraction):
    """The one-call solve's stop `(iteration, converged fraction)` from one
    run's summed counts; raises its error when no stop comes before it."""
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
    return j, fraction


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


__all__ = [
    "AVERAGE_BLOCK_SHARE",
    "STOP_OFF",
    "Average",
    "Chunk",
    "gauge",
    "load",
    "load_averaged",
    "plan",
    "replayed",
    "trace_buffer",
]
