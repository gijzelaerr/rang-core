# Big plan task DF1: an exact gridder and degridder (wgridder algorithm)

Protocol frozen 2026-10-30 on branch `df1-wgridder` (from `5965d37`),
before any gridder code. Task DF1 of [big-plan.md](big-plan.md), as
recommended by section 4.1 ("First protocol to freeze: DF1, exact gridder")
and item 0 of [ddfacet-feasibility.md](ddfacet-feasibility.md). Status at
freeze: **proposed; the oracle precondition and item 0's convention pin are
measured (below); nothing of the port is implemented.**

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
