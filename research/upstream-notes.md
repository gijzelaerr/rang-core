# Upstream tool notes

Started 2026-10-29 at the user's request. This is a side project: find bugs,
performance problems and possible improvements in the radio-astronomy tools
rang depends on, and contribute fixes back. Nothing is filed or sent upstream
without the user's explicit go-ahead for that item. Timings live in
[tool-timings.md](tool-timings.md).

Status key: **observed** (seen in a rang run), **verified** (reproduced in
isolation), **filed** (issue or PR exists, with link).

## QuartiCal 0.2.7 (Numba 0.67.0)

- **Observed: JIT dominates small solves.** A 192-row, 4-station, 2048-channel
  solve with DATA = MODEL took 27 s. Of that, 23.9 s was "execute graph",
  although the solve converged immediately.
  - QuartiCal sets `cache: True` in `quartical/utils/numba.py`, so the cost is
    first-call compilation.
  - In rang this is our own problem: `tools/flagging/Dockerfile` sets
    `NUMBA_CACHE_DIR=/tmp/numba`, and every container is fresh, so the cache
    never persists.
  - Rang-side fix: mount a persistent cache volume.
  - Upstream question: how much of the 24 s survives a warm cache, given that
    `generated_jit`/overload-heavy kernels may still re-specialise per call?
    To be measured.
- **Observed: no provenance trail.** QuartiCal writes no HISTORY row, so the
  LUNO stores carry `CORRECTED_DATA_QCAL` with no record of how it was made
  (see [the candidate report](flagging-luno-candidate.md)). Possible
  contribution: optionally append a HISTORY row with the command and version
  when writing output columns.

## dask-ms 0.2.32 (Zarr export)

- **Observed: tiny-object fan-out.** The exported LUNO FEED subtable is split
  into one zarr group per antenna (56 groups), each with about 10 columns
  of single-row chunks. Fetching the needed subtables meant 2,608 objects for
  2.3 MB, which took 432 s with sequential `curl`. Worth checking whether
  dask-ms partitions subtables by default on export, and whether consolidated
  metadata (`.zmetadata`) is written; neither LUNO store root lists one.
- **Observed: object-column encoding differs between exports.** ESO137 string
  columns use the `pickle` filter, which is unsafe to decode from untrusted
  stores. LUNO uses `json2`. Check which dask-ms version switched, and whether
  readers can refuse pickle by default.

## Rang's own tooling (not upstream)

- The S3 listings in `tools/flagging/fetch-luno-support.sh` and
  `fetch-luno-solve.sh` originally ignored the 1000-key pagination limit. Fixed
  in `fetch-luno-solve.sh`; the support fetch lists no prefixes, so it is not
  affected.
- Containers wrote outputs as root until runs used `--user $(id -u):$(id -g)`.
- pytest wall time varied from 986 s to 175 s for the same 654 tests on this
  host, probably because of concurrent load. Check before treating it as a
  regression.

## Findings from the stack-consolidation study (2026-10-29)

See [stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
for the measurements. None of these has been sent anywhere.

- **Verified: a warm Numba cache removes almost all of QuartiCal's cost on
  small solves.** The same LUNO four-station solve takes 28.3 s with a cold
  cache (25.2 s "execute graph") and 3.6 s with a bind-mounted cache (1.0 s
  graph). The cache is 3.9 MB. Rang-side: `run-next.sh` already mounts a
  cache; the LUNO solve and the older wrappers do not. Upstream-relevant:
  the warm subprocess still spends 2.4 s importing `quartical.executor` and
  about 2.5 s outside the graph; a note on a persistent default cache
  location and import-time cost may be worth raising, pending the user's
  go-ahead.
- **Observed: cached and freshly compiled kernels give different bits.**
  Gains from the cold-cache run (hash `57809b86…`, matching the archive) and
  from the warm-cache run (`769a69b1…`) differ by at most 1.1e-16 absolute
  and 2.0e-14 relative, with identical gain flags and rank survey. This is
  rounding-level and expected from different compiled arithmetic order, but
  it means receipts that hash QuartiCal gains byte-for-byte depend on the
  cache state. Rang should compare gains with a tolerance, not a hash.
- **Observed: the public zarr chunking defeats station subsets.** The LUNO
  DATA array is chunked 50,000 rows × 128 channels × 4; keeping 192 rows for
  four stations decodes 3.28 GB to retain 12.6 MB (260×), after fetching
  2.72 GB. A row-chunk aligned with integrations, or a per-baseline layout,
  would let subsets be fetched by range. This is a question for the data
  publishers (RATT public bucket), not for dask-ms itself, although dask-ms's
  default export chunking chose it.
- **Observed: Tricolour 0.2.1 takes about 302 s per strategy on a 140-row ×
  4096-channel MS** (archived `gain-tv-caracal.json`, four controls at
  301.7–302.9 s). The data are 18 MB, so this is almost certainly JIT plus
  dask overhead rather than flagging work. Not yet profiled in isolation.
- **Verified: QuartiCal compiles its kernels with `fastmath`.**
  `quartical/utils/numba.py` sets `"fastmath": True` in `JIT_OPTIONS`, which
  lets LLVM reassociate and fuse multiply-adds. This probably explains the
  1e-16 difference between cold-cache and warm-cache gains. A faithful Rust
  port of the `complex` term (`core/src/solve.rs`) agrees with QuartiCal to
  1.4e-15 without `fastmath`, so the option costs reproducibility for little
  visible gain at these sizes. Possible note upstream: document it, or offer a
  strict mode for reproducible receipts. Not raised.
- **Observed: the full `complex` term ignores `solver.reference_antenna`.**
  Only the diagonal and delay-like kernels read it, so the
  `solver.reference_antenna=0` in rang's command has no effect on its solves;
  rang fixes the gauge afterwards with its own polar decomposition. Worth a
  sentence in the QuartiCal option docs. Not raised.
- **Observed: the conjugate-baseline normal equations reuse the pq weight
  order.** In `compute_jhj_jhr` the qp contribution uses the same
  XX, XY, YX, YY weights as pq, although the transposed residual pairs XY with
  YX. It matters only when the XY and YX weights differ, and it changes the
  step, not the fixed point. To be checked against QuartiCal's intent before
  any report. Not raised.
