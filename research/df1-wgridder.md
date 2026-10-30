# Big plan task DF1: an exact gridder and degridder (wgridder algorithm)

Protocol frozen 2026-10-30 on branch `df1-wgridder` (from `5965d37`),
before any gridder code. Task DF1 of [big-plan.md](big-plan.md), as
recommended by section 4.1 ("First protocol to freeze: DF1, exact gridder")
and item 0 of [ddfacet-feasibility.md](ddfacet-feasibility.md). Status at
freeze (`7ddace5`): proposed; the oracle precondition and item 0's
convention pin measured; nothing of the port implemented.

**Status now: implemented and measured; every gated criterion passes as
frozen** ([Measured results](#measured-results-2026-10-30-post-freeze-runs-as-frozen)).
The port agrees with ducc0 to 1e-12–1e-14 of the peak in f64 away from the
field edge, is adjoint to 4e-13, and is bit-identical at 1–16 threads.
Item 0 is attributed: the w-stacking image's 19 % from the DFT is aliasing
of WSClean's Kaiser–Bessel kernel at padding 1.2 (98.9 % reproduced by an
aliasing prediction), plus a pixel mis-map in the study's orientation
search; not a defect of `grid.rs`. Cost: 0.13–0.16 s per four-station
image (dirty + PSF) at 16 threads against w-stacking's 0.38–0.41 s, but
3.7–4.4× slower than ducc0 on one thread, so it scales worse than w-stacking at
many visibilities (open item).

## Scope (fixed before code)

A Rust port of the wgridder algorithm of Arras, Reinecke, Westermann and
Enßlin (2021, A&A 646, A58) as implemented in ducc0 0.42.0
(`src/ducc0/wgridder/wgridder_impl.h`, `src/ducc0/math/gridding_kernel.{h,cc}`,
`src/ducc0/math/gl_integrator.*`, `src/ducc0/fft/fft.h` `good_size_cmplx`;
GPL-2.0-or-later, read from tag `ducc0_0_42_0`, commit `42ce8ab5`), facet-free:

- `vis2dirty` (visibilities to dirty image) and `dirty2vis` (image to
  visibilities), f32 and f64 paths (grid, FFT, kernel and phases in the
  working precision; uvw, frequencies and the parameter calculation in f64,
  as ducc0);
- the exponential-of-semicircle (ES) kernel `exp(β W (((1−x²)^e0) − 1))`
  with ducc0's `KernelDB` rows (support W, oversampling σ, ε, β, e0, ndim,
  precision), evaluated through ducc0's piecewise Chebyshev-to-monomial
  approximation (`FunctionApproximator`, degree W+3), and the correction
  function by ducc0's Gauss–Legendre quadrature (`GLFullCorrection`,
  p = ⌊1.5 W⌋ + 2, 2p nodes);
- grid sizes `nu = 2 good_size_cmplx(⌊nx σ / 2⌋ + 1)` (at least 16), w
  planes as `countRanges` (`dw = 0.5 / σ / max|n−1+nshift|`,
  `nplanes = ⌊(wmax−wmin)/dw + W⌋`, `wmin`, `wshift`), the `nshift`
  recentring (`−(nm1max + nm1min)/2`, on by default) with its
  per-visibility phase, the w-screen per plane and
  `apply_global_corrections` (u, v and w correction functions, optional
  division by n); `lshift/mshift` (`center_x/center_y`, with ducc0's
  recentring `r_l, r_m`), `flip_u/v/w`, `divide_by_n`, `do_wgridding`
  (false: one plane, w ignored);
- **kernel and grid choice by an explicit rule independent of the thread
  count**: ducc0's `getNuNv` cost model evaluated with `nthreads = 1` and
  the SIMD width fixed at `vlen = 8` for both precisions (what the wheel's
  active `x86-64-v4` profile uses on this host: `native_vector_lengths()`
  = (16, 8), capped at 8 by `mysimdlen`), `sigma_min = 1.1`,
  `sigma_max = 2.6`, counting only active visibilities
  (`|vis|² · wgt · mask ≠ 0` when gridding) as ducc0 does, with the
  gridding/degridding cost factor; an override takes an explicit kernel
  row and grid size so that agreement can always be measured at an
  identical kernel;
- parallelism with rayon (`RAYON_NUM_THREADS`) over w-planes, each plane
  gridded, transformed and projected by one task, the planes' image terms
  added in plane order (as P2); for `dirty2vis` each visibility's
  contributions are accumulated in plane order. Visibilities are bucketed
  once by first plane; each plane reads its buckets in row-channel order.
  The result does not depend on the thread count.

Conventions are rang's direct Fourier transform's (the DFT oracle below):
pixel `(i, j)` of an `(nx, ny)` image, first axis l, lies at
`l = (i − nx/2) dx`, `m = (j − ny/2) dy`;
`dirty(l, m) = Σ_k wgt_k Re[V_k e^{+2πi(u l + v m + w (n−1))}]` and
`V_k = wgt_k Σ I(l, m) e^{−2πi(u l + v m + w (n−1))}`, uvw in wavelengths,
no division by n unless asked. ducc0 meets these with `flip_w=True,
divide_by_n=False` (its default `divide_by_n=True` and unflipped w differ:
measured below). Out of scope: facets, BDA input, the tuned variants
(w-towers, DF1b), the imaging chains (DF2).

Owner files: `core/src/wgridder.rs`, `core/src/ffi_wgridder.rs`,
`python/rangtoy/core_wgridder.py`, `examples/oracle_ducc0.py`,
`examples/compare_core_wgridder.py`, `examples/bench_df1.py`,
`tests/test_core_wgridder.py`, this file and
`research/results/df1-wgridder.json`. `core/src/lib.rs` and the extension
belong to P7: on the branch the two Rust files are compiled as a standalone
`cdylib` (generated root with `#[path]` modules, rayon and rustfft from the
core's lock, offline) into `core/target/df1-standalone`, as P5 did, loaded
through ctypes by `core_wgridder`; Rust tests, clippy and fmt run on that
crate. The `pub mod` and binding lines go to the coordinator. ducc0 is not
added to `pyproject.toml`; the tests use `importorskip`.

## Inputs

1. **Synthetic** (`oracle_ducc0.py synthetic`, seeds 101–104): four
   cases, `small-8arcmin` (64², field 8′, |w| ≤ 1e3 λ), `mid-2deg` (128²,
   2°, 3e3 λ), `wide-0p3rad` (128², 0.3 rad, 1e4 λ) and `wide-0p3rad-rect`
   (128 × 64, 0.3 rad, 1e4 λ); 300–400 rows × 3–4 channels (0.9–1.6 GHz),
   uv to 0.45 of the Nyquist extent, w uniform of both signs; complex128
   visibilities of four point sources on pixel centres (one near a corner)
   plus noise, weights 0.5–1.5; a sparse 16-pixel image for the degridding
   direction. SHA256 in `synthetic.json`.
2. **LUNO four-station slice** of the feasibility study, regenerated
   (`oracle_ducc0.py export`, the core's own MS reader on
   `outputs/luno-solve-20261029-02/work.ms`): field 1, cross-correlations,
   every 16th channel (128), Stokes I complex64, `4 min(w_XX, w_YY)`;
   7,377 unflagged visibilities, weight sum 129,363.328125, |w| ≤ 160.025 λ
   (the study's numbers exactly); 512² at 8″. `inputs.npz` SHA256
   `3786691f…`.
3. **Task C/I/K gridder inputs** of P2 (`outputs/p2-gridder-20261030-01/
   inputs-{c,k}`) for the cost table and the reported science metrics.

## Oracles

- **Direct Fourier transform**, float64, both directions (`oracle_ducc0.py`).
  Slice: dirty and PSF (`dft-slice`, 47 s): peak 9.2725576 × weight sum
  (study: 9.27256), PSF edge level 0.801, SHA256 recorded.
- **ducc0 0.42.0** wheel (PyPI), `nthreads=1`, `flip_w=True`,
  `divide_by_n=False`, `verbosity=1` report captured (grid, planes,
  support), every output hashed (`oracle_ducc0.py ducc`).

## Precondition (measured before the freeze)

Convention (`wide-0p3rad`, ε = 1e-10, L∞ / peak against the DFT):
`flip_w=True, divide_by_n=False` 9.2e-13; `flip_w=True, divide_by_n=True`
1.8e-2; unflipped w 1.01 (both `divide_by_n`). Run
`outputs/df1-wgridder-20261030-01/synthetic/convention.json`.

ducc0 against the DFT, `nthreads=1`, worst case over the cases, L∞ / max|DFT|
(`ducc-synth/ducc.json`, `ducc-slice/ducc.json`):

| precision, ε | synthetic vis2dirty | synthetic dirty2vis | slice dirty | slice PSF | 10 ε |
| --- | ---: | ---: | ---: | ---: | ---: |
| f32, 1e-4 (gated) | 2.4e-5 | 4.0e-5 | 1.2e-5 | 9.7e-6 | 1e-3 |
| f32, 1e-5 (reported) | 8.6e-7 | 2.1e-6 | 2.8e-6 | 4.9e-6 | 1e-4 |
| f64, 1e-7 (gated) | 1.1e-8 | 4.1e-8 | 3.7e-8 | 3.7e-8 | 1e-6 |
| f64, 1e-9 (reported) | 1.0e-10 | 2.3e-10 | 2.1e-10 | 2.1e-10 | 1e-8 |

So the L∞ / peak metric is met by ducc0 itself with margin on every case
(ε is not an L∞ guarantee; relative L2 and RMS are recorded beside it).
ducc0's choices (`verbosity=1`), e.g. slice f64 1e-7: 720² grid,
11 planes, support 11; `wide-0p3rad` f64 1e-7: 162², 301 planes, support 14.
The slice DFT floor is now 2e-10, not the study's 6e-8 (float64 tensordot
over complex128 instead of complex64 products).

## Item 0, pinned before the freeze

The study's 19 % (and 12 % at padding 2) between the core's w-stacking image
and the DFT is attributed (`compare_core_wgridder.py item0`, run
`item0/item0.json`, 48 s):

1. **Pixel map and w sign, derived from `grid.rs`** (`project`,
   `initialize_sqrt_lm`, no search): output pixel `(X, Y)` holds the DFT
   pixel `(ix, iy) = (X, H − Y)` of the visibilities with **w negated**
   (equivalently: WSClean's FITS image is the rang-convention image of the
   data with v and w flipped, transposed). Checked on an asymmetric point
   at (+60, +25) pixels with w scaled × 100: with w negated it lands on
   (316, 281) as expected, peak 0.99999; with w as given at (292, 271).
   The study's search chose its map by PSF fit; the PSF is nearly
   centrosymmetric, so the chosen flips differed between settings and the
   12 % at padding 2 is that mis-map.
2. **With the fixed map** the core against the DFT: padding 1.2 / kernel 7
   / 64 layers (WSClean's defaults) 20.4 % L∞ of the peak, but 0.37 % in the
   inner half; padding 2: 1.2 % (0.020 % inner); padding 2, kernel 15,
   512 layers: **2.1e-5**. Every sample is gridded (7,377 of 7,377).
3. **The residual is aliasing of the w-stacking grid**, measured against
   ducc0 at ε 1e-9 (itself 1.7e-10 from the DFT): it falls with padding
   (1.2 → 4: 19 % → 5.9e-5 at kernel 7) and kernel size, and is the same
   with w forced to zero (19.5 %), so not the w layers. The aliasing
   predicted from the kernel's Fourier transform and the true dirty image
   at the alias positions (ducc0 with centre shifts, |j| ≤ 6 periods per
   axis), `Σ_j D(x + jP) T(x + jP) / T(x)`, reproduces it: at padding 1.2
   predicted 19.48 % against measured 19.46 %, core minus prediction 0.22 %
   (98.9 % explained); at padding 2, 1.19 % against 1.18 %, residual 0.021 %.
   The cause is WSClean's Kaiser–Bessel kernel (7 taps, α 8.6) at padding
   1.2 on a four-station PSF whose sidelobes stay near 0.8 over the whole
   sky, so the folded sky is barely suppressed near the field edge.

Not a defect of `grid.rs`: the core reproduces WSClean to 6e-7 (task C).
The fix proposals (for P2's file, listed only): none for correctness; for
comparisons against an exact image use padding ≥ 2 with kernel 15, or the
exact gridder (DF2).

## Gated criteria (frozen)

Gated epsilons: f32 ε = 1e-4 and f64 ε = 1e-7. Reported, not gated:
f32 1e-5 and f64 1e-9.

1. **Against the DFT.** Core `vis2dirty` (synthetic dirty images; slice
   dirty and PSF) and core `dirty2vis` (synthetic visibilities):
   L∞ / max|DFT| ≤ 10 ε for every case at both gated epsilons.
2. **Against ducc0** at the same ε, precision and kernel (nthreads=1):
   L∞ / max|ducc0| ≤ ε, both directions, every case, both gated epsilons.
   The real figure is reported; for a faithful port it should be near
   rounding (about 1e-12 in f64), and anything far above that is reported
   as a fidelity finding even when the gate passes.
3. **Adjointness** in f64 at ε 1e-7 and 1e-9 on every synthetic case with
   random real images x and random complex visibilities y (seeds recorded):
   `|⟨dirty2vis(x), y⟩ − ⟨x, vis2dirty(y)⟩| / (‖dirty2vis(x)‖₂ ‖y‖₂) ≤ 1e-12`
   with `⟨a, b⟩ = Re Σ conj(a) b`.
4. **Thread independence.** SHA256 of every output (both directions, both
   precisions, every synthetic case and the slice, gated ε) identical at
   `RAYON_NUM_THREADS` 1, 2, 4, 8 and 16, each in a fresh process.
5. **Kernel table and choice.** The Rust table equals the rows extracted
   from `gridding_kernel.cc` at the tag (SHA256 of the extracted text
   recorded, since the clone is deleted at the end); the core's
   `(supp, nu, nv, nplanes)` equal ducc0's `verbosity=1` report on every
   oracle case and ε (both directions).

## Reported, not gated

- Single visibilities at many sub-cell offsets (w = 0 and w ≠ 0) against
  ducc0: the kernel values directly.
- Relative L2 and RMS beside every L∞.
- **Task C/I/K science metrics** with the exact gridder (f64, ε 1e-6, in
  WSClean's FITS orientation by the map of item 0), by substituting
  `core_grid.invert` in the existing drivers and comparators
  (`run_core_gridder.py` + `compare_core_gridder.py`, `run_core_imaging.py`,
  `bench_p2_gridder.py k-replay`) at run time, without editing them; task
  A's tolerances compare w-stacking with w-stacking, so a move beyond them
  is information (aliasing removed), not a failure.
- **Cost**: wall, process CPU and peak RSS per image (dirty + PSF, i.e.
  two `vis2dirty` calls, against P2's one pass giving both), fresh process
  per measurement, load recorded, at 1, 4 and 16 threads, on the six K
  inputs and the 4×, 16× and 41× row tiles of K `original`, against P2's
  w-stacking (0.8 s per four-station image) and ducc0 at the same threads;
  a whole-array estimate.

Failures are recorded as frozen; anything decided after this commit is
labelled post hoc.

## What was built (code `99365ae`, final runs on the branch head)

- `core/src/wgridder.rs` (new, about 1,000 lines of code plus the 939-row
  table and 7 unit tests): `vis2dirty`, `dirty2vis`, `plan`, the kernel
  table (`kernel_row`, `available_kernels`), `good_size_complex`,
  `EsKernel` (ES kernel, `FunctionApproximator` port, Gauss–Legendre
  correction), the `getNuNv` choice with one thread and `COST_VLEN = 8`,
  `countRanges`' planes, `nshift`, the w-screens and global corrections,
  l/m shifts with recentring, both modes (`do_wgridding` false: one plane).
  Each plane is gridded into its own complex grid, transformed along v for
  touched u rows and along u for the image columns only (rustfft), and
  projected; plane terms are added in plane order in batches of the rayon
  thread count. Degridding computes each plane's contributions in parallel
  and accumulates them per visibility in plane order.
- `core/src/ffi_wgridder.rs` (new): `rang_core_wgridder_{vis2dirty,dirty2vis}_{f64,f32}`,
  `rang_core_wgridder_kernel_row`, `rang_core_wgridder_last_error`;
  `catch_unwind`, status 0/1/2. Additive; nothing existing changed.
- `python/rangtoy/core_wgridder.py` (new): `vis2dirty`, `dirty2vis` (ducc0's
  keywords plus `kernel=(row, nu, nv)`, `return_info`), `kernel_table`,
  `fits_image` (WSClean FITS orientation and PSF-centre normalisation, the
  map of item 0), the standalone build (`core/target/df1-standalone`,
  files rewritten only on change).
- `examples/oracle_ducc0.py` (`export`, `dft-slice`, `synthetic`, `ducc`,
  `convention`, `kerneldb`), `examples/compare_core_wgridder.py` (`item0`,
  `gates`, `threads`, `hashes`, `science`, `kpixels`, `summary`),
  `examples/bench_df1.py` (`time`, `bench`), `tests/test_core_wgridder.py`
  (6 tests, ducc0 by `importorskip`).

## Measured results (2026-10-30, post-freeze runs as frozen)

Run directory `outputs/df1-wgridder-20261030-01` (81 MB); compact result
`research/results/df1-wgridder.json`. The gates and thread hashes were run
on the code before the clippy rewrites (`gates/`, `threads.json`) and again
on the committed code (`gates-final/`, `threads-final.json`): every output
SHA256 is identical between the two.

### Gated criteria

| # | Criterion | Result | Worst figure (limit) |
| --- | --- | --- | --- |
| 1 | Against the DFT, ≤ 10 ε | **pass**, every case and direction | f32 1e-4: 4.0e-5 (1e-3), `small-8arcmin` dirty2vis; f64 1e-7: 4.1e-8 (1e-6) |
| 2 | Against ducc0, ≤ ε | **pass** | f32 1e-4: 1.1e-5 (1e-4), slice PSF; f64 1e-7: 1.7e-10 (1e-7), `wide-0p3rad` vis2dirty |
| 3 | Adjointness ≤ 1e-12 | **pass** | 4.2e-13 (`wide-0p3rad`, ε 1e-7); others 1e-17–7e-14 |
| 4 | SHA256 at 1, 2, 4, 8, 16 threads | **pass**, 20 outputs identical | – |
| 5 | Kernel table and choice | **pass**: 939 rows equal in value and text (SHA256 `0427f594…` both); `(supp, nu, nv, nplanes)` equal to ducc0's report in all 40 (case, ε, direction) runs | – |

Reported epsilons (f32 1e-5, f64 1e-9) also meet both limits: worst against
the DFT 2.9e-6 and 2.3e-10, against ducc0 9.5e-7 and 3.6e-12.

**Fidelity finding (reported).** In f64 the port matches ducc0 to
1e-14–5e-12 of the peak, except `vis2dirty` on the 0.3 rad cases (1.7e-10
and 8.4e-11 at ε 1e-7). The difference sits in the outermost pixels:
excluding a border of 1, 2, 4 and 8 pixels it falls to 5.1e-11, 7.0e-12,
1.4e-12 and 7.7e-13. It is rounding amplified by the correction function,
which is largest at the field edge, and it is the same in a single-row
case (1e-9 at ε 1e-7, all at edge pixels); `dirty2vis`, which applies the
same correction before the FFT, matches to 1e-12. Single visibilities at
40 sub-cell offsets: 1.8e-12 (w = 0) and 2.0e-12 (w ≠ 0) of ducc0's peak.

In f32 the port and ducc0 differ by about the f32 accumulation error
(1e-7–1e-5 of the peak); both are within ε of each other and within 10 ε
of the DFT.

### Item 0 (measured before the freeze, recorded above)

The w-stacking image differs from the DFT by 20.4 % of the peak at the
default padding 1.2 (0.37 % in the inner half), 1.2 % at padding 2 and
2.1e-5 at padding 2 with kernel 15 and 512 layers, with the pixel map
derived from `grid.rs`; aliasing predicted from the kernel transform
reproduces 98.9 % (padding 1.2) and 98.2 % (padding 2) of the L∞. With the
exact gridder, the same map holds on real data (below): the C, I and K
images differ from w-stacking by 19–32 % of the peak at the edge and
0.3–0.6 % in the inner half, the aliasing figure.

### Reported: science metrics through the exact gridder (f64, ε 1e-6)

`core_grid.invert`'s pixels replaced at run time (counters from the
w-stacking call), drivers and comparators unedited
(`compare_core_wgridder.py science`):

- **Task C** (fifteen jobs, `run_core_gridder.py`): driver criteria 1–3
  pass (counters are w-stacking's). Against WSClean's FITS
  (`compare_core_gridder.py`): dirty L∞ 14–32 % of the peak (tolerance
  8.8e-6), PSF 18.8 % (20.8 % on `caracal-firstpass-rejected`), WCS equal;
  inner-half differences against core w-stacking at most 0.56 % (dirty).
  The exact gridder removes WSClean's padding-1.2 aliasing, so task A's
  w-stacking tolerances do not apply.
- **Task I** (`run_core_imaging.py`): both comparisons fail (23 failures of
  the 860 checked values), as expected: exact, WCS, weight sums, unit flux
  and closure classes pass; response fractions move by up to 0.036
  absolute (`omitted-total` 0.776 → 0.812, `omitted-adaptation` −0.224 →
  −0.188; tolerance 1.6e-7), template fluxes by up to 37 % relative on
  near-zero coefficients (`complete-adaptation`) and 4.6 % on
  `omitted-total`; PSF-vs-fixedG0 L∞ 0.0738 against 0.0747. No sign of a
  response fraction or of a template coefficient changes. Central RMS
  difference of the dirty images 0.0097, border RMS 0.54 (the aliasing is
  at the border).
- **Task K**: `bench_p2_gridder.py k-replay` cannot run any more: the
  archived fetched bytes (`outputs/core-k-20261030-01/fetch/`) are no
  longer on the host (failure recorded). Pixels only, from P2's dumped
  gridder inputs of the six arms (`kpixels`): dirty L∞ 19.0 % of the peak,
  inner half 0.32 %, RMS 2.7 %; PSF L∞ 0.190, inner 0.0032; the same on
  every arm. The K science calls (residual-RMS ratios) are not re-measured.

### Reported: cost

Per image = dirty + PSF (w-stacking: one call; exact gridder and ducc0: two
`vis2dirty` calls). f64, ε 1e-6, fresh process per (implementation,
threads), load 8.5–10.8 (one-minute), two repeats on the six K arms
(medians; range over repeats). ducc0's pool was capped at one thread by
`OMP_NUM_THREADS=1` in the run environment, so its rows are single-threaded
whatever `RAYON_NUM_THREADS` says (post hoc finding).

| Input (visibilities gridded) | Threads | w-stacking (P2) | exact gridder | ducc0 (1 thread) |
| --- | ---: | ---: | ---: | ---: |
| K six arms (117 k) | 1 | 0.66–0.72 s, 204 MB | 0.41–0.44 s, 121 MB | 0.11–0.13 s, 112 MB |
| | 4 | 0.38–0.39 s, 256 MB | 0.16–0.19 s, 171 MB | – |
| | 16 | 0.38–0.41 s, 466 MB | 0.13–0.16 s, 328–356 MB | – |
| K, f32 ε 1e-4 | 1 / 16 | – | 0.26 s / 0.074 s | 0.077 s |
| K `original` × 4 (470 k) | 1 / 16 | 0.69 / 0.29 s | 1.07 / 0.40 s, 348 MB | 0.30 s |
| × 16 (1.9 M) | 1 / 16 | 0.94 / 0.53 s | 3.69 / 1.14 s, 619 MB | 0.93 s |
| × 41 (4.8 M) | 1 / 16 | 1.51 / 0.70 s, 773 MB | 8.70 / 2.51 s, 1.24 GB | 1.96 s, 749 MB |

The exact gridder is faster than w-stacking at four stations (it needs 8
planes of a 900² grid against 64 layers of 616²) but its per-visibility
cost is about 1.8 µs per image on one thread (0.9 µs per `vis2dirty`),
4.4× ducc0's 0.4 µs: kernel taps are recomputed per plane (8 planes ×
2 × 8 polynomials of degree 11) and evaluated by scalar Horner without
SIMD, against ducc0's vectorised even/odd evaluation and tiled buffers.
Peak RSS at 4.8 M visibilities is 1.24 GB, mostly the wrapper's complex128
and float64 copies (16 M cells) and a second unit-visibility array for the
PSF, plus 48 + 48 + 16 bytes per visibility in the core.

**Whole-array estimate (not measured).** LUNO chunk 0 (56 stations,
100.9 M cells, about 30 M gridded): about 50 s per image on one thread and
15 s at 16 threads with the code as it is, against 3–6 s for P2's
w-stacking and about 12 s for ducc0 on one thread; memory several GB from
the wrapper copies. Before DF2 puts the gridder into the whole-array
chains, the gridding loop needs the optimisations listed in the open items.

## For the coordinator

**STATE paragraph.** DF1 (exact gridder, `research/df1-wgridder.md`,
branch `df1-wgridder`): a Rust port of ducc0 0.42's wgridder
(`core/src/wgridder.rs`, `ffi_wgridder.rs`, `core_wgridder.py`), f32 and
f64, both directions, ducc0's 939-row kernel table and a thread-free kernel
choice. All five gated criteria pass as frozen: against a float64 DFT
≤ 10 ε (worst 4.0e-5 at f32 1e-4, 4.1e-8 at f64 1e-7), against ducc0 ≤ ε
(1e-12–1e-14 in f64 away from the field edge, 1.7e-10 at the edge of a
0.3 rad field from correction-amplified rounding), adjoint to 4.2e-13,
bit-identical at 1–16 threads, kernel table and choices equal to ducc0's.
Item 0 of the DDFacet study is attributed: the core w-stacking image's 19 %
from the DFT on the LUNO slice is aliasing of WSClean's KB kernel at
padding 1.2 (reproduced to 98.9 % by an aliasing prediction; 2.1e-5 at
padding 2 with kernel 15), plus a pixel mis-map in the study's search; no
defect in `grid.rs`. Through the exact gridder the C/I/K images move by
19–32 % of the peak at the edge and 0.3–0.6 % inside; task I's response
fractions move by up to 0.036 (no sign changes). Cost: 0.13–0.16 s per
four-station image at 16 threads (w-stacking 0.38–0.41 s) but 3.7–4.4× slower than ducc0
per visibility, so whole-array use needs the gridding loop optimised first.

**Lines for `core/src/lib.rs`** (alphabetical, beside the others):

```rust
pub mod ffi_wgridder;
pub mod wgridder;
```

and in its doc comment: "DF1 adds `wgridder` (an exact w-gridder and
degridder ported from ducc0 0.42, research/df1-wgridder.md)". After that
`core_wgridder.library()` uses `librang_core` and skips the standalone
build; the Rust unit tests then run in check-all.

**Bindings for P7's extension** (`core/py/src/lib.rs`, optional; the
ctypes path works without them): two functions per precision taking the
`Options` fields as scalars and NumPy buffers, calling
`rang_core::wgridder::vis2dirty::<T>` and `dirty2vis::<T>` and returning
`Plan::to_array()`; `core_wgridder` would prefer `ext.wgridder_vis2dirty_f64`
etc. when present (one `hasattr` check, as `p5_extension`).

**Timing rows for `research/tool-timings.md`:** the table under "Tool runs"
below (all 2026-10-30).

**Recommendation for DF2** (the exact gridder in the imaging chains):

- Drivers: `core_imaging.image_job` (task I), `core_campaign.image_arm`
  (task K, L1 array campaign) and `run_core_gridder.py` (task C) all call
  `core_grid.invert`; DF2 should add `gridder="wgrid"` there, calling
  `core_wgridder.fits_image` (f64, ε 1e-6) and keeping the counters from
  the existing reader pass. w-stacking stays the default and the archive
  reproducer.
- Archives needing re-tolerancing: task C (`outputs/core-c-20261029-01`
  WSClean FITS, tolerance 8.8e-6/2.8e-6 is w-stacking against w-stacking);
  task I (`research/results/gain-tv-next-imaging.json`, the response
  fraction tolerance 1.6e-7 and template flux 4.7e-6); task K and L1
  (`research/results/core-k-luno-campaign.json`, `core-l1…`). The new
  reference is WSClean 3.7 `-gridder wgridder` (DF0) within ε plus
  WSClean's float tolerance; the expected size of the change is the
  aliasing figure above (edge 20–30 %, inner < 1 %).
- Before whole-array use: optimise the gridding loop (open items) or call
  for the measured ducc0 speed.
- Re-measure the K science calls with the exact gridder from a fresh
  fetch (the archived fetched bytes are gone).

**Upstream observations.**

- Non-RATT, ducc0 0.42.0: (1) `vis2dirty`/`dirty2vis` default
  `divide_by_n=True` and the w sign opposite to the usual
  `exp(+2πi(ul+vm+w(n−1)))` dirty-image convention: documented, but a trap
  (the study's 4 % at default settings); (2) the kernel and grid choice
  depends on `nthreads` and on the dispatched SIMD width (AVX-512 gives
  `vlen` 8 for f64, AVX2 4), so results at ε ≥ 1e-4 differ between thread
  counts and hosts (1.2e-5 against 8.4e-6 on the slice); a "deterministic
  choice" option would help reproducibility; (3) the pool size follows
  `OMP_NUM_THREADS` silently, so `nthreads=16` ran on one thread in our
  benchmark. No bug found.
- Non-RATT, WSClean (3.6, w-stacking default): with the default padding
  1.2 and the 7-tap KB kernel, sparse-array PSFs with sky-wide sidelobes
  alias into the field edge at the 20 % level (0.4 % inside); not a bug,
  a default worth a note to users of four-station data; the wgridder of
  3.6+ avoids it. Also `CalculateMsLimits` computes both bounds from u
  (already noted by task C).
- RATT, caracal-pipeline: none.

**Evidence to keep:** `outputs/df1-wgridder-20261030-01` (81 MB): slice
export and DFT, synthetic cases, ducc0 outputs and reports, `item0/`,
`kerneldb/rows.txt` (the extracted table; the ducc clone is deleted),
`gates*/`, `threads*.json`, `bench-*`, `science/` (C images, I run and
comparisons, K pixels), `logs/`. Deletable: `smoke-gates-01`,
`smoke-bench`, `science/c-run/images` once DF2 has its own runs.

**Deleted scratch:** `~/Build/tmp/20261030-ducc` (ducc clone at
`ducc0_0_42_0`, `42ce8ab5`), `~/Build/tmp/20261030-ducc-setup.log`.

## Open items

1. Gridding speed: precompute u/v taps once per visibility (not per
   plane), SIMD the polynomial evaluation (even/odd split as ducc0) and the
   tap loops, tile the grid writes; drop the wrapper's float64/complex128
   copies and the unit-visibility array for the PSF (a PSF mode in the
   core). Target: ducc0's 0.4 µs per visibility per image.
2. ducc0 multi-thread timings with `OMP_NUM_THREADS` unset (only the
   one-thread figures are valid here).
3. Task K science calls through the exact gridder need a fresh fetch.
4. DF0's WSClean 3.7 `-gridder wgridder` FITS as the external oracle of the
   FITS orientation and normalisation used by `fits_image` (verified here
   against core w-stacking at padding 2, kernel 15, to 1e-3 in a test and
   2.1e-5 on the slice).
5. BDA input, facets (DF3) and w-towers (DF1b) are out of scope.

## Tool runs

Host: WSL2 workstation, 16 threads, 30 GiB; load 4–11 (one-minute)
throughout. Wall and peak RSS from GNU `time` unless noted.

| Tool | Input | Wall | Max RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `git clone` ducc (GitLab) + checkout | `ducc0_0_42_0` | 4.2 s | – | read-only reference; deleted at the end |
| `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin ducc0==0.42.0` | worktree | 60.2 s | 605 MB | |
| `maturin develop --release --offline` | worktree | 0.5 s | 37 MB | |
| `oracle_ducc0.py export` | LUNO slice MS | 0.30 s | 72 MB | nvis 7,377, weight sum 129,363.328125 (study's numbers) |
| `oracle_ducc0.py synthetic` | 4 cases | 1.6 s | 100 MB | |
| `oracle_ducc0.py convention` | `wide-0p3rad` | 0.42 s | 52 MB | `flip_w=True, divide_by_n=False` 9.2e-13 |
| `oracle_ducc0.py dft-slice` | slice, 512² | 47.4 s | 448 MB | dirty and PSF |
| `oracle_ducc0.py ducc` | synthetic, 4 ε | 0.86 s | 56 MB | |
| `oracle_ducc0.py ducc` | slice, 4 ε | 0.29 s | 79 MB | |
| `compare_core_wgridder.py item0` | slice | 48.1 s | 1.96 GB | 680 ducc0 calls for the aliasing prediction |
| `oracle_ducc0.py kerneldb` (first) | `gridding_kernel.cc` | 0.08 s | 38 MB | **failed**: 938 rows, the last row's `}};` not matched; fixed |
| `oracle_ducc0.py kerneldb` | same | 0.08 s | 38 MB | 939 rows, SHA256 `0427f594…` |
| `cargo build` standalone (first) | `df1-standalone` | 6.5 s | 376 MB | **failed**: trait bounds (13 errors); fixed |
| `cargo test` standalone | same | 32.1 s | 832 MB | **1 failed**: wrong expected `good_size_complex` values in the test (181 → 189, 1025 → 1029); test fixed |
| `cargo test` standalone | same | 39.5 s | 791 MB | 7 passed |
| `compare_core_wgridder.py gates` (smoke, labelled) | 2 synthetic cases | 77.7 s | 792 MB | includes a core library build; all checks pass |
| `compare_core_wgridder.py gates` | all cases | 33.6 s | 811 MB | **pass**; about 28 s was a standalone rebuild (wrapper rewrote its files each process; fixed later) |
| `compare_core_wgridder.py threads` | 1, 2, 4, 8, 16 | 141.0 s | 817 MB | identical; 26–30 s per process, the same rebuild |
| pytest `test_core_wgridder.py` | 6 tests | 37.4 s | 779 MB | pass |
| `cargo clippy -D warnings` standalone | same | 2.8 s | 361 MB | **failed**: 6 lints (needless range loops, `chunks_exact`, items after tests, negated comparisons); fixed |
| `cargo clippy -D warnings`, `rustfmt --check`, `cargo test` | same | 0.3 s, –, 26.8 s | 838 MB | clean; 7 passed |
| pytest `test_core_wgridder.py` without cargo on PATH | 6 tests | 0.7 s | – | **6 errors**: the shell lacked `~/.cargo/bin` (environment, not code); rerun below |
| pytest `test_core_wgridder.py test_core_grid.py` | 10 tests | 23.9 s | 829 MB | pass |
| `bench_df1.py time` smoke ×3 (labelled) | K `original` | 0.64 s / 28.5 s / 0.24 s | 223 / 814 / 79 MB | the 28.5 s was the rebuild; fixed (`_write_if_changed`), then 0.11 s per call |
| `bench_df1.py bench` | K six arms, 1/4/16 threads, 2 repeats | 35.0 s | 477 MB | table above |
| `bench_df1.py bench --single --epsilon 1e-4` | K six arms, 1/16 | 4.0 s | 181 MB | |
| `bench_df1.py bench --tile 4/16/41` | K `original` | 3.9 / 9.1 / 18.4 s | 463 MB / 634 MB / 1.27 GB | |
| `compare_core_wgridder.py science` + `run_core_gridder.py` | task C, 15 jobs | 7.9 s | 339 MB | driver criteria pass |
| `compare_core_gridder.py` (first) | C images | 0.26 s | 57 MB | **failed**: wrong candidate path (`c-run` instead of `c-run/images`); rerun 0.36 s |
| `compare_core_wgridder.py science` + `run_core_imaging.py` | task I | 8.4 s | 400 MB | exit 1: comparisons fail (reported above) |
| `compare_core_wgridder.py science` + `bench_p2_gridder.py k-replay` | task K | 0.15 s | 44 MB | **failed**: `outputs/core-k-20261030-01/fetch/result.json` no longer on the host |
| `compare_core_wgridder.py kpixels` | K six arms | 2.7 s | 355 MB | |
| `compare_core_wgridder.py gates` / `threads` (final code) | all | 1.1 s / 2.5 s | 136 / 204 MB | all outputs identical to the first runs |
