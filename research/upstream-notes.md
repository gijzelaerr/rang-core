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
- **Measured: blosc block tables allow partial reads of the public stores.**
  The LUNO DATA chunks hold 196 independently compressed 1 MB blosc blocks,
  and the chunk header lists where each starts. Reading only the blocks that
  hold four stations' rows read 461 MB instead of 2,717 MB and decoded 512 of
  3136 blocks (`core-section6.md`). The same offsets would let a client fetch
  those byte ranges with HTTP range requests from the RATT bucket. Useful for
  dask-ms or zarr readers that today fetch whole chunks; not raised. Measured
  2026-10-29 (`core-g-http-fetch.md`): the range-request fetch of the section
  6 slice moved 15.4 % of the bytes in 11 % of the time. The bucket serves
  single ranges only, so a reader wanting fewer requests needs coalescing,
  not multi-range requests.

## Wave 1 observations (2026-10-29; observed, not raised)

- **Tricolour 0.2.1 licence metadata** (`core-d-tricolour.md`): the wheel
  declares `License: GPLv2` but ships only a BSD-3-Clause `LICENSE`; the
  string dates from the Poetry migration in PR #94. Crystalball 0.4.3 carries
  the same metadata string with a real GPL-2 text. Worth a question to the
  maintainers; rang treats Tricolour as BSD-3-Clause pending that answer.
- **Tricolour compilation cost**: of the 302 s per archived native run, 300 s
  is `ProgressBar(dt=300)` (noted above) and about 114 s of CPU is Numba
  compilation: 75 s for `sum_threshold_flagger` and 39 s again for the
  strategy step whose YAML gives `spike_width_time: 2` as an integer, which
  makes Numba compile a second specialisation; the kernels themselves take
  about 1.2 s warm. A persistent `NUMBA_CACHE_DIR` or floats in the shipped
  YAML would remove most of it. `nanmean` of an all-flagged channel logs
  "Mean of empty slice" on every call.
- **WSClean 3.6-1 `CalculateMsLimits`** (`core-c-gridder.md`):
  `gridding/msprovidercollection.cpp` computes the y bound from `u` instead
  of `v`; the limits are unaffected for rang's jobs (measured).
- **WSClean `-store-imaging-weights`** (`core-b-weighting.md`): the column is
  written during both the PSF and the dirty passes with the same values, and
  the flag must precede the MS argument on the command line (documented).
- **Survey eigensolver** (`core-f-performance.md`): the rank survey's cost is
  the root crate's classical Jacobi eigensolver in `src/response.rs`; LAPACK
  does the 864 32×32 decompositions in 0.056 s against 0.51 s, so the survey
  would drop from 0.73 s to about 0.3 s under its own equality protocol.
  NumPy's OpenBLAS pool keeps eight spinning threads during the core's
  single-threaded work (17–18 % of perf samples); `OPENBLAS_NUM_THREADS=1` in
  the drivers would free them. Both are rang-side items, not upstream.

## Task K observations (2026-10-30; observed, not raised)

- QuartiCal `complex` term on the four-station LUNO solve: the 50-iteration
  cap is reached with 98.3 % of intervals converged, in QuartiCal and in the
  port alike, on real data as on the fixture. A convergence-criterion note
  for sparse arrays may be worth raising once more data are solved.
- CARACAL first-pass strategy on a 2048-channel sub-band that is already
  70 % flagged: `uvcontsub_flagger` drops the running flags to 39 % (as
  designed, `or_original_from_cycle: 1`), the static masks and SumThreshold
  rebuild them to 66 %, and `combine_with_input_flags` restores the input;
  166 new cells in all. Nothing wrong, but worth knowing when reading its
  logs on pre-flagged calibrator data.

## Upstream status after task U1 (2026-10-30; details in `upstream-issues/`)

Every RATT observation above was checked against its latest release
(QuartiCal 0.2.7 and v0.2.8-dev, Tricolour 0.2.1 and 0.5.0-dev, dask-ms 0.2.32).

- QuartiCal conjugate-baseline weights: **filed**
  <https://github.com/ratt-ru/QuartiCal/issues/452> (the qp half of JHJ in the
  `complex` term uses the pq weight order, swapping XY and YX weights; JHr and
  the fixed point are unaffected, the update step is not; verified against
  QuartiCal's own element kernel on 0.2.7, same pattern on v0.2.8-dev).
- QuartiCal HISTORY row: **filed** <https://github.com/ratt-ru/QuartiCal/issues/453>.
- QuartiCal JIT and cache: not filed. Upstream already caches; the cold cost was
  rang's `/tmp` `NUMBA_CACHE_DIR`. 0.2.7 measured cold 29.3 s, warm 4.0 s. See #278.
- QuartiCal `fastmath` bit differences: not filed; rounding-level, cause not isolated.
- QuartiCal `complex` and `reference_antenna`: not filed. Documented as
  diagonal-only in 0.2.7; PR #440 on v0.2.8-dev references `complex` by default.
- QuartiCal 50-iteration cap: not filed; not a defect, the port gives the same fraction.
- Tricolour licence metadata: not filed; 0.5.0-dev declares BSD-3-Clause (c36d982).
  This settles the task D question in the direction rang assumed.
- Tricolour compile cost: 300 s of the archived 302 s per run is the non-TTY
  `ProgressBar(dt=300)`, **filed** <https://github.com/ratt-ru/tricolour/issues/110>;
  the second compilation from the integer `spike_width_time` is **filed**
  <https://github.com/ratt-ru/tricolour/issues/111>. Caching is already on upstream.
- dask-ms FEED fan-out: not filed; deliberate per-row grouping (#191).
- dask-ms object encoding: not filed; JSON since #310 (2024-03).
- CARACal first-pass strategy intermediate state: not filed; by design, and the
  repository is under `caracal-pipeline`. Stimela 2.1.4 on Python 3.14: not
  filed; the release declares `<3.14`, repository under `caracal-pipeline`.
- Non-RATT items: [non-ratt-observations.md](non-ratt-observations.md), not
  reported by decision.

## S1 observations (2026-10-30; observed, not raised)

- **QuartiCal `complex` convergence, measured curve** (`simplification-review.md`
  section 2.7, on the port that equals QuartiCal to 3.3e-16 at 50 iterations):
  on the LUNO 1934−638 four-station slice 7.3 % of intervals pass the 1e-7
  criterion at 8 iterations, 49 % at 15, 98.33 % at 45; the default stop
  fraction 0.99 is reached only at 91; held-out MSE is within 2e-5 relative by
  12 iterations while gain products still move 1.3e-3 between 50 and 91. A
  loss-based or gauge-invariant criterion would stop an estimated 3–5× earlier.
  To be reproduced on QuartiCal's latest release before filing (U1 closed the
  plain iteration-cap note as not a defect; this is the improvement case).

## L1 observations (2026-10-30; observed, not raised)

- **QuartiCal `complex` at array scale** (ported, same settings as the
  archived four-station solve): 50 iterations converge 83 % of intervals on
  the 53-station LUNO chunk against 98 % on four stations. Together with S1's
  convergence curve this is the improvement case for the iteration cap and
  criterion; to be reproduced on the latest release before filing.
- **CARACal first-pass strategy on pre-flagged calibrator data**
  (`caracal-pipeline`): it flags 762,924 new cells of chunk 0 and some
  station × 32-channel bins lose every unflagged sample, so a solver loses
  those gains. Worth a documentation note once reproduced with CARACal itself.
