"""Zarr ingest at the edge of the Rang core (research/core-section6.md).

Reads blosc-compressed zarr v2 chunks and decodes them with the core's Rust
blosc decoder. `read_rows` reads only the byte spans of the blosc blocks that
hold the requested rows, using the block-start table, so a large chunk is
neither read nor decoded in full. The same spans could be fetched with HTTP
range requests. Object and pickle columns are not handled here. The core is
reached through `core.extension()` (research/core-j-packaging.md,
research/p7-architecture.md).
"""

import json
import time
from pathlib import Path

import numpy as np

from . import core

HEADER = 16
MEMCPYED = 0x02


def check_meta(meta, name="zarr array", dtype=None):
    """Refuse `.zarray` metadata the core would decode wrongly (task W4-2,
    W4R-09): filters, object dtypes, other compressors, Fortran order (read
    in C order it comes out transposed), big-endian dtypes, and a dtype other
    than `dtype` when one is expected. Returns `meta`."""
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"{name}: object or filtered zarr arrays are not supported")
    if (meta.get("compressor") or {}).get("id") != "blosc":
        raise ValueError(f"{name}: only blosc-compressed zarr arrays are supported")
    if meta.get("order") != "C":
        order = meta.get("order")
        raise ValueError(
            f"{name}: only C-ordered zarr arrays are supported, not order {order!r}"
        )
    if np.dtype(meta["dtype"]).byteorder == ">":
        raise ValueError(f"{name}: big-endian dtype {meta['dtype']} is not supported")
    if dtype is not None and np.dtype(meta["dtype"]) != np.dtype(dtype):
        raise ValueError(f"{name}: dtype {meta['dtype']}, expected {dtype}")
    return meta


def array_meta(array_dir, dtype=None):
    """The checked `.zarray` metadata (`check_meta`)."""
    path = Path(array_dir) / ".zarray"
    meta = json.loads(path.read_text(encoding="utf-8"))
    return check_meta(meta, str(array_dir), dtype)


def header_fields(head):
    ext = core.extension()
    status, fields = ext.blosc_header(bytes(head))
    if status:
        raise ValueError("unsupported or invalid blosc header")
    nbytes, blocksize, nblocks, typesize = (int(x) for x in fields)
    return nbytes, blocksize, nblocks, typesize


def block_table(prefix):
    """(starts, ends, prefix length, nblocks) from a chunk's first bytes: the
    header and, unless the chunk is memcpyed, its block-start table. `ends`
    assumes the blocks are stored in order (see `blocks_in_order`)."""
    nbytes, blocksize, nblocks, _ = header_fields(prefix[:HEADER])
    cbytes = int.from_bytes(prefix[12:16], "little")
    if prefix[2] & MEMCPYED:
        starts = HEADER + np.arange(nblocks, dtype=np.int64) * blocksize
        ends = np.minimum(starts + blocksize, HEADER + nbytes)
        used = HEADER
    else:
        used = HEADER + 4 * nblocks
        if len(prefix) < used:
            raise ValueError("blosc start table longer than the fetched prefix")
        starts = np.frombuffer(prefix[HEADER:used], "<u4").astype(np.int64)
        ends = np.append(starts[1:], cbytes)
    return starts, ends, used, nblocks


def blocks_in_order(starts):
    """True when the blocks are stored in ascending order. Multithreaded
    blosc (as in QuartiCal's stores; research/dfio-formats.md) may store them
    out of order; then a run of blocks is not one byte span, and the readers
    decode the whole chunk instead (`whole_chunk_rows`)."""
    return not np.any(np.diff(starts) <= 0)


def whole_chunk_rows(chunk, row_bytes, rows):
    """Rows `rows` of a whole chunk (bytes or a uint8 array) decoded in full,
    as a `(len(rows), row_bytes)` uint8 array: the out-of-order fallback."""
    data = np.frombuffer(core.blosc_decode(bytes(chunk)), np.uint8)
    if len(rows) and (rows[-1] + 1) * row_bytes > len(data):
        raise ValueError("row beyond the chunk")
    return data[: (len(data) // row_bytes) * row_bytes].reshape(-1, row_bytes)[rows]


def check_rows_covered(head, first, count, row_bytes, rows):
    """ValueError unless every row of `rows` (ascending) lies entirely inside
    the decoded bytes of blocks `first`..`first + count` (task W4-2, W4R-10;
    the core refuses such rows too)."""
    nbytes, blocksize, _, _ = header_fields(head[:HEADER])
    rows = np.asarray(rows, dtype=np.int64)
    lo, hi = first * blocksize, min((first + count) * blocksize, nbytes)
    if len(rows) and (
        np.any(np.diff(rows) < 0)
        or rows[0] * row_bytes < lo
        or (rows[-1] + 1) * row_bytes > hi
    ):
        raise ValueError(f"rows outside blosc blocks {first}+{count}")


def decode_span_rows(head, first, count, span, row_bytes, rows, out):
    """Decode blocks `first`..`first + count` of a chunk from `span` (the
    compressed bytes from block `first`'s offset) and copy `rows` (uintp,
    ascending, inside those blocks) into `out` (uint8, `len(rows) *
    row_bytes`). Returns the core's status code, 0 on success."""
    check_rows_covered(head, first, count, row_bytes, rows)
    return core.extension().blosc_decode_span_rows(
        bytes(head), first, count, bytes(span), row_bytes, rows, out
    )


def read_chunk(path):
    """Decode a whole chunk to bytes."""
    return core.blosc_decode(Path(path).read_bytes())


def read_rows(path, row_bytes, rows):
    """Decode rows `rows` (ascending) of a row-major chunk.

    Returns (bytes of len(rows) * row_bytes, statistics).
    """
    rows = np.asarray(rows, dtype=np.int64)
    if rows.ndim != 1 or np.any(np.diff(rows) <= 0):
        raise ValueError("rows must be ascending and unique")
    out = np.empty(len(rows) * row_bytes, np.uint8)
    stats = {
        "bytes_read": 0,
        "blocks_decoded": 0,
        "blocks_total": 0,
        "decode_seconds": 0.0,
    }
    with open(path, "rb") as stream:
        head = stream.read(HEADER)
        nbytes, blocksize, nblocks, _ = header_fields(head)
        stats["blocks_total"] = nblocks
        if not head[2] & MEMCPYED:
            head = head + stream.read(4 * nblocks)
        starts, ends, _, _ = block_table(head)
        if not blocks_in_order(starts):
            # Blocks stored out of order: decode the whole chunk and select
            # the rows (`blocks_in_order`).
            stream.seek(0)
            whole = stream.read()
            stats["bytes_read"] = len(whole)
            stats["blocks_total"] = stats["blocks_decoded"] = nblocks
            decode_started = time.perf_counter()
            picked = whole_chunk_rows(whole, row_bytes, rows)
            stats["decode_seconds"] = time.perf_counter() - decode_started
            return picked.tobytes(), stats
        stats["bytes_read"] += len(head)
        if len(rows) and (rows[-1] + 1) * row_bytes > nbytes:
            raise ValueError("row beyond the chunk")
        first = rows * row_bytes // blocksize
        last = ((rows + 1) * row_bytes - 1) // blocksize
        needed = np.unique(
            np.concatenate([np.arange(a, b + 1) for a, b in zip(first, last)])
        )
        # Group consecutive blocks into one read each; rows never straddle runs
        # because every block of a requested row is requested.
        breaks = np.flatnonzero(np.diff(needed) != 1) + 1
        for run in np.split(needed, breaks):
            if not len(run):
                continue
            first_block, count = int(run[0]), len(run)
            stream.seek(int(starts[first_block]))
            span = stream.read(int(ends[run[-1]] - starts[first_block]))
            stats["bytes_read"] += len(span)
            inside = np.flatnonzero((first >= first_block) & (last <= run[-1]))
            run_rows = np.ascontiguousarray(rows[inside], dtype=np.uintp)
            run_out = np.empty(len(inside) * row_bytes, np.uint8)
            decode_started = time.perf_counter()
            status = decode_span_rows(
                head, first_block, count, span, row_bytes, run_rows, run_out
            )
            stats["decode_seconds"] += time.perf_counter() - decode_started
            if status:
                raise ValueError(f"blosc blocks {first_block}+{count} of {path} failed")
            stats["blocks_decoded"] += count
            out.reshape(len(rows), row_bytes)[inside] = run_out.reshape(-1, row_bytes)
    return out.tobytes(), stats
