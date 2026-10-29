# Rang core, task G: HTTP range-request fetch of the LUNO four-station slice

Protocol frozen 2026-10-29 in `6c0d7c0`, before any fetch code was written.
Status: **implemented; measured: all five frozen criteria pass on the single
run** (`outputs/core-g-20261029-01`, checked in `core-g-check-20261029-01`):
2,124 requests, 751,848,436 bytes in 74.5 s against 4,869,187,244 bytes in
about 679 s for the same tiles fetched whole (6.5× fewer bytes, 9.1× faster;
16.4× against the 1,220 s of all three archived fetches), every fetched byte
hash-equal to the archived tiles and the decoded arrays identical. Wave 1
task G of
[core-parallel-plan.md](core-parallel-plan.md). The section 6 prototype
([core-section6.md](core-section6.md)) decodes only 2048 of the 12,544 blosc
blocks of the 64 LUNO tiles it reads, but those tiles were fetched whole from
the RATT bucket: 4,869,187,244 bytes. This task fetches only the blocks the
prototype needs, with HTTP range requests, and measures bytes and seconds
against the archived whole-tile fetch. A transport change; under AGENTS.md
not a scientific contribution, and no archived result may change because of
it.

## Precondition: the bucket serves Range requests (measured 2026-10-29)

Probe at 17:26 UTC against
`https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr/MAIN/MAIN_1/FLAG/0.8.0`
(the smallest tile of the slice, 851,970 bytes; archived SHA256
`33ee3790…3511c`), with curl, three requests in all:

- `HEAD`: `200 OK`, `Accept-Ranges: bytes`, `Content-Length: 851970`,
  `ETag: "a6f7b1a7969c5fed930aa9dbd1399bb2"`,
  `Last-Modified: Fri, 29 Nov 2024 14:12:49 GMT`,
  `x-amz-storage-class: INTELLIGENT_TIERING`, `Server: AmazonS3`.
- `GET` with `Range: bytes=0-15`: `206 Partial Content`,
  `Content-Range: bytes 0-15/851970`, `Content-Length: 16`, same ETag; the
  16 bytes are the blosc header (`02 01 21 01 …`, format 2, LZ4, shuffle,
  typesize 1). 0.21 s wall.
- `GET` with `Range: bytes=0-15,100-115` (two ranges): `200 OK` with the
  **whole object** (851,970 bytes). S3 ignores multi-range requests.

So: single byte ranges are served; multi-range is not. The fetcher issues one
request per contiguous run of needed blocks and never a multi-range request.

## Design, fixed before any code

- **Language: Python, standard library only** (`python/rangtoy/core_fetch.py`,
  `http.client` over the system OpenSSL, `ssl.create_default_context`,
  `concurrent.futures.ThreadPoolExecutor`). The work is latency- and
  bandwidth-bound, not compute-bound; the archived fetches ran at 6–10 MB/s
  with about 0.2 s per request from af-south-1. A Rust fetcher would need a
  TLS stack (rustls or native-tls plus an HTTP client), a dependency tree the
  core crate does not have and this task does not justify. The decoder stays
  the Rust one: fetched spans are passed to the existing
  `rang_core_blosc_decode_span_rows` symbol through `rangtoy.core_zarr`,
  whose block arithmetic (`read_rows`) the planner repeats byte for byte.
  No code is added to `core/`.
- **What is fetched**, for row chunk 0 of `MAIN/MAIN_1`, stations 0–3, tiles
  8–23, exactly as the prototype reads them (192 rows):
  1. `.zarray` of the eight arrays and the four whole row-column chunks
     `ANTENNA1/0`, `ANTENNA2/0`, `TIME/0`, `FLAG_ROW/0` (14,391 bytes in
     all), fetched whole as plain GETs. The kept rows are computed from them
     as `prototype_section6.ingest` does.
  2. For each of the 64 tile chunks (`DATA`, `MODEL_DATA`, `FLAG`,
     `WEIGHT_SPECTRUM` × tiles 8–23): one ranged GET of the 16-byte header
     plus the 4-byte-per-block start table (800 bytes for 196 blocks), then
     one ranged GET per contiguous run of needed blocks, with the run's byte
     span taken from the start table exactly as `core_zarr.read_rows` does.
     Planned from the archived tiles: 32 runs of one block per tile, 2048
     runs in all, 751,619,313 bytes of spans and tables. Nothing else is
     fetched; no whole tile.
- **Concurrency and politeness.** Eight worker threads, each with one
  persistent HTTPS connection, so at most eight requests are in flight.
  A response other than `206` for a ranged request (or `200` for a whole
  object), a short body or a connection error is retried up to three times
  with backoff of 1, 2 and 4 s; every attempt is recorded. The measured
  fetch runs once; a second run is allowed only if the first fails a
  criterion, and is labelled. Probe requests are the three above.
- **Outputs**, in a fresh `outputs/core-g-<yyyymmdd>-NN/`: the fetched bytes
  as files under `spans/<key>/<first_block>-<count>` (the header-and-table
  prefix as `spans/<key>/head`, whole objects as `objects/<key>`), a
  `receipt.json` with, per request, key, byte range, status, bytes received,
  wall seconds, SHA256 of the body and the response's `ETag`,
  `Last-Modified`, `x-amz-request-id` and `Date`, plus the URL, UTC start
  time, worker count, Python and OpenSSL versions; and a `result.json` with
  the totals. Downloaded bytes are data: hashed and decoded, never executed.
- **Checker** `examples/check_core_fetch.py`, run after the fetch, writes
  `outputs/core-g-check-<yyyymmdd>-NN/result.json` with every criterion below
  and the values it measured. It reads the archived tiles once, streaming.

## Acceptance criteria (frozen)

1. **Range support** as recorded above: every ranged response is `206` with a
   `Content-Range` whose first-last/total equals the requested span and the
   archived tile's size, and every whole-object response is `200` with
   `Content-Length` equal to the archived object's size.
2. **Byte equality.** The SHA256 of every fetched span equals the SHA256 of
   the same byte range of the archived tile (`outputs/luno-solve-20261029-02/inputs`
   for DATA, `outputs/luno-support-20261029-01/slice` for the rest), and the
   SHA256 of every fetched whole object equals the archived receipt line and,
   for the four row-column chunks, `input_chunk_sha256` in
   `outputs/core-section6-20261029-02/receipt.json`. Exact, no exceptions.
3. **Array equality.** The 192 × 2048 × 4 arrays decoded from the fetched
   spans by the Rust decoder (DATA, MODEL_DATA, FLAG, WEIGHT_SPECTRUM) and the
   four row arrays equal, exactly, the arrays `core_zarr.read_rows` decodes
   from the archived tiles with the same rows.
4. **Bytes transferred.** Response bodies total at most 760,000,000 bytes
   (the planned 751,619,313 plus the small objects; 15.4 % of the
   4,869,187,244-byte whole tiles), and the request count is at most 2,200
   (2048 runs + 64 heads + 8 `.zarray` + 4 chunks + retries). The response
   headers are reported, not counted.
5. **Wall time.** The whole fetch, from the first request to the last byte,
   takes less than 679 s: the archived whole-tile time for the same 64 tiles,
   461 s for the DATA tiles (`fetch-luno-solve.sh --data`, 2,717,394,612 B)
   plus the MAIN_1 share of the 325.7 s support fetch pro rata by bytes
   (2,151,792,632 of 3,222,232,014 B, 217.5 s). The 1,220 s figure in the
   plan is the sum of all three archived fetches including the 432 s of
   2,608 subtable objects, which this slice does not need; both are reported.
   Reported, not gated: the achieved MB/s, requests per second and the
   decode time of the fetched spans.
6. **Outputs** as listed; `tools/check-all.sh` passes; the fetcher has unit
   tests that run without network against a local HTTP server serving a
   synthetic blosc chunk, covering range parsing, run planning against
   `core_zarr.read_rows`, retry on a `200` to a ranged request, and the
   receipt.

A failure of 2 or 3 stops the timing claim: it is recorded as frozen and any
fix is a labelled post-hoc step with a second, labelled run.

## Implementation (`c20a988`)

- `python/rangtoy/core_fetch.py`: `plan_runs` (the block arithmetic of
  `core_zarr.read_rows`), `Client` (one persistent `http.client` connection
  per worker thread, ranged GETs validated against `Content-Range`, retries
  with 1, 2, 4 s backoff, every attempt recorded), `fetch_slice` (the slice
  into `objects/`, `spans/`, `receipt.json`, `result.json`) and
  `decode_slice` (the Rust decoder through `core_zarr`'s registered symbol).
  One detail the protocol left open: the head request asks for bytes
  0–4111 (a header plus a table of up to 1024 blocks), and the 816 bytes a
  196-block tile needs are cut from that; the extra 3,296 bytes per tile are
  counted. A range past a small object's end is served clamped (RFC 9110),
  and the record carries the served range.
- `examples/fetch_luno_slice.py` runs the measured fetch;
  `examples/check_core_fetch.py` checks criteria 1–5 against the archive;
  `tests/test_core_fetch.py` runs offline against a local range-capable HTTP
  server (plan versus `read_rows`, byte and array equality, clamped head,
  retry on a `200` to a ranged request).

## Measured result (2026-10-29, run `-01`)

Fetch started 17:34:45 UTC with eight workers from the WSL2 workstation
(Python 3.14.4, OpenSSL 3.5.5), `outputs/core-g-20261029-01`; receipt with
every request's key, range, status, bytes, seconds, SHA256 and the `ETag`,
`Last-Modified`, `x-amz-request-id`, `Date` and `Content-Range` headers.
Checked in `outputs/core-g-check-20261029-01/result.json`:
**all five criteria pass as frozen.**

| Criterion | Measured | Limit |
| --- | --- | --- |
| 1 range support | 2,112 ranged responses `206` with the requested `Content-Range` over the archived size; 12 whole objects `200` with the archived size; no retries (2,124 attempts for 2,124 requests) | exact |
| 2 byte equality | every one of the 2,124 bodies hash-equal to the same bytes of the archived tile or object; the four row chunks equal the section 6 receipt; the files on disk hash to the receipt | exact |
| 3 array equality | DATA, MODEL_DATA, FLAG, WEIGHT_SPECTRUM (192 × 2048 × 4) and the four row arrays identical to `read_rows` on the archived tiles; 2048 blocks decoded | exact |
| 4 bytes | 751,848,436 bytes, 2,124 requests (15.44 % of the 4,869,187,244-byte tiles) | ≤ 760,000,000; ≤ 2,200 |
| 5 wall | 74.5 s, first request to last byte | < 678.5 s |

Reported, not gated: 10.09 MB/s and 28.5 requests/s over eight connections
(median 0.20 s per 367 KB run span, worst 1.28 s; 0.12 s per head);
decoding the fetched spans with the Rust decoder took 0.74 s for 2048 blocks
(the section 6 prototype's ingest from local whole tiles took 1.29 s of
decode plus file reads); the whole process took 75.3 s. Peak RSS was
817 MB because the run as committed kept every span body in memory after
writing it; **post-hoc code change**, not re-measured: run spans are now
written and dropped (`span(..., keep=False)`), which changes no fetched byte
and no criterion. The archived tiles' ETags carry a part count
(`…-21`, `…-13`), so they are multipart uploads and the ETag is not an MD5 of
the object; the receipt records them as provenance only.

**Against the whole-tile fetch.** The same 64 tiles took about 679 s to
fetch whole (461 s for the DATA tiles at 5.9 MB/s; the MAIN_1 share of the
325.7 s support fetch at 9.9 MB/s), 4,869,187,244 bytes, of which the
prototype decodes 2048 of 12,544 blocks. The range fetch moves 15.4 % of the
bytes in 11 % of the time; per byte it runs at the support fetch's rate, so
the saving is the bytes, not the link. The three archived fetches together
took 1,219 s (the 1,220 s of the plan), 432 s of which were 2,608 subtable
objects this slice does not need; a four-station solve from the bucket now
costs 75 s of transfer plus the prototype's 1.67 s.

**What this does not show.** One run on one afternoon from one host: the
rate is a measurement, not a characterisation of the bucket. The row
columns are still fetched whole (14 KB; irrelevant here, but a full-rate
LUNO row chunk is larger). Nothing changes for whole-tile consumers;
dask-ms and zarr readers still fetch whole chunks, which is the upstream
observation in [upstream-notes.md](upstream-notes.md) and remains unfiled.

## Tool timings (this task)

| Date | Tool / stage | Input | Wall | Notes |
| --- | --- | --- | ---: | --- |
| 2026-10-29 | curl probe: HEAD, 16-byte ranged GET, two-range GET | `FLAG/0.8.0` | 0.32 s, 0.21 s, (not timed) | see precondition |
| 2026-10-29 | `python3 -m venv` | worktree | 0.04 s, failed | no `ensurepip` on this Ubuntu; recreated with `uv venv` |
| 2026-10-29 | `uv venv` + `uv pip install -e .[pointing,beam,test] ruff` | public PyPI | 23.3 s | |
| 2026-10-29 | `cargo +1.93 build --release` (core, 4 jobs) | `core/` | 2.4 s | warm cache |
| 2026-10-29 | run planning from archived tiles (Python, no network) | 64 tiles | about 3 s | 2048 runs, 751,619,313 B |
| 2026-10-29 | pytest, `test_core_fetch.py` + `test_core_zarr.py` | local HTTP server | 1.1–8.4 s | the 8.4 s run included retry backoff on a wrong test store |
| 2026-10-29 | `fetch_luno_slice.py`, 8 workers, run `-01` | 2,124 requests, 751,848,436 B | 74.5 s fetch; 75.3 s process (user 4.3 s, sys 2.9 s) | 817 MB peak RSS (see above) |
| 2026-10-29 | `check_core_fetch.py` | run `-01` against 4.87 GB of archived tiles | 3.0 s | streams only the needed spans |
| 2026-10-29 | `bash tools/check-all.sh` (4 cargo jobs) | repo, 671 tests | 1531 s (pytest 1517 s) | PASS; host load average 58–72 on 16 cores from the eight wave 1 sessions |

## For the coordinator

- `research/tool-timings.md`: the rows above, in particular the fetch row
  and the check row.
- `research/STATE.md`: one paragraph, "Core task G, 2026-10-29 (implemented;
  measured): the LUNO four-station slice fetched with HTTP range requests,
  751.8 MB in 74.5 s against 4.87 GB in about 679 s whole-tile, all bytes
  hash-equal to the archive (`core-g-http-fetch.md`)."
- `research/README.md`: index entry for this file.
- `research/upstream-notes.md`: the range-fetch item (dask-ms / zarr readers
  fetch whole chunks) is now measured: 15.4 % of the bytes, 11 % of the
  time, for the section 6 slice. S3 serves single ranges only; a reader
  wanting fewer requests needs coalescing, not multi-range.
- No shared source file was edited; `core/` is unchanged.
