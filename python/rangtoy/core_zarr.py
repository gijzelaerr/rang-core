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


def array_meta(array_dir):
    """The `.zarray` metadata, refusing filters and object dtypes."""
    meta = json.loads((Path(array_dir) / ".zarray").read_text())
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError("object or filtered zarr arrays are not supported")
    if meta["compressor"]["id"] != "blosc":
        raise ValueError("only blosc-compressed zarr arrays are supported")
    return meta


def header_fields(head):
    ext = core.extension()
    status, fields = ext.blosc_header(bytes(head))
    if status:
        raise ValueError("unsupported or invalid blosc header")
    nbytes, blocksize, nblocks, typesize = (int(x) for x in fields)
    return nbytes, blocksize, nblocks, typesize


def decode_span_rows(head, first, count, span, row_bytes, rows, out):
    """Decode blocks `first`..`first + count` of a chunk from `span` (the
    compressed bytes from block `first`'s offset) and copy `rows` (uintp,
    ascending) into `out` (uint8, `len(rows) * row_bytes`). Returns the
    core's status code, 0 on success."""
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
        memcpyed = head[2] & MEMCPYED
        cbytes = int.from_bytes(head[12:16], "little")
        if memcpyed:
            starts = HEADER + np.arange(nblocks, dtype=np.int64) * blocksize
            ends = np.minimum(starts + blocksize, HEADER + nbytes)
        else:
            table = stream.read(4 * nblocks)
            head = head + table
            starts = np.frombuffer(table, "<u4").astype(np.int64)
            ends = np.append(starts[1:], cbytes)
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
