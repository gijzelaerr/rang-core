# SPDX-License-Identifier: MIT
"""The diagonal gain solve streamed over its cells (issue #34,
research/selfcal-memory.md).

A self-calibration term Sp or Sa (`rang.cal_gain`'s kernel with QuartiCal's
rules) solves each solution interval whole. When one interval does not fit
`data.memory_limit_gb`, `solve_field` reads the field once in blocks of
whole rows, prepares them as the one-call solve does (`_Field.prepare`,
`cal_gain.finite_cells`, autocorrelations and FLAG_ROW) and writes the
unflagged cells (`solve::data_flags`) to a scratch file beside the MS, in
row then channel order, with their interval and antennas. The Rust solver
(`rang._core.cal_gain_solve_streamed`, `rang_core::cal::diag_stream`) then
reads that file in blocks on every iteration. The solution (gains, flags,
iterations, converged fraction) and the row weights equal the one-call
solve's bit for bit; CASA's statistics `snr` and `err` are not computed
(NaN), and nothing that reads them takes this path.

Resident memory: the field's row metadata and the gains, then one read block
of the first pass or the solver's read block (at most `READ_BLOCK` records). Disk: `RECORD_BYTES` per
unflagged cell (one channel of one row), removed after the solve.
"""

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np

from . import core_chunks, core_ms

# One record: interval, antenna 1, antenna 2 (uint32), then data (8),
# model (8) and weights (4) as float32 (rang_core::cal::diag_stream).
RECORD_WORDS = 23
RECORD_BYTES = 4 * RECORD_WORDS
# The most records the solver reads per block on each iteration, and the
# bytes one record of that block holds resident: the raw record, the decoded
# cell and its grouping.
READ_BLOCK = 1 << 20
READ_RECORD_BYTES = 2 * RECORD_BYTES + 32
# Bytes per gain held for the solve (live flags, gains, flags, sums).
GAIN_BYTES = 256


def blocks(budget, nrows, nchan, ncorr, ngain, what):
    """`(rows, records)`: the rows of all channels one block of the read
    pass may hold under `budget` (a `core_chunks.ChainBudget`, at its
    `cell_bytes`; None: every row), and the records of the solver's read
    block, each after the field's row metadata and the gains. The pass and
    the solver do not hold their blocks at the same time. A
    MemoryLimitError when one row or one record does not fit."""
    cells = int(nrows) * int(nchan)
    if budget is None:
        return max(1, int(nrows)), max(1, min(READ_BLOCK, cells))
    left = (
        budget.chunk_bytes
        - core_chunks.CHAIN_ROW_BYTES * int(nrows)
        - GAIN_BYTES * int(ngain)
    )
    row = int(nchan) * int(ncorr)
    rows = left // (budget.cell_bytes * row)
    records = min(READ_BLOCK, cells, left // READ_RECORD_BYTES)
    if rows < 1 or records < 1:
        need = core_chunks._gib(
            budget.fixed_bytes
            + core_chunks.CHAIN_ROW_BYTES * int(nrows)
            + GAIN_BYTES * int(ngain)
            + max(budget.cell_bytes * row, READ_RECORD_BYTES)
        )
        limit = (
            ""
            if budget.limit_gb is None
            else f", above data.memory_limit_gb {budget.limit_text or budget.limit_gb}"
        )
        raise core_chunks.MemoryLimitError(
            f"{what}: the streamed solve needs {need:.3f} GiB for one row of "
            f"{nchan} channels and {nrows} rows{limit}; raise the limit"
        )
    return int(rows), max(1, int(records))


def _cells(got, flag_row, a1, a2):
    """The one-call kernel's arrays of one block (`cal_gain._kernel`'s
    conversions and `finite_cells`) and its unflagged cells
    (`solve::data_flags`): `(data, model, weights, good)`."""
    from . import cal_gain

    data = np.ascontiguousarray(got["data"], np.complex64)
    model = np.ascontiguousarray(
        np.broadcast_to(got["model"], data.shape), np.complex64
    )
    weights = np.ascontiguousarray(
        np.broadcast_to(got["weights"], data.shape), np.float32
    )
    flag = np.ascontiguousarray(np.broadcast_to(got["flag"], data.shape), np.uint8)
    data, model, weights, flag = cal_gain.finite_cells(data, model, weights, flag)
    rowflag = np.asarray(flag_row, bool) | (a1 == a2)
    bad = flag.any(-1)
    bad |= rowflag[:, None]
    for c in (0, 3):
        bad |= data[..., c] == 0
        bad |= weights[..., c] == 0
    return data, model, weights, ~bad


def solve_field(
    fld, tb, *, nchan, freq_bin, budget, what, nant, calmode, refants,
    max_iterations, stop_criterion, stop_fraction, scratch=None,
):  # fmt: skip
    """`cal_gain._kernel`'s result (a dict: `gains`, `kernel_flags`, `snr`,
    `err`, `ok`, `iterations`, `fraction`) for the rows of `fld` (a
    `cal_gain._Field`) with interval index `tb`, `freq_bin` per channel
    (None: one bin), QuartiCal's rules (no `minblperant`, referencing to
    `refants[0]`), streamed under `budget`. Also returns the rows' weight
    sums (`row_w`) and a record of the stream. `scratch`: the directory
    for the cell file (default beside the MS)."""
    from . import _core, cal_gain

    if calmode not in cal_gain.KINDS:
        raise ValueError(f"calmode must be one of {sorted(cal_gain.KINDS)}")
    tb = np.asarray(tb, np.int64)
    n = len(tb)
    if n == 0:
        raise ValueError(f"no data to solve: 0 rows of {nchan} channels")
    fb = (
        np.zeros(nchan, np.int64)
        if freq_bin is None
        else np.asarray(freq_bin, np.int64)[:nchan]
    )
    ntime, nfreq = int(tb.max()) + 1, int(fb.max()) + 1
    ngain = ntime * nfreq * int(nant)
    step, read_block = blocks(budget, n, nchan, 4, ngain, what)
    a1_all = np.asarray(fld.meta["ANTENNA1"], np.int64)
    a2_all = np.asarray(fld.meta["ANTENNA2"], np.int64)
    if n and max(a1_all.max(), a2_all.max()) >= nant:
        raise ValueError("antenna index out of range")
    row_w = np.zeros(n)
    live = np.zeros(ngain, bool)
    where = Path(scratch) if scratch is not None else Path(fld.ms).resolve().parent
    tmp = Path(tempfile.mkdtemp(prefix=".rang-stream-", dir=where))
    started = time.perf_counter()
    try:
        path = tmp / "cells.bin"
        ncells = 0
        with core_ms.open_table(fld.ms) as reader, open(path, "wb") as out:
            for b in range(0, n, step):
                pos = np.arange(b, min(n, b + step))
                cols = {
                    name: core_chunks.read_rows(reader, name, fld.rows[pos])
                    for name in fld.cells
                }
                got = fld.prepare(pos, cols)
                del cols
                row_w[pos] = got.pop("row_w")
                a1, a2 = a1_all[pos], a2_all[pos]
                data, model, weights, good = _cells(got, fld.flag_row[pos], a1, a2)
                del got
                r, c = np.nonzero(good)
                del good
                k = len(r)
                if not k:
                    continue
                interval = tb[pos][r] * nfreq + fb[c]
                live[interval * nant + a1[r]] = True
                live[interval * nant + a2[r]] = True
                rec = np.empty((k, RECORD_WORDS), np.float32)
                words = rec.view(np.uint32)
                words[:, 0] = interval
                words[:, 1] = a1[r]
                words[:, 2] = a2[r]
                del interval
                rec[:, 3:11] = data[r, c].view(np.float32)
                del data
                rec[:, 11:19] = model[r, c].view(np.float32)
                del model
                rec[:, 19:23] = weights[r, c]
                del weights, r, c
                rec.tofile(out)
                ncells += k
                del rec
        read_seconds = time.perf_counter() - started
        g = np.zeros(4 * ngain, np.float64)
        gf = np.zeros(ngain, np.int8)
        iterations, fraction = _core.cal_gain_solve_streamed(
            str(path), int(ncells), read_block, ntime, nfreq, int(nant),
            live.astype(np.uint8), cal_gain.KINDS[calmode], int(max_iterations),
            float(stop_criterion), float(stop_fraction), int(refants[0]), g, gf,
        )  # fmt: skip
        nbytes = path.stat().st_size
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shape = (ntime, nfreq, int(nant))
    raw = {
        "gains": g.view(np.complex128).reshape(*shape, 2),
        "kernel_flags": gf.reshape(shape) != 0,
        "snr": np.full((*shape, 2), np.nan, np.float32),
        "err": np.full((*shape, 2), np.nan, np.float32),
        "ok": np.ones(shape, bool),
        "iterations": int(iterations),
        "fraction": float(fraction),
    }
    record = {
        "cells": int(ncells),
        "file_bytes": int(nbytes),
        "block_rows": int(step),
        "read_block": int(read_block),
        "read_seconds": read_seconds,
        "seconds": time.perf_counter() - started,
    }
    return raw, row_w, record
