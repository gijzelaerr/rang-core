# Big plan task P2: the gridder's FFT and parallel w-layers

Protocol frozen 2026-10-30 on branch `p2-gridder` (from `43dc3c7`), before
any change to `core/src/grid.rs` (`473d63b`). Status: **implemented and
measured; every gated criterion passes as frozen.** One four-station image
goes from 5.8 s to 0.80 s on one thread (7×) and 0.53–0.61 s at 4–16
threads on a host at load 15–33; images differ from the old FFT's by at most
2.1e-15 of the peak, every comparator margin is unchanged (response fraction
1.31e-7 of 1.6e-7), and results are identical at 1, 2, 4, 8 and 16 threads. Task P2 of
[big-plan.md](big-plan.md), cut in
[simplification-review.md](simplification-review.md) section 3 ("P2
Gridder") and section 4. An optimisation of an existing port, not a
scientific contribution: the result must be the same images within task A's
frozen tolerances, faster.

## What changes (fixed before code)

In `core/src/grid.rs` only; the C ABI (`ffi_grid.rs`), the extension
(`core/py/src/lib.rs`) and the Python wrapper (`core_grid.py`) keep their
signatures. The thread count is rayon's (`RAYON_NUM_THREADS`, default all
hardware threads).

1. **Samples bucketed once.** Today `Gridder::invert` scans every sample for
   every one of the 64 layers (`w_to_layer` 64 × N times) and does so twice,
   once for the dirty image and once for the PSF, each time from a
   materialised 40-byte tuple. After: one pass over (row, channel) computes
   the counters exactly as today (same order, same `f32` products), places
   each sample once (`AddDataSample`'s conjugation, cell rounding, wrap and
   sub-cell kernel choice) and keeps it as 24 bytes (cell, kernels, the
   `f32` weighted sample and the `f32` weight, which are the reader's `f32`
   products, so storing them rounds nothing), then a stable counting sort
   by layer keeps the row-channel order within each layer. Samples whose
   weighted value and weight are both zero (flagged cells; about 70 % of
   task K's) add only signed zeros and are not kept.
2. **Dirty image and PSF in one loop.** Each sample is added to both grids
   with the same kernel product; both grids are transformed; the projection
   computes the w-phasor `sin_cos` once per pixel for both; the kernel
   correction (the DCT prefix) is computed once.
3. **Layers in parallel, ordered sum.** Each layer is gridded, transformed
   and projected into its own term image by one rayon task; the term images
   are added to the result in layer order in batches of 16 layers (fixed,
   so memory is bounded and does not depend on the thread count). Each
   projected term is the value today's code adds to the image, and the
   additions happen in today's order, so this step alone must reproduce
   today's images bit for bit, at any thread count.
4. **FFT.** The hand-written radix-2/Bluestein transform is replaced by
   `rustfft` 6.4.1 (MIT/Apache-2.0, public crates.io, already fetched by
   P0), unnormalised inverse (`exp(+2πi jk/n)`, FFTW's `FFTW_BACKWARD`),
   planned once per inversion, rows then columns through a blocked
   transpose. **The grid keeps WSClean's exact size**: WSClean plans FFTW at
   the padded size itself (`main/settings.cpp` lines 468–474,
   `paddedImageWidth = ceil(width × padding)` rounded up to a multiple of
   four; `gridding/wstackinggridder.cpp` lines 168–171 and 209–212,
   `fftw_plan_dft_2d(_height, _width, …, FFTW_BACKWARD, …)`), so 616 × 616
   (2³ · 7 · 11) is transformed directly by a mixed-radix plan; no padding
   to a smoother size.
5. Kernel, oversampling, w-layer mapping, normalisation, PSF scaling, trim
   and FITS orientation are not touched. Grids stay `f64` (the review's
   f32 option is not taken: the response-fraction margin is too small).

Staging, so that differences are attributable: **stage (a)** is items 1–3
with today's FFT and must be bit-identical to today's images (K archive
SHA256s and the baseline images, at 1 and 16 threads); **stage (b)** swaps
the FFT (item 4). Every pixel difference after stage (b) is the FFT's.
Bit-identity of stage (b) with the old Bluestein FFT is **not expected**;
the actual differences are reported.

Not in scope: f32 grids, a GPU path (optional spike behind a cargo feature
only if time allows; the host has no CUDA toolkit or Vulkan in WSL per S1),
parallel gridding within one layer, streaming samples from the rows.

## Inputs and comparators

- **Task C**: the fifteen archived imaging jobs (archive
  `outputs/tv-next-imaging-wsl-20261029-01`, oracle
  `outputs/core-c-20261029-01` with WSClean's FITS), driver
  `examples/run_core_gridder.py`, comparator
  `examples/compare_core_gridder.py` against the archived WSClean FITS.
- **Task I**: `examples/run_core_imaging.py` (reads the backup MSs, writes
  `result.json` and FITS, runs `compare_core_imaging.py` against
  `research/results/gain-tv-next-imaging.json` with the archived FITS
  pixels and against the host reproduction).
- **Task K**: `examples/bench_p2_gridder.py k-replay` (written for this
  task): decodes the archived fetched bytes of `outputs/core-k-20261030-01`,
  builds the state with `core_campaign.build_state`, takes each arm's
  archived gains (`gains/<arm>.npz`) and flag additions
  (`flags/<arm>.npz`) and images the six arms through the unedited
  `core_campaign.image_arm`; it compares with
  `research/results/core-k-luno-campaign.json` and the archived FITS. No
  solve and no Tricolour run is repeated.
- **Timing inputs**: the gridder inputs of the fifteen C jobs
  (`bench_p2_gridder.py c-inputs`, 9,169 or 7,812 gridded visibilities each
  of 2,048 × 1,190 cells) and of the six K arms (dumped by `k-replay
  --dump-inputs`, 117,428–117,556 gridded of 393,216 cells), in
  `outputs/p2-gridder-20261030-01/inputs-{c,k}`. `bench_p2_gridder.py
  bench` times `core_grid.invert` alone in a fresh process per (repeat,
  thread count, library) through `RANG_CORE_LIB` (ctypes) with
  `RAYON_NUM_THREADS` and `OPENBLAS_NUM_THREADS=1`, and records per-image
  wall and process CPU, peak RSS, the one-minute load before and after,
  and the SHA256 of every dirty image and PSF. The old library is the
  baseline build saved before any edit (`baseline/librang_core.so`,
  SHA256 `98f75224…`; `_core.abi3.so` `064f61eb…`).

## Comparator precondition (measured before the freeze, baseline build)

| Check | Result |
| --- | --- |
| K replay, six arms, baseline build (`k-replay-baseline`) | dirty and PSF SHA256 equal to the archive for all six arms; metrics and counters identical (0.0); pixels against the float32 FITS 3.2e-8 of peak (dirty), 3.0e-8 (PSF), i.e. FITS rounding; 27.1 s wall, 333 MB |
| C driver + comparator against the WSClean FITS (`c-baseline`) | criteria 1–3 pass on all fifteen jobs; dirty L∞ 6.11e-7 of peak, PSF L∞ 4.17e-7, WCS equal (task C's run `-05` figures exactly); 118.6 s wall, 138 MB |
| I driver + comparators (`i-baseline`) | both comparisons pass; response fraction 1.312e-7 (82 % of 1.6e-7), template flux 1.43e-7, PSF-vs-fixedG0 8.9e-8, weight sums 5.8e-16, dirty pixels 6.11e-7 of peak, PSF 4.17e-7; 96.9 s wall, 212 MB |

## Acceptance criteria (frozen)

Gated:

1. **Task C** (`compare_core_gridder.py`, core versus the archived WSClean
   FITS, all fifteen jobs): dirty L∞ / archived peak ≤ 8.8e-6, PSF L∞ ≤
   2.8e-6, WCS keys equal; and the driver's own criteria 1–3 (image weight
   to 1e-6 relative and counts equal, w limits to 1e-4, PSF centre exactly
   1.0).
2. **Task I** (`run_core_imaging.py`, both comparisons): passes under the
   frozen classes of `core_imaging.classify_replay` (task A's tolerances:
   dirty L∞ 8.8e-6 of peak, PSF L∞ 2.8e-6, template flux 4.7e-6 relative,
   response fraction 1.6e-7 absolute, weight sums 1e-9 relative, exact
   fields exact), except the side-effect audit's git clause, which failed
   as frozen in task I and is reported, not gated. The response-fraction
   margin is reported explicitly (today 1.31e-7 of 1.6e-7).
3. **Task K** (`k-replay`, six arms): pixels against the archived FITS
   dirty L∞ / peak ≤ 8.8e-6 and PSF L∞ ≤ 2.8e-6; gridder counters
   (`image_weight`, `visibility_weight_sum`, `max_gridded_weight`) to 1e-9
   relative and `gridded_count`, `n_w_layers`, `min_w`, `max_w` exactly
   (that code path is unchanged); image metrics derived from the dirty
   image (peak, off-source RMS, residual RMS, off-source residual RMS,
   residual maximum, flux recovery) to 8.8e-6 relative and from the PSF
   (centre, sidelobes) to 2.8e-6 absolute; peak pixel and imaged cells
   equal; the residual-RMS calls of the three archived hypotheses
   unchanged. The archived `dirty_sha256`/`psf_sha256` will change after
   stage (b); they are reported.
4. **Stage (a) bit-identity**: before the FFT swap, the K replay's dirty
   and PSF SHA256 equal the archive for all six arms, and the C and K
   timing images equal the baseline images bit for bit, at 1 and 16
   threads. A difference is a bug in the restructuring, not a tolerance
   question.
5. **Thread-count identity** (final build): every dirty image and PSF of
   the C and K timing sets has the same SHA256 at 1, 2, 4, 8 and 16
   threads and across repeats; plus a Rust unit test at 1, 2, 3 and 8
   threads in one process and a pytest at `RAYON_NUM_THREADS` 1 and 4.
6. **FFT correctness**: a unit test checks the 2-D transform against a
   direct DFT (sign `+i`, unnormalised) for lengths with factors 2, 3, 7,
   11 and a prime.

Reported, not gated:

7. **Speed-up**: per image (median of 3 repeats) and per set, old at one
   thread against new at 1, 2, 4, 8 and 16 threads; wall, process CPU-s,
   peak RSS; old and new interleaved (ABAB) in each repeat; load before and
   after every process. Where the host is shared (siblings P1, P3, P8, L1
   and W1 run concurrently), walls at 8 and 16 threads are labelled
   load-contaminated and CPU-s is the steadier figure.
8. **Where the time goes**: `perf record -e cpu-clock:u` of one K image at
   one thread, old and new, by symbol (FFT, gridding, projection, `sin_cos`,
   other); in the old build gridding and projection are inlined into
   `Gridder::invert`, so they are reported together.
9. **Old versus new pixels** (float64, not the float32 FITS): maximum
   absolute and relative-to-peak differences of every C and K image.
10. **Scale probe**: the K `original` inputs tiled 4×, 16× and 41× in rows
    (1.6 M, 6.3 M and 16.1 M cells; same uv coverage, so the same layer
    occupancy) at 1 and 16 threads, old at 1 thread for the 4× and 16× points, to
    measure the per-sample cost, and the extrapolation to the whole-array
    chunk 0 (100.9 M cells; S1 section 2.8).

Failures are recorded as frozen; anything after the freeze that is not in
this protocol is labelled post-hoc.

## Baseline (measured before the freeze, baseline build, one thread)

`bench_p2_gridder.py bench` with the baseline library, one thread, three
repeats, 2026-10-30 09:06–09:12 CAT, one-minute load 16.7–20.0 (siblings
running; wall exceeds CPU by 15–20 % for that reason). Per image: median over
repeats, then median [range] over the images of the set.

| Set | Images | Set wall, median (min) | Set CPU-s, median | Per image wall | Per image CPU-s | Peak RSS | Repeats identical |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| C (9,169 / 7,812 gridded each) | 15 | 90.5 s (84.7) | 73.5 | 5.87 s [5.32–6.27] | 4.89 | 148 MB | yes |
| K (about 117,500 gridded each) | 6 | 32.3 s (32.0) | 28.2 | 5.57 s [5.46–6.22] | 4.64 | 126 MB | yes |

Where the time goes (`perf record -F 999 -e cpu-clock:u`, K `original`,
one image, 4,528 samples, symbols mapped from `nm` of the baseline library;
`perf-baseline-k-original-symbols.json`): `FftPlan::radix2` 77.0 %,
`Gridder::invert` (sample scan, `add_sample`, `project` inlined) 9.3 %,
libm (`sin_cos` of the projection) 5.4 %, `FftPlan::execute` (Bluestein
chirps) 5.0 %, Python and libc 2.8 %, `dct3_prefix` under 0.1 %. FFT 82 %,
gridding + projection about 15 %, normalisation (DCT, trim, scaling) under
0.5 %: the review's py-spy split (83 % FFT) reproduces.

## Measured results (2026-10-30, post-freeze runs as frozen)

Code: `27795e2` stage (a) (bucketing, one pass for dirty and PSF, rayon
over layers with the ordered sum, old FFT), `1d7c707` stage (b) (`rustfft`).
Final library `final/librang_core.so` SHA256 `fce67ad5…`, extension
`_core.abi3.so` `5706980d…`. Run directory
`outputs/p2-gridder-20261030-01` (logs `baseline.log`, `stage-a.log`,
`measure.log`). The host was shared throughout (siblings P1, P3, P8, L1, W1):
one-minute load 15–33 during the final measurements, so walls at 8 and 16
threads are load-contaminated, as the protocol anticipated.

### Gated criteria

| # | Criterion | Result | Margin |
| --- | --- | --- | --- |
| 1 | Task C, `compare_core_gridder.py` vs WSClean FITS (`c-final`) | **pass**: criteria 1–3 pass on all fifteen jobs, WCS equal | dirty L∞ 6.11e-7 of peak (tolerance 8.8e-6, 7 %), PSF 4.17e-7 (2.8e-6, 15 %); identical to the baseline to all printed digits |
| 2 | Task I, `run_core_imaging.py` (`i-final`) | **pass**, both comparisons, 0 failures; side-effect audit: inputs unchanged **and** git status unchanged | response fraction 1.312092e-7 of 1.6e-7 (82 %, unchanged from the baseline in the first seven digits), template flux 1.43e-7 of 4.7e-6, PSF vs fixedG0 8.9e-8 of 2.8e-6, weight sums 5.8e-16 of 1e-9, dirty pixels 6.11e-7 of peak of 8.8e-6, PSF pixels 4.17e-7 of 2.8e-6 |
| 3 | Task K, `k-replay` six arms (`k-replay-final`) | **pass**, 0 failures | pixels vs archived FITS: dirty 3.19e-8 of peak, PSF 2.98e-8 (float32 FITS rounding, as on the baseline); dirty-derived metrics 1.4e-14 relative (tolerance 8.8e-6); PSF metrics 4.4e-16 absolute (2.8e-6); counters exact; PSF normalisation 2.2e-16 relative; peak pixel and imaged cells equal; residual-RMS calls unchanged (headline ratio 0.9999581520151007 against the archived 0.9999581520151, null) |
| 4 | Stage (a) bit-identity | **pass**: K replay SHA256 equal to the archive for all six arms (`k-replay-stage-a`); C 15/15 and K 6/6 timing images bit-identical to the baseline at 1 and 16 threads (`bench-stage-a-*`) | exact |
| 5 | Thread-count identity | **pass**: every C and K image has one SHA256 across 1, 2, 4, 8, 16 threads and three repeats (`bench-final-*`, `determinism`), the scale probes too; the Rust test at 1, 2, 3, 8 threads and the pytest at 1 and 4 pass | exact |
| 6 | FFT correctness | **pass**: `fft2_matches_naive_backward_dft` (14×11, 12×13, 22×17, 1×7, 8×8; factors 2, 3, 7, 11, primes 13, 17) to 1e-10 | |

The archived K `dirty_sha256`/`psf_sha256` no longer match after stage (b),
as the protocol stated: the FFT rounds differently.

### Old versus new pixels (criterion 9)

Float64 images of the baseline library against the final one
(`images-old-vs-new.json`, 21 images of each kind): dirty at most 3.1e-14
absolute, **2.1e-15 of the peak**; PSF at most **2.1e-15**; no image is
bit-identical (expected: the FFT changed). The differences are eight to
nine orders of magnitude below the differences against WSClean, which is
why every comparator margin is unchanged.

### Speed-up (criterion 7)

`bench_p2_gridder.py bench`, three repeats, old (baseline library, one
thread) and new interleaved in each repeat, a fresh process per run,
`core_grid.invert` only. Per image: median over repeats, then median
[range] over the set. Load 21.7–26.0 (K), 14.6–32.6 (C).

| Set | Build, threads | Per image wall | Per image CPU-s | Set wall median (min) | Peak RSS | Speed-up (per-image wall) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| K (6) | old, 1 | 5.76 s [5.19–5.97] | 4.91 | 34.2 s (31.6) | 126 MB | 1 |
| K | new, 1 | 0.80 s [0.68–1.02] | 0.68 | 5.23 s (5.17) | 205 MB | 7.2× |
| K | new, 2 | 0.70 s [0.68–0.84] | 0.80 | 4.45 s (4.00) | 222 MB | 8.2× |
| K | new, 4 | 0.53 s [0.48–0.62] | 1.02 | 3.26 s (3.00) | 258 MB | 11.0× |
| K | new, 8 | 0.55 s [0.53–0.58] | 1.27 | 3.37 s (3.25) | 327 MB | 10.4× (load) |
| K | new, 16 | 0.61 s [0.55–0.63] | 1.63 | 3.34 s (3.27) | 466 MB | 9.5× (load) |
| C (15) | old, 1 | 5.48 s [3.94–7.55] | 4.70 | 77.0 s (57.3) | 148 MB | 1 |
| C | new, 1 | 0.82 s [0.65–1.15] | 0.67 | 14.4 s (9.07) | 234 MB | 6.7× |
| C | new, 2 | 0.66 s [0.46–0.75] | 0.81 | 10.4 s (6.93) | 251 MB | 8.3× |
| C | new, 4 | 0.60 s [0.50–0.76] | 1.03 | 9.11 s (5.72) | 286 MB | 9.2× |
| C | new, 8 | 0.60 s [0.51–0.70] | 1.23 | 9.04 s (4.92) | 355 MB | 9.2× (load) |
| C | new, 16 | 0.53 s [0.38–0.65] | 1.61 | 8.51 s (5.13) | 494 MB | 10.3× (load) |

On one thread the CPU per image falls 7.2× (4.91 → 0.68 CPU-s): the FFT
swap, the single scan of the samples and the shared phasor. Threads add
another 1.5× on this loaded host; the CPU-s rising with threads (0.68 →
1.63) is contention with the siblings and SMT, not extra work (the work and
the result are the same). The review's estimate of 0.15–0.3 s per image at
8 cores is not reached under this load; it needs a quiet host to be tested.
End-to-end drivers at the same load: task C, fifteen jobs, 118.6 s → 7.5 s
(gridding 117.2 s → 5.5 s, 0.32–0.54 s per job); task I 96.9 s → 7.6 s;
task K replay 27.1 s → 7.1 s (invert 3.6–4.6 s → 0.34–0.42 s per arm at
the default thread count).

Memory: the per-layer grids, the transpose buffer and the batch of 16
projected term images cost about 20 MB per busy thread plus 96 MB per
batch, so peak RSS grows from 205 MB (one thread) to 466 MB (16 threads) on
K, against 126 MB for the old single-threaded code. The 40-byte sample
tuples built twice are gone (24 bytes once; flagged cells dropped).

### Where the time goes now (criterion 8)

`perf record`, K `original`, one image at one thread, 598 samples (old:
4,528 for the same image): libm (`sin_cos` of the projection) 20.4 %,
`grid::transpose` 18.4 %, Python (loading inputs, outside `invert`) 14.9 %,
`rustfft` AVX mixed-radix butterflies (radix 7 and 11, 8-point) about 24 %,
libc (memset/memcpy of grids) 7.5 %, `Gridder::project` 7.2 %,
`Gridder::invert` and `grid_layer` 4.0 %, `dct3_prefix` under 0.2 %. The FFT
fell from 82 % of the image to about a quarter; the projection's `sin_cos`
and the transposes are now the largest items (open items below).

### Scale probe (criterion 10, one repeat)

K `original` inputs tiled in rows (`scale-{4,16,41}`), same uv coverage:

| Tile | Cells | Old t1 wall / CPU-s | New t1 wall / CPU-s | New t16 wall / CPU-s | New t16 peak RSS |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4× | 1.57 M | 10.2 s / 5.57 | 1.79 s / 0.81 | 0.51 s / 1.39 | 452 MB |
| 16× | 6.29 M | 15.4 s / 9.02 | 1.88 s / 0.92 | 0.81 s / 1.56 | 557 MB |
| 41× | 16.1 M | – | 2.12 s / 1.45 | 1.19 s / 2.08 | 774 MB |

Load 27–30; walls at one thread are about twice the CPU. Marginal cost on
one thread: about 25–55 ns CPU per cell (row × channel; about 30 % of the
cells are gridded), against about 730 ns per cell for the old code (its
64-layer scan; 5.57 → 9.02 CPU-s over 4.7 M cells).

**Whole-array extrapolation (estimate, not measured).** LUNO chunk 0 with
56 stations is 100.9 M cells (S1 section 2.8). At 512² pixels and 64 layers
the fixed part stays about 0.75 CPU-s per image; the per-cell part at
25–55 ns gives about 2.5–5.5 CPU-s, of which the one serial pass over (row,
channel) (counters, placement, counting sort) is roughly half and does not
parallelise as written. Estimate: **about 3–6 s per image at the whole
array on this host** (S1 estimated 100–150 s for the gridding term plus
2.9 s FFT for the old code), with a transient of about 52 B per kept sample
(about 1.6 GB at 30 M kept samples) on top of the inputs. If L1 chooses
finer pixels, the fixed part scales with padded pixels × layers.

### Not done

- No GPU spike (no CUDA toolkit or Vulkan in WSL per S1; the CPU path now
  takes an image well under a second at four stations).
- No f32 grids, no parallel serial pass, no in-layer parallelism (outside
  the protocol).

## For the coordinator

- **check-all:** `bash tools/check-all.sh` PASS on the final tree (1,703 s, 741 tests; log `outputs/p2-gridder-20261030-01/check-all.log`).
- **No shared file was edited.** `core/Cargo.toml` already carries `rayon`
  and `rustfft` (P0); C ABI, extension and wrapper signatures unchanged.
- **STATE paragraph (proposed):** "P2 gridder (merged 2026-10-30): the
  w-stacking gridder buckets samples by w-layer once, grids dirty image and
  PSF in one pass, runs the layers in parallel with rayon and an ordered
  sum, and uses `rustfft` at WSClean's exact padded size. One four-station
  image: 5.8 s → 0.80 s on one thread, 0.53–0.61 s at 4–16 threads on a
  loaded host; task C, I and K comparators pass with unchanged margins;
  images differ from the old FFT's by 2e-15 of the peak and are identical
  at any thread count. Whole array: about 3–6 s per image (estimate).
  [p2-gridder.md](p2-gridder.md)."
- **`tool-timings.md` rows:** the "Tool runs" table below.
- **Re-archive note:** the K archive's dirty/PSF SHA256 (and any other
  archive storing image hashes of the core) will not match a rerun after
  this merge; image metrics and pixels do, within task A's tolerances
  (measured above). Checkers that compare image hashes (S1's
  `profile_campaign.py` equality, `check_luno_campaign.py` if it hashes
  images) should compare metrics or pixels instead.
- **Determinism caveat for W1:** `rustfft` selects AVX, SSE or scalar code at
  run time from the CPU, so images can differ at the 1e-15 level between
  hosts and between the x86-64-v3 local build and a baseline wheel. Results
  do not depend on the thread count on any one host.
- **Upstream observations:** none for RATT or caracal-pipeline. Non-RATT:
  none new (WSClean plans FFTW at the exact padded size, confirmed in
  `main/settings.cpp` 468–474 and `gridding/wstackinggridder.cpp` 168–171,
  209–212; nothing to report).
- **For L1 and P5:** per-image gridder time at four stations is now
  0.7–0.8 CPU-s (0.5–0.6 s wall with threads); estimate for the whole-array
  chunk 0 about 3–6 s per image and about 1.6 GB transient sample memory
  (52 B per kept sample) plus about 0.5 GB of per-thread grids at 16
  threads. The image step is no longer the whole-array bottleneck; P5's
  gain correction (330 B per cell in NumPy) is.
- **Evidence to keep:** `outputs/p2-gridder-20261030-01` (447 MB; the
  inputs, bench JSONs, comparator receipts, perf data and the old/new
  float64 images). Deletable after merge: `k-replay-stage-a-stale-extension`
  (void run), `images-old`/`images-new` npy (about 90 MB, summarised in
  `images-old-vs-new.json`), `inputs-*` (103 MB, regenerable with
  `c-inputs` and `k-replay --dump-inputs`).
- **Environment lesson:** `maturin develop` must run from the repository
  root (`pyproject.toml` names `core/py/Cargo.toml`); run in `core/py` it
  installs a separate `rang-core-py` package and leaves `rangtoy._core`
  stale, silently.

## Open items

- `sin_cos` of the projection (20 % of a one-thread image) can be replaced
  by a per-layer phasor recurrence or a table per distinct `sqrt_lm` value
  only if the comparators allow; the transposes (18 %) can go by
  transforming columns in blocks of rows (rustfft processes many lines at
  once) or by projecting from the transposed grid.
- The serial (row, channel) pass will be about half of a whole-array image;
  parallelising it needs per-chunk counters summed in order (exactness of
  `image_weight` and the counts) and a two-pass placement.
- Memory per thread (about 20 MB at 616²) grows with the pixel count; a
  finer whole-array image may want a smaller batch or fewer threads.
- Thread scaling was measured on a host at load 15–33; a quiet-host run
  would settle the 8- and 16-thread figures.

## Tool runs

| When | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` + `uv pip install` of the worktree venv | 14.5 s | – | Python 3.14, public PyPI |
| 2026-10-30 | `cargo +1.93 build --release --offline` of `core/` (baseline) | 10.7 s | 382 MB | |
| 2026-10-30 | `maturin develop --release --offline` (baseline) | 0.8 s | 34 MB | |
| 2026-10-30 | `bench_p2_gridder.py c-inputs` | 0.8 s | 95 MB | 15 input files, 66 MB |
| 2026-10-30 | `bench_p2_gridder.py k-replay --dump-inputs` (baseline, precondition) | 27.1 s | 333 MB | load 3.5–4.4; 6 input files, 37 MB; hashes equal |
| 2026-10-30 | `run_core_gridder.py` (baseline) | 118.6 s | 138 MB | load 4.1→20; 7.6 s per job |
| 2026-10-30 | `compare_core_gridder.py` (baseline) | 0.6 s | 65 MB | |
| 2026-10-30 | `run_core_imaging.py` (baseline) | 96.9 s | 212 MB | load 20 |
| 2026-10-30 | `bench_p2_gridder.py bench` K, old, t1 × 3 | about 100 s | 126 MB | load 16.7–19.4 |
| 2026-10-30 | `bench_p2_gridder.py bench` C, old, t1 × 3 | about 270 s | 148 MB | load 19.4–20.0 |
| 2026-10-30 | `perf record` + `time` K `original` (baseline) | about 6 s | – | 4,528 samples |
| 2026-10-30 | `cargo build` + `cargo test grid` stage (a) | 5.0 s + under 1 s | – | 6 tests pass |
| 2026-10-30 | `bench` C and K, stage (a), t1 and t16, one repeat | about 140 s | 402 MB | load 15–22; 15/15 and 6/6 bit-identical to baseline |
| 2026-10-30 | `maturin develop` run in `core/py` (operator error, at setup and stage a) | 0.8 s | – | installed a stray `rang-core-py` package and left `rangtoy._core` stale; the first stage (a) K replay (`k-replay-stage-a-stale-extension`, 49.8 s) therefore tested the baseline extension and is void; uninstalled and rerun from the root. The baseline extension was the one `uv pip install -e .` built from `43dc3c7`, so the baseline runs stand |
| 2026-10-30 | `maturin develop --release --offline` from the root (stage a) | about 30 s | – | |
| 2026-10-30 | `k-replay` stage (a) | 7.3 s | 611 MB | load 21; hashes equal |
| 2026-10-30 | `cargo clippy -D warnings`, `cargo fmt --check` (core) | about 20 s | – | clean |
| 2026-10-30 | `cargo build` + `cargo test grid` + clippy stage (b) | 25.5 s + under 1 s | – | 6 tests pass |
| 2026-10-30 | `maturin develop --release --offline` (final) | 32.7 s | 681 MB | |
| 2026-10-30 | `k-replay` final | 7.1 s | 708 MB | load 20.8 |
| 2026-10-30 | `run_core_gridder.py` final | 7.5 s | 515 MB | load 20.6 |
| 2026-10-30 | `compare_core_gridder.py` final | 0.8 s | 66 MB | |
| 2026-10-30 | `run_core_imaging.py` final | 7.6 s | 568 MB | load 22.7 |
| 2026-10-30 | `time --save-images` C and K (t16) + `diff` | about 12 s | – | |
| 2026-10-30 | `perf record` K `original` final | about 1 s | – | 598 samples |
| 2026-10-30 | `bench` K, old t1 + new t1–16, three repeats | 168 s | 466 MB | load 21.7–26.0 |
| 2026-10-30 | `bench` C, old t1 + new t1–16, three repeats | 426 s | 494 MB | load 14.6–32.6 |
| 2026-10-30 | scale probes 4×, 16×, 41× | 37 s | 774 MB | load 27–30 |
| 2026-10-30 | `pytest tests/test_p2_gridder.py tests/test_core_grid.py tests/test_core_imaging.py` | 1.8 s | 81 MB | 14 passed |
| 2026-10-30 | `bash tools/check-all.sh` (final tree) | 1702.6 s | 1.88 GB | **PASS**; pytest 741 passed in 1617 s; root 19 and core 48 Rust tests; clippy, fmt, ruff clean; load 28→36 |
