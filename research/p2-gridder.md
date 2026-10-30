# Big plan task P2: the gridder's FFT and parallel w-layers

Protocol frozen 2026-10-30 on branch `p2-gridder` (from `43dc3c7`), before
any change to `core/src/grid.rs`. Status: **protocol frozen; baseline
measured; implementation not started.** Task P2 of
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
