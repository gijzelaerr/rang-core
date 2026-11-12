# SPDX-License-Identifier: GPL-3.0-or-later
"""Chunking by time and row for whole-array data (task W3, research/w3-chunking.md).

The rang-core stages run within `data.memory_limit_gb` (GiB of resident
memory). This module turns that limit into chunk sizes and holds the pieces
the stages share:

- `Budget`: the bytes left for chunk arrays once the process itself and the
  row metadata held for the whole stage are counted, and the rows or cells a
  chunk of a given stage may hold;
- `runs`, `read_rows`, `write_rows`: rows read and written in runs of
  consecutive row numbers, through a reader (`core_ms.Table`) or a W1
  `WriteBack` session;
- `baseline_blocks`: the flagger's chunks, blocks of consecutive baselines of
  one field and scan group, each flagged on the group's whole time grid;
- `solve_chunks` and `replay_stop`: the solver's chunks, whole solution
  intervals, and the replay of the solver's global stop test over them.

Chunking changes no arithmetic: every stage gives the bit-identical result at
any chunk size (research/w3-chunking.md, section 3).
"""

import re
from dataclasses import dataclass

import numpy as np

GIB = 1 << 30
DEFAULT_LIMIT_GB = 8.0
# Fitted from probe runs (research/w3-chunking.md, section 5.1), with margins:
# the resident size of a stage's process before it reads any visibilities
# (Python, NumPy, the extension, the reader, the subtables) ...
BASE_BYTES = 640 << 20
# ... the bytes held per MS row for the whole stage (TIME and the row columns
# of `core_pipeline.inspect_ms`, selections, row-to-bin maps) ...
ROW_BYTES = 160
# ... and the bytes per visibility cell (one channel of one correlation) of a
# chunk while a stage works on it: the columns read, the copies the kernels
# make and the outputs before they are written.
CELL_BYTES = {
    "flag": 32,
    "calibrate": 64,
    "apply": 64,
    "model": 64,
    "rows": 24,
    # The K, G, B, F and polarisation solves (tasks C2e, C6w; chunked by task
    # W3b, research/w3b-chainchunks.md): the cell columns read, their
    # pre-applied copies, the weights and the kernel's sorted copies.
    "chain": 96,
}
# Bytes held per row of a chain solve's field for the whole solve (task W3b):
# the row metadata, the interval index, the uvrange flag and the row's weight
# sum for the solution times.
CHAIN_ROW_BYTES = 128


class MemoryLimitError(ValueError):
    """The memory limit cannot hold what a stage needs at least."""


def _gib(nbytes):
    return nbytes / GIB


@dataclass(frozen=True)
class Budget:
    """Chunk sizes of one MS under `limit_gb` (and `chunk_rows`, a cap on the
    rows of every chunk when set)."""

    limit_gb: float
    nrows: int
    cell: tuple
    chunk_rows: int | None = None

    @property
    def limit_bytes(self):
        return int(self.limit_gb * GIB)

    @property
    def fixed_bytes(self):
        return BASE_BYTES + ROW_BYTES * int(self.nrows)

    @property
    def chunk_bytes(self):
        """Bytes left for chunk arrays (MemoryLimitError when none)."""
        left = self.limit_bytes - self.fixed_bytes
        if left <= 0:
            raise MemoryLimitError(
                f"data.memory_limit_gb {self.limit_gb:g}: the stage itself needs about "
                f"{_gib(self.fixed_bytes):.2f} GiB for {self.nrows} rows before it reads "
                "any visibilities; raise the limit"
            )
        return left

    def cells(self, stage, capped=True):
        """Visibility cells (channel x correlation) a chunk of `stage` holds
        under the limit, and under `chunk_rows` when `capped`."""
        cells = self.chunk_bytes // CELL_BYTES[stage]
        if capped and self.chunk_rows:
            cells = min(cells, int(self.chunk_rows) * int(np.prod(self.cell)))
        return int(cells)

    def rows(self, stage, capped=True):
        """Rows of full cells a chunk of `stage` holds, under `chunk_rows`
        too when `capped` (at least one when one row fits the memory;
        MemoryLimitError when not)."""
        per_row = int(np.prod(self.cell))
        if self.chunk_bytes < CELL_BYTES[stage] * per_row:
            raise MemoryLimitError(
                f"data.memory_limit_gb {self.limit_gb:g}: one row of {self.cell} cells "
                f"needs {_gib(CELL_BYTES[stage] * per_row + self.fixed_bytes):.2f} GiB in "
                f"{stage}; raise the limit"
            )
        rows = max(1, self.chunk_bytes // (CELL_BYTES[stage] * per_row))
        if capped and self.chunk_rows:
            rows = min(rows, int(self.chunk_rows))
        return int(rows)

    def need_gb(self, stage, cells):
        """GiB a chunk of `cells` cells needs in `stage`, the process included."""
        return _gib(self.fixed_bytes + CELL_BYTES[stage] * int(cells))

    def chain(self):
        """The `ChainBudget` of the K, G, B, F and polarisation solves (task
        W3b)."""
        return ChainBudget(
            self.chunk_bytes, self.fixed_bytes, self.limit_gb, self.chunk_rows
        )

    def describe(self):
        out = {
            "memory_limit_gb": self.limit_gb,
            "chunk_rows": self.chunk_rows,
            "fixed_gb": _gib(self.fixed_bytes),
        }
        try:
            out["chunk_gb"] = _gib(self.chunk_bytes)
            out["rows"] = {s: self.rows(s) for s in CELL_BYTES}
        except MemoryLimitError as exc:
            out["error"] = str(exc)
        return out


@dataclass(frozen=True)
class ChainBudget:
    """Chunk sizes of a K, G, B, F or polarisation solve on one field (task
    W3b, research/w3b-chainchunks.md): `chunk_bytes` for chunk arrays (of
    `Budget`), less `CHAIN_ROW_BYTES` per row of the field."""

    chunk_bytes: int
    fixed_bytes: int = 0
    limit_gb: float | None = None
    chunk_rows: int | None = None

    def plan(self, nrows, nchan, ncorr, per_channel):
        """`(max_cells, hard_cells, block_rows)` of a solve on `nrows` rows:
        the cells a chunk may hold (under `chunk_rows` too), the memory's
        own limit on them, and the rows of all channels a read block may
        hold. Per-channel terms (B, Xf, Df) give half to a chunk and half to
        a block of whole rows. A block is a read buffer, not a chunk:
        `chunk_rows` does not cap it (W3 read a frequency chunk's rows
        whole). `hard_cells` is negative when the rows alone do not fit."""
        left = self.chunk_bytes - CHAIN_ROW_BYTES * int(nrows)
        hard = left // CELL_BYTES["chain"]
        if per_channel:
            hard //= 2
        row = int(nchan) * int(ncorr)
        block = hard // row
        cells = hard
        if self.chunk_rows:
            cells = min(cells, int(self.chunk_rows) * row)
        return int(cells), int(hard), int(block)

    def need_gb(self, nrows, cells, per_channel):
        """GiB a solve on `nrows` rows needs for a chunk of `cells` cells
        (and, per channel, a block of one whole row), the process
        included."""
        cell = CELL_BYTES["chain"] * int(cells) * (2 if per_channel else 1)
        return _gib(self.fixed_bytes + CHAIN_ROW_BYTES * int(nrows) + cell)


def budget(config, info):
    """The `Budget` of `config['data']` for the MS described by `info`
    (`core_pipeline.inspect_ms`)."""
    data = config["data"]
    limit = data.get("memory_limit_gb")
    return Budget(
        float(DEFAULT_LIMIT_GB if limit is None else limit),
        int(info["nrows"]),
        tuple(info["cell"]),
        data.get("chunk_rows"),
    )


# -- rows --------------------------------------------------------------------------


def runs(rows):
    """[(start, n)] of consecutive row numbers in `rows` (ascending)."""
    rows = np.asarray(rows, np.int64)
    if not len(rows):
        return []
    if np.any(np.diff(rows) <= 0):
        raise ValueError("rows must be strictly ascending")
    breaks = np.flatnonzero(np.diff(rows) != 1) + 1
    starts = np.concatenate([[0], breaks])
    ends = np.concatenate([breaks, [len(rows)]])
    return [(int(rows[s]), int(e - s)) for s, e in zip(starts, ends)]


def _getter(source):
    """`(name, start, n) -> array` of a `WriteBack` session or a reader."""
    if hasattr(source, "write_flags"):  # core_writeback.WriteBack
        return source.read
    return lambda name, start, n: source.getcol(name, int(start), int(n))


def _rows_getter(source):
    """`(name, rows, chans) -> array` of a `WriteBack` session or a core
    reader (`core_ms`, `core_ms_write`), which read a list of rows and a
    channel slice in one call; None for other readers."""
    if hasattr(source, "write_flags"):  # core_writeback.WriteBack
        return getattr(source, "read_rows", None)
    get = getattr(source, "getcol_rows", None)
    if get is None:
        return None
    return lambda name, rows, chans: get(name, rows, chans=chans)


def read_rows(source, name, rows, chans=None, block_rows=None):
    """Column `name` at `rows` (any order; duplicates not allowed) from a
    `WriteBack` session or a reader, in the order of `rows`. `chans` (a
    slice) keeps only those channels. The core's readers read the rows in
    one call per block of `block_rows` rows, only the channels kept
    (research/sliced-read.md); other readers (python-casacore) read runs of
    consecutive rows and cut the channels in NumPy."""
    rows = np.asarray(rows, np.int64)
    if not len(rows):
        raise ValueError("no rows")
    step = len(rows) if not block_rows else max(1, int(block_rows))
    sliced = _rows_getter(source)
    if sliced is not None:
        if step >= len(rows):
            return sliced(name, rows, chans)
        out = None
        for b in range(0, len(rows), step):
            values = sliced(name, rows[b : b + step], chans)
            if out is None:
                out = np.empty((len(rows), *values.shape[1:]), values.dtype)
            out[b : b + len(values)] = values
            del values
        return out
    get = _getter(source)
    out = None
    for b in range(0, len(rows), step):
        part = rows[b : b + step]
        order = np.argsort(part, kind="stable")
        ascending = part[order]
        pieces = [get(name, s, n) for s, n in runs(ascending)]
        values = pieces[0] if len(pieces) == 1 else np.concatenate(pieces)
        del pieces
        if chans is not None:
            values = values[:, chans]
        if out is None:
            out = np.empty((len(rows), *values.shape[1:]), values.dtype)
        out[b + order] = values
        del values
    return out


def write_rows(session, name, rows, values):
    """Write `values` (one per row of `rows`, ascending) in runs through a
    `WriteBack` session; FLAG goes through `write_flags`."""
    rows = np.asarray(rows, np.int64)
    at = 0
    for start, n in runs(rows):
        if name == "FLAG":
            session.write_flags(start, values[at : at + n])
        else:
            session.write(name, start, values[at : at + n])
        at += n


# -- the flagger's chunks --------------------------------------------------------


def baseline_blocks(baseline_index, nbl, max_rows):
    """Blocks of consecutive baselines (indices into Tricolour's baseline
    order) whose rows add up to at most `max_rows` (one baseline at least).
    `baseline_index` holds each row's baseline. Returns [array of baselines]."""
    counts = np.bincount(np.asarray(baseline_index, np.int64), minlength=nbl)
    blocks, current, total = [], [], 0
    for b in range(nbl):
        if current and total + counts[b] > max_rows:
            blocks.append(np.array(current, np.int64))
            current, total = [], 0
        current.append(b)
        total += int(counts[b])
    if current:
        blocks.append(np.array(current, np.int64))
    return blocks


# -- the solver's chunks ---------------------------------------------------------


@dataclass(frozen=True)
class SolveChunk:
    """Time bins [t0, t1) and frequency bins [f0, f1) of one partition, its
    rows (a slice of the partition's time-sorted rows) and channels."""

    t0: int
    t1: int
    f0: int
    f1: int
    rows: slice
    chans: slice


def solve_chunks(time_bin, freq_bin, max_cells, ncorr, hard_cells=None):
    """Chunks of whole solution intervals of one partition, rows sorted by
    time bin: consecutive time bins while their rows fit `max_cells`; a time
    bin that does not fit alone is split into consecutive frequency bins.
    A chunk always holds one interval: when the largest interval exceeds
    `max_cells` but not `hard_cells` (the memory limit, when `max_cells` is a
    `chunk_rows` cap), chunks hold one interval at least. Returns
    ([SolveChunk], largest interval in cells), or (None, largest) when the
    largest interval exceeds `hard_cells` (default `max_cells`)."""
    time_bin = np.asarray(time_bin, np.int64)
    freq_bin = np.asarray(freq_bin, np.int64)
    if np.any(np.diff(time_bin) < 0):
        raise ValueError("rows must be sorted by time bin")
    nchan = len(freq_bin)
    ntime = int(time_bin.max()) + 1
    nfreq = int(freq_bin.max()) + 1
    bounds = np.searchsorted(time_bin, np.arange(ntime + 1))
    rows_of = np.diff(bounds)
    fbounds = np.searchsorted(freq_bin, np.arange(nfreq + 1))
    chans_of = np.diff(fbounds)
    largest = int(rows_of.max()) * int(chans_of.max()) * ncorr
    if largest > (max_cells if hard_cells is None else hard_cells):
        return None, largest
    max_cells = max(max_cells, largest)
    chunks = []
    t = 0
    while t < ntime:
        if rows_of[t] * nchan * ncorr > max_cells:
            f = 0
            while f < nfreq:
                g = f + 1
                while (
                    g < nfreq
                    and rows_of[t] * (fbounds[g + 1] - fbounds[f]) * ncorr <= max_cells
                ):
                    g += 1
                chunks.append(
                    SolveChunk(
                        t,
                        t + 1,
                        f,
                        g,
                        slice(int(bounds[t]), int(bounds[t + 1])),
                        slice(int(fbounds[f]), int(fbounds[g])),
                    )
                )
                f = g
            t += 1
            continue
        u = t + 1
        while u < ntime and (bounds[u + 1] - bounds[t]) * nchan * ncorr <= max_cells:
            u += 1
        chunks.append(
            SolveChunk(
                t, u, 0, nfreq, slice(int(bounds[t]), int(bounds[u])), slice(0, nchan)
            )
        )
        t = u
    return chunks, largest


_COUNTS = re.compile(r'"gain_converged":(\d+),"gain_flagged":(\d+)')


def trace_counts(path):
    """[(converged, flagged)] per iteration of a solver trace file
    (`core.solve_complex(trace=...)`), without parsing its per-interval
    arrays."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return [(int(a), int(b)) for a, b in _COUNTS.findall(text)]


def replay_stop(totals, ngains, stop_fraction):
    """The iteration at which `solve.rs::decide` stops (0-based) and the
    converged fraction there, from the per-iteration (converged, flagged)
    totals of every interval of a partition; the last iteration when the
    loop runs to its maximum."""
    fraction = 0.0
    for j, (converged, flagged) in enumerate(totals):
        solvable = ngains - flagged
        fraction = converged / solvable if solvable > 0 else 0.0
        if fraction >= stop_fraction:
            return j, fraction
    return len(totals) - 1, fraction


__all__ = [
    "CELL_BYTES",
    "CHAIN_ROW_BYTES",
    "DEFAULT_LIMIT_GB",
    "Budget",
    "ChainBudget",
    "MemoryLimitError",
    "SolveChunk",
    "baseline_blocks",
    "budget",
    "read_rows",
    "replay_stop",
    "runs",
    "solve_chunks",
    "trace_counts",
    "write_rows",
]
