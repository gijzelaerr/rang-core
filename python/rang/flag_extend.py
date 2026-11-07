"""CASA's `flagdata(mode='extend')` as CARACal runs it (task E0).

research/e0-refant-extend.md sections 1.2 and 1.3. CARACal 8f7bb363's polcal
worker, before its first solve, runs `flagdata(mode='extend', ntime='60s',
combinescans=True, growtime=80, growfreq=80, growaround=True,
flagnearfreq=True, flagneartime=True)` on the polarisation calibrator and
then on the leakage calibrator. CASA 6.7.6 iterates the selected rows in
chunks sorted by OBSERVATION_ID, ARRAY_ID, FIELD_ID, DATA_DESC_ID and TIME
(no SCAN_NUMBER with `combinescans`); casacore's `MSInterval` starts a chunk
at the first unused time t0 and keeps the rows with
`floor((t - (t0 - 0.01)) / ntime) == floor((t0 - (t0 - 0.01)) / ntime)`.
Within a chunk each (ANTENNA1, ANTENNA2) pair's rows, in time order, form
one (correlation, channel, row) cube that the Rust kernel
(`rang._core.flag_extend`, `core/src/flag_extend.rs`) extends. Flags are
only added; FLAG_ROW is not written.
"""

import hashlib
import itertools
import math
from pathlib import Path

import numpy as np

from . import core_writeback

# CARACal's flagdata arguments (polcal_worker.py, "preliminary flags").
CARACAL = {
    "ntime": 60.0,
    "growtime": 80.0,
    "growfreq": 80.0,
    "growaround": True,
    "flagneartime": True,
    "flagnearfreq": True,
    "extendpols": True,
}
RULES = (
    "neartime",
    "nearfreq",
    "growaround",
    "grown",
    "growfreq",
    "growtime",
    "extendpols",
)
META = ("OBSERVATION_ID", "ARRAY_ID", "FIELD_ID", "DATA_DESC_ID", "TIME", "ANTENNA1",
        "ANTENNA2", "SCAN_NUMBER")  # fmt: skip


def casa_chunks(obs, array, field, ddid, time, ntime=60.0):
    """Chunk number of every row, as CASA's flagdata iterates them with
    `combinescans=True` (casacore `MSIter` with `MSInterval`)."""
    n = len(time)
    chunk = np.full(n, -1, np.int64)
    if not n:
        return chunk
    order = np.lexsort((time, ddid, field, array, obs))
    key = np.stack([obs, array, field, ddid], axis=1)[order]
    t = np.asarray(time, np.float64)[order]
    breaks = np.flatnonzero(np.any(key[1:] != key[:-1], axis=1)) + 1
    bounds = np.concatenate([[0], breaks, [n]])
    k = 0
    for lo, hi in itertools.pairwise(bounds):
        times = t[lo:hi]
        uniq = np.unique(times)
        ids = np.empty(len(uniq), np.int64)
        i = 0
        while i < len(uniq):
            t0 = uniq[i]
            offset = t0 - 0.01
            ref = math.floor((t0 - offset) / ntime)
            j = i + 1
            while j < len(uniq) and math.floor((uniq[j] - offset) / ntime) == ref:
                j += 1
            ids[i:j] = k
            k += 1
            i = j
        chunk[order[lo:hi]] = ids[np.searchsorted(uniq, times)]
    return chunk


def segments(chunk, a1, a2, time):
    """(order, starts): rows grouped by (chunk, ANTENNA1, ANTENNA2), each
    group in time order (then row order), for the kernel."""
    rows = np.flatnonzero(chunk >= 0)
    if not len(rows):
        return np.zeros(0, np.uint64), np.zeros(1, np.uint64)
    order = rows[np.lexsort((rows, time[rows], a2[rows], a1[rows], chunk[rows]))]
    key = np.stack([chunk[order], a1[order], a2[order]], axis=1)
    breaks = np.flatnonzero(np.any(key[1:] != key[:-1], axis=1)) + 1
    starts = np.concatenate([[0], breaks, [len(order)]])
    return order.astype(np.uint64), starts.astype(np.uint64)


def extend_flags(flag, a1, a2, time, chunk, settings=None):
    """Extend `flag` (bool or uint8, `(row, chan, corr)`) in place for the
    rows with `chunk >= 0`; returns the cells each rule added."""
    from . import _core

    s = dict(CARACAL, **(settings or {}))
    order, starts = segments(np.asarray(chunk), np.asarray(a1), np.asarray(a2),
                             np.asarray(time))  # fmt: skip
    work = np.ascontiguousarray(flag, dtype=np.uint8)
    _, nchan, npol = work.shape
    counts = {r: 0 for r in RULES}
    if len(order):
        counts = _core.flag_extend(
            work, nchan, npol, order, starts, float(s["growtime"]), float(s["growfreq"]),
            bool(s["growaround"]), bool(s["flagneartime"]), bool(s["flagnearfreq"]),
            bool(s["extendpols"]),
        )  # fmt: skip
    flag[...] = work.astype(flag.dtype, copy=False)
    return {r: int(counts[r]) for r in RULES}


def extend_ms(
    ms,
    fields,
    *,
    scans=None,
    settings=None,
    chunk_rows=None,
    batch_rows=None,
    flag_backup=core_writeback.DEFAULT_BACKUP,
    stage="calibrate",
):
    """CARACal's flag extension on the rows of `fields` (MS field ids) and,
    when given, `scans`, of `ms`; FLAG written through
    `core_writeback.WriteBack` (`flag_backup` saved before the first write).
    Whole CASA chunks are read and extended together, up to `batch_rows`
    rows a batch (a larger chunk in blocks of whole baselines, task W3b).
    Returns a summary."""
    ms = Path(ms)
    s = dict(CARACAL, **(settings or {}))
    with core_writeback.WriteBack(
        ms, flag_backup=flag_backup, stage=stage, chunk_rows=chunk_rows
    ) as w:
        spans = list(w.chunks(chunk_rows))
        meta = {k: np.concatenate([w.read(k, s0, n) for s0, n in spans]) for k in META}
        keep = np.isin(meta["FIELD_ID"], [int(f) for f in fields])
        if scans is not None:
            keep &= np.isin(meta["SCAN_NUMBER"], [int(v) for v in np.atleast_1d(scans)])
        rows = np.flatnonzero(keep)
        chunk = np.full(len(keep), -1, np.int64)
        chunk[rows] = casa_chunks(
            *(meta[k][rows] for k in ("OBSERVATION_ID", "ARRAY_ID", "FIELD_ID",
                                      "DATA_DESC_ID", "TIME")), ntime=s["ntime"],
        )  # fmt: skip
        nchunk = int(chunk.max()) + 1 if len(rows) else 0
        limit = batch_rows or w.chunk_rows()
        sizes = (
            np.bincount(chunk[rows], minlength=nchunk) if nchunk else np.zeros(0, int)
        )
        counts = {r: 0 for r in RULES}
        before = after = 0
        digest = hashlib.sha256()
        for mine in _batches(rows, chunk, meta["ANTENNA1"], meta["ANTENNA2"],
                             sizes, limit):  # fmt: skip
            flag = _read_rows(w, "FLAG", mine, spans)
            before += int(flag.sum())
            got = extend_flags(flag, meta["ANTENNA1"][mine], meta["ANTENNA2"][mine],
                               meta["TIME"][mine], chunk[mine])  # fmt: skip
            for r in RULES:
                counts[r] += got[r]
            after += int(flag.sum())
            _write_rows(w, mine, flag, spans)
        cells = len(rows) * int(np.prod(w.cell))
        for s0, n in spans:
            pick = rows[(rows >= s0) & (rows < s0 + n)]
            if len(pick):
                digest.update(
                    np.ascontiguousarray(w.read("FLAG", s0, n)[pick - s0]).tobytes()
                )
    return {
        "fields": sorted(int(f) for f in fields),
        "scans": None
        if scans is None
        else sorted(int(v) for v in np.atleast_1d(scans)),
        "settings": s,
        "rows": len(rows),
        "chunks": nchunk,
        "cells": cells,
        "flagged_before": before,
        "flagged_after": after,
        "added": counts,
        "flag_sha256": digest.hexdigest(),
    }


def _batches(rows, chunk, a1, a2, sizes, limit):
    """The MS rows (sorted) of each batch: consecutive whole CASA chunks up
    to `limit` rows; a chunk larger than `limit` is split into blocks of
    whole baselines (task W3b, research/w3b-chainchunks.md). The kernel
    extends every (chunk, ANTENNA1, ANTENNA2) cube on its own, so the flags
    do not depend on the batches."""
    from . import core_chunks

    nchunk = len(sizes)
    lo = 0
    while lo < nchunk:
        if sizes[lo] > limit:
            mine = rows[chunk[rows] == lo]
            key = a1[mine].astype(np.int64) * (1 << 32) + a2[mine].astype(np.int64)
            ubl, inverse = np.unique(key, return_inverse=True)
            inverse = inverse.reshape(-1)
            for block in core_chunks.baseline_blocks(inverse, len(ubl), limit):
                yield mine[np.isin(inverse, block)]
            lo += 1
            continue
        hi, total = lo, 0
        while hi < nchunk and (hi == lo or total + sizes[hi] <= limit):
            total += sizes[hi]
            hi += 1
        yield rows[(chunk[rows] >= lo) & (chunk[rows] < hi)]
        lo = hi


def _read_rows(w, name, rows, spans):
    """`name` at MS rows `rows` (sorted), read span by span."""
    out = None
    for s0, n in spans:
        pick = (rows >= s0) & (rows < s0 + n)
        if not pick.any():
            continue
        part = w.read(name, s0, n)[rows[pick] - s0]
        if out is None:
            out = np.empty((len(rows), *part.shape[1:]), part.dtype)
        out[pick] = part
    return out


def _write_rows(w, rows, flag, spans):
    for s0, n in spans:
        pick = (rows >= s0) & (rows < s0 + n)
        if not pick.any():
            continue
        out = w.read("FLAG", s0, n)
        out[rows[pick] - s0] = flag[pick]
        w.write_flags(s0, out)


__all__ = ["CARACAL", "RULES", "casa_chunks", "extend_flags", "extend_ms", "segments"]
