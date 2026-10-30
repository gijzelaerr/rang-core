"""HTTP range-request fetch of a zarr row slice (research/core-g-http-fetch.md).

Fetches, from a zarr v2 store served over HTTP, only the blosc blocks that
hold the requested rows of each tile chunk: one ranged GET for the blosc
header and block-start table, then one ranged GET per contiguous run of
needed blocks, with the same block arithmetic as `core_zarr.read_rows`.
Whole small objects (`.zarray`, row-column chunks) are plain GETs. The
fetched bytes are written to disk, hashed and decoded by the core's Rust
decoder; they are data and are never executed. Standard library only.

Decoding writes straight into the caller's final `(row, channel, corr)`
arrays (big plan task P5, research/p5-memory.md): each run of blocks is
decoded by the core's strided row decoder at its channel offset, and local
tiles are memory-mapped, so no column is held twice and no compressed span
is copied. The P5 kernels (`core/src/ffi_correct.rs`) are called through
the extension; the standalone P5 build and its ctypes handle were removed by
task P7 (research/p7-architecture.md).
"""

import hashlib
import http.client
import json
import mmap
import platform
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from . import core, core_zarr

HEADER = 16
MEMCPYED = 0x02
PREFIX = 4112  # header plus a start table of up to 1024 blocks
ROW_COLUMNS = (
    ("ANTENNA1", "<i4"),
    ("ANTENNA2", "<i4"),
    ("TIME", "<f8"),
    ("FLAG_ROW", "|b1"),
)
TILE_COLUMNS = ("DATA", "MODEL_DATA", "FLAG", "WEIGHT_SPECTRUM")
RECORDED_HEADERS = (
    "ETag",
    "Last-Modified",
    "x-amz-request-id",
    "Date",
    "Content-Range",
)
_local = threading.local()


def block_table(prefix):
    """(starts, ends, prefix length, nblocks) from a chunk's first bytes."""
    nbytes, blocksize, nblocks, _ = core_zarr.header_fields(prefix[:HEADER])
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


def plan_runs(prefix, row_bytes, rows):
    """Runs of needed blocks as (first_block, count, start, end), like read_rows."""
    rows = np.asarray(rows, dtype=np.int64)
    if rows.ndim != 1 or np.any(np.diff(rows) <= 0):
        raise ValueError("rows must be ascending and unique")
    starts, ends, _, _ = block_table(prefix)
    nbytes, blocksize, _, _ = core_zarr.header_fields(prefix[:HEADER])
    if len(rows) and (rows[-1] + 1) * row_bytes > nbytes:
        raise ValueError("row beyond the chunk")
    first = rows * row_bytes // blocksize
    last = ((rows + 1) * row_bytes - 1) // blocksize
    if not len(rows):
        return []
    needed = np.unique(
        np.concatenate([np.arange(a, b + 1) for a, b in zip(first, last)])
    )
    breaks = np.flatnonzero(np.diff(needed) != 1) + 1
    return [
        (int(run[0]), len(run), int(starts[run[0]]), int(ends[run[-1]]))
        for run in np.split(needed, breaks)
        if len(run)
    ]


def _content_range(value):
    """(start, end exclusive, total) from `bytes a-b/t`, or None."""
    try:
        span, total = value.removeprefix("bytes ").split("/")
        first, last = (int(x) for x in span.split("-"))
        return first, last + 1, int(total)
    except (AttributeError, ValueError):
        return None


class Client:
    """One persistent HTTP(S) connection with ranged GETs and retries."""

    def __init__(self, base_url, timeout=120.0, retries=3, backoff=(1.0, 2.0, 4.0)):
        parts = urlsplit(base_url)
        self.scheme, self.netloc = parts.scheme, parts.netloc
        self.prefix = parts.path.rstrip("/")
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.connection = None

    def connect(self):
        if self.connection is not None:
            self.connection.close()
        if self.scheme == "https":
            self.connection = http.client.HTTPSConnection(
                self.netloc, timeout=self.timeout, context=ssl.create_default_context()
            )
        elif self.scheme == "http":
            self.connection = http.client.HTTPConnection(
                self.netloc, timeout=self.timeout
            )
        else:
            raise ValueError(f"unsupported URL scheme {self.scheme}")

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def get(self, key, byte_range=None):
        """GET `key`, optionally bytes [start, end). Returns a request record and the body.

        A ranged request must answer 206 with the requested Content-Range and
        length; a whole request must answer 200 with the full body. Anything
        else is retried; the record lists every attempt.
        """
        headers = {}
        if byte_range is not None:
            start, end = byte_range
            headers["Range"] = f"bytes={start}-{end - 1}"
        path = f"{self.prefix}/{key}"
        attempts = []
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            failure = None
            body = b""
            status = None
            seen = {}
            try:
                if self.connection is None:
                    self.connect()
                self.connection.request("GET", path, headers=headers)
                response = self.connection.getresponse()
                status = response.status
                body = response.read()
                seen = {
                    h: response.getheader(h)
                    for h in RECORDED_HEADERS
                    if response.getheader(h)
                }
                if byte_range is not None:
                    # A range past the object's end is clamped by the server
                    # (RFC 9110); the record then carries the served range.
                    served = _content_range(seen.get("Content-Range"))
                    if status != 206:
                        failure = f"status {status} to a ranged request"
                    elif (
                        served is None
                        or served[0] != start
                        or (served[1] != end and not (end > served[2] == served[1]))
                    ):
                        failure = f"Content-Range {seen.get('Content-Range')}"
                    elif len(body) != served[1] - start:
                        failure = f"{len(body)} bytes for a {end - start}-byte range"
                    else:
                        end = served[1]
                elif status != 200:
                    failure = f"status {status}"
                elif response.getheader("Content-Length") and len(body) != int(
                    response.getheader("Content-Length")
                ):
                    failure = "short body"
            except (OSError, http.client.HTTPException) as error:
                failure = f"{type(error).__name__}: {error}"
                self.close()
            elapsed = time.perf_counter() - started
            attempts.append(
                {
                    "attempt": attempt,
                    "status": status,
                    "bytes": len(body),
                    "seconds": elapsed,
                    "failure": failure,
                    "headers": seen,
                }
            )
            if failure is None:
                record = {
                    "key": key,
                    "range": None if byte_range is None else [start, end],
                    "status": status,
                    "bytes": len(body),
                    "seconds": elapsed,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "headers": seen,
                    "attempts": attempts,
                }
                return record, body
            if attempt < self.retries:
                time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
        raise OSError(f"GET {path} {headers.get('Range', '')} failed: {attempts}")


def kept_rows(row_arrays, stations):
    """Cross rows between `stations` with FLAG_ROW false, as the prototype keeps them."""
    a1, a2 = row_arrays["ANTENNA1"], row_arrays["ANTENNA2"]
    keep = (
        (a1 != a2)
        & np.isin(a1, stations)
        & np.isin(a2, stations)
        & ~row_arrays["FLAG_ROW"]
    )
    return np.flatnonzero(keep)


def fetch_slice(
    base_url,
    group,
    stations,
    tiles,
    out,
    workers=8,
    tile_columns=TILE_COLUMNS,
    row_columns=ROW_COLUMNS,
    row_chunk=0,
):
    """Fetch the four-station slice of `group` into `out`; returns the result dict.

    `base_url` is the store root (…/LBAND_LUNO_CALIBRATORS.zarr). Writes
    `objects/<key>` for whole objects, `spans/<key>/head` and
    `spans/<key>/<first_block>-<count>` for ranged spans, `receipt.json` and
    `result.json`.
    """
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists; use a fresh output directory")
    out.mkdir(parents=True)
    tiles = list(tiles)
    stations = list(stations)
    records = []
    lock = threading.Lock()

    def client():
        if not hasattr(_local, "client"):
            _local.client = Client(base_url)
        return _local.client

    def whole(key):
        record, body = client().get(key)
        dest = out / "objects" / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        with lock:
            records.append(record)
        return body

    def span(key, byte_range, name, keep=False):
        record, body = client().get(key, byte_range)
        dest = out / "spans" / key / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        with lock:
            records.append(record)
        # Run spans live on disk only, so the process does not hold the slice.
        return body if keep else None

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Small objects: metadata and the row columns, whole.
        metas = {
            name: json.loads(whole(f"{group}/{name}/.zarray"))
            for name, _ in row_columns
        }
        metas.update(
            {
                name: json.loads(whole(f"{group}/{name}/.zarray"))
                for name in tile_columns
            }
        )
        for name, meta in metas.items():
            if meta["compressor"]["id"] != "blosc" or meta.get("filters"):
                raise ValueError(f"{name}: only plain blosc arrays are supported")
        row_payloads = dict(
            zip(
                [name for name, _ in row_columns],
                pool.map(
                    lambda name: whole(f"{group}/{name}/{row_chunk}"),
                    [n for n, _ in row_columns],
                ),
            )
        )
        row_arrays = {
            name: np.frombuffer(core.blosc_decode(row_payloads[name]), dtype)
            for name, dtype in row_columns
        }
        rows = kept_rows(row_arrays, stations)
        # Tile heads: header plus start table, one ranged GET each.
        keys = [
            f"{group}/{name}/{row_chunk}.{tile}.0"
            for name in tile_columns
            for tile in tiles
        ]
        heads = dict(
            zip(keys, pool.map(lambda key: span(key, (0, PREFIX), "head", True), keys))
        )
        # Runs of needed blocks.
        jobs = []
        plans = {}
        for name in tile_columns:
            meta = metas[name]
            row_bytes = (
                meta["chunks"][1] * meta["chunks"][2] * np.dtype(meta["dtype"]).itemsize
            )
            for tile in tiles:
                key = f"{group}/{name}/{row_chunk}.{tile}.0"
                runs = plan_runs(heads[key], row_bytes, rows)
                plans[key] = {"row_bytes": row_bytes, "runs": runs}
                jobs.extend(
                    (key, (start, end), f"{first}-{count}")
                    for first, count, start, end in runs
                )
        list(pool.map(lambda job: span(*job), jobs))
    seconds = time.perf_counter() - started
    result = {
        "base_url": base_url,
        "group": group,
        "stations": stations,
        "tiles": tiles,
        "rows": rows.tolist(),
        "row_columns": [list(c) for c in row_columns],
        "tile_columns": list(tile_columns),
        "plans": plans,
        "requests": len(records),
        "attempts": sum(len(r["attempts"]) for r in records),
        "bytes": sum(r["bytes"] for r in records),
        "seconds": seconds,
        "workers": workers,
        "started_utc": started_utc,
        "python": platform.python_version(),
        "openssl": ssl.OPENSSL_VERSION,
    }
    (out / "receipt.json").write_text(json.dumps(records, indent=1) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    return result


# --- the P5 kernels (core/src/correct.rs, core/src/ffi_correct.rs) -----------


def p5_extension():
    """The extension module (it carries the P5 bindings)."""
    return core.extension()


def decode_rows_into(head, first, count, span, row_bytes, rows, out, offset, stride):
    """Decode blocks `first`..`first + count` of a chunk from `span` (uint8
    array or bytes from block `first`'s offset) and write row `rows[i]` at
    byte `offset + i * stride` of `out` (a C-contiguous array). Returns the
    core's status, 0 on success."""
    rows = np.ascontiguousarray(rows, dtype=np.uintp)
    if not out.flags.c_contiguous or not out.flags.writeable:
        raise ValueError("out must be a writable C-contiguous array")
    flat = out.reshape(-1).view(np.uint8)
    if offset < 0 or offset > flat.size:
        raise ValueError("offset outside out")
    span = np.frombuffer(span, np.uint8) if isinstance(span, bytes) else span
    return core.extension().blosc_decode_span_rows_strided(
        bytes(head), first, count, span, row_bytes, rows, flat, offset, stride
    )


def _runs(blocksize, row_bytes, rows):
    """(first block, count, rows slice) per run of needed blocks, as
    `core_zarr.read_rows` groups them; the rows of a run are contiguous."""
    first = rows * row_bytes // blocksize
    last = ((rows + 1) * row_bytes - 1) // blocksize
    needed = np.unique(
        np.concatenate([np.arange(a, b + 1) for a, b in zip(first, last)])
    )
    breaks = np.flatnonzero(np.diff(needed) != 1) + 1
    out = []
    for run in np.split(needed, breaks):
        if not len(run):
            continue
        inside = np.flatnonzero((first >= run[0]) & (last <= run[-1]))
        if len(inside) and inside[-1] - inside[0] + 1 != len(inside):
            raise ValueError("rows of a block run are not contiguous")
        out.append((int(run[0]), len(run), slice(int(inside[0]), int(inside[-1]) + 1)))
    return out


def read_rows_into(path, row_bytes, rows, out, offset):
    """`core_zarr.read_rows` straight into `out`: rows `rows` (ascending) of
    the row-major chunk at `path` land at byte `offset + i * stride` of `out`,
    where the stride is one row of `out`. The file is memory-mapped, so the
    compressed bytes are not copied. Returns the statistics of `read_rows`."""
    rows = np.asarray(rows, dtype=np.int64)
    if rows.ndim != 1 or np.any(np.diff(rows) <= 0):
        raise ValueError("rows must be ascending and unique")
    stride = out.strides[0] if out.ndim > 1 else row_bytes
    stats = {
        "bytes_read": 0,
        "blocks_decoded": 0,
        "blocks_total": 0,
        "decode_seconds": 0.0,
    }
    with open(path, "rb") as stream:
        mapped = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
    view = span = None
    try:
        view = np.frombuffer(mapped, np.uint8)
        head = bytes(view[:HEADER])
        nbytes, blocksize, nblocks, _ = core_zarr.header_fields(head)
        stats["blocks_total"] = nblocks
        if not head[2] & MEMCPYED:
            head = bytes(view[: HEADER + 4 * nblocks])
        starts, ends, _, _ = block_table(head)
        stats["bytes_read"] += len(head)
        if len(rows) and (rows[-1] + 1) * row_bytes > nbytes:
            raise ValueError("row beyond the chunk")
        for first, count, part in (
            _runs(blocksize, row_bytes, rows) if len(rows) else []
        ):
            span = view[int(starts[first]) : int(ends[first + count - 1])]
            stats["bytes_read"] += span.size
            started = time.perf_counter()
            status = decode_rows_into(
                head,
                first,
                count,
                span,
                row_bytes,
                rows[part],
                out,
                offset + part.start * stride,
                stride,
            )
            stats["decode_seconds"] += time.perf_counter() - started
            if status:
                raise ValueError(f"blosc blocks {first}+{count} of {path} failed")
            stats["blocks_decoded"] += count
    finally:
        del span, view
        mapped.close()
    return stats


def decode_slice(fetched):
    """Decode a fetched slice directory into arrays with the Rust decoder.

    Returns (arrays, statistics). Row columns are decoded whole; tile columns
    from their spans, each written straight into the final `(row, channel,
    corr)` array at its tile's channel offset (tile order).
    """
    fetched = Path(fetched)
    result = json.loads((fetched / "result.json").read_text())
    group = result["group"]
    rows = np.asarray(result["rows"], dtype=np.int64)
    stats = {"blocks_decoded": 0, "decode_seconds": 0.0, "bytes_decoded": 0}
    arrays = {}
    for name, dtype in result["row_columns"]:
        payload = (fetched / "objects" / group / name / "0").read_bytes()
        started = time.perf_counter()
        arrays[name] = np.ascontiguousarray(
            np.frombuffer(core.blosc_decode(payload), dtype)[rows]
        )
        stats["decode_seconds"] += time.perf_counter() - started
    for name in result["tile_columns"]:
        meta = json.loads((fetched / "objects" / group / name / ".zarray").read_text())
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        dtype = np.dtype(meta["dtype"])
        out = np.empty((len(rows), nchan * len(result["tiles"]), ncorr), dtype)
        for position, tile in enumerate(result["tiles"]):
            key = f"{group}/{name}/0.{tile}.0"
            plan = result["plans"][key]
            row_bytes = plan["row_bytes"]
            if row_bytes != nchan * ncorr * dtype.itemsize:
                raise ValueError(f"{key}: row size disagrees with the metadata")
            prefix = (fetched / "spans" / key / "head").read_bytes()
            _, _, used, _ = block_table(prefix)
            head = prefix[:used]
            _, blocksize, _, _ = core_zarr.header_fields(head)
            runs = {
                (first, count): part
                for first, count, part in _runs(blocksize, row_bytes, rows)
            }
            for first, count, start, end in plan["runs"]:
                body = (fetched / "spans" / key / f"{first}-{count}").read_bytes()
                part = runs[(first, count)]
                started = time.perf_counter()
                status = decode_rows_into(
                    head,
                    first,
                    count,
                    body,
                    row_bytes,
                    rows[part],
                    out,
                    part.start * out.strides[0] + position * row_bytes,
                    out.strides[0],
                )
                stats["decode_seconds"] += time.perf_counter() - started
                if status:
                    raise ValueError(
                        f"blosc blocks {first}+{count} of {key} failed to decode"
                    )
                stats["blocks_decoded"] += count
                stats["bytes_decoded"] += len(body)
        arrays[name] = out
    return arrays, stats


__all__ = [
    "Client",
    "block_table",
    "decode_slice",
    "fetch_slice",
    "kept_rows",
    "plan_runs",
]
