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
