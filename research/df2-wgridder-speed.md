# Big plan task DF2a: the exact gridder at ducc0's speed

Protocol frozen 2026-10-30 on branch `df2-wgridder-speed` (from `8c1726f`),
before any change to the gridder. Task DF2a of [big-plan.md](big-plan.md):
the speed half of DF2. The wiring into the imaging drivers and the
re-tolerancing against WSClean 3.7's wgridder (DF0, O-CASA) is DF2b, later.
Starting point: DF1's port of ducc0 0.42's wgridder
([df1-wgridder.md](df1-wgridder.md), `core/src/wgridder.rs`), which passes
all five DF1 gates but is 3.7–4.4× slower than ducc0 per visibility on one
thread and uses 1.25 GB against ducc0's 0.77 GB at 4.8 M visibilities.

**Status at freeze: proposed.** Nothing below is implemented or measured
except what DF1 already archived.

## Scope and owner files

Owner files: `core/src/wgridder.rs`, `core/src/ffi_wgridder.rs` (additive
only: new entry points, none changed), `python/rangtoy/core_wgridder.py`,
`examples/bench_df2.py` (new; `bench_df1.py` stays as DF1 archived it),
`tests/test_core_wgridder.py`, this file and
`research/results/df2-wgridder-speed.json`. Not edited: `grid.rs`,
`core_grid.py`, `core_imaging.py`, the shared files (`core/src/lib.rs`,
`core/py/src/lib.rs`, `Cargo.toml`/`Cargo.lock`, `.cargo/config.toml`,
`tools/check-all.sh`), and DF1's comparators `examples/compare_core_wgridder.py`
and `examples/oracle_ducc0.py` (P9 owns `examples/compare_core_*`; they are
run unmodified). The core library is reached as in DF1: `core_wgridder`
loads its task-local standalone build (`core/target/df1-standalone`,
ctypes), because the extension does not bind the gridder (since P7 the only
ctypes path left is such a task-local loader). Evidence goes to fresh
`outputs/df2-20261030-NN` directories only.

Build target: the repository's `.cargo/config.toml` builds for
`x86-64-v3` (AVX2, four f64 lanes, no FMA contraction by the compiler);
ducc0's wheel dispatches AVX-512 on this host (eight f64 lanes). The shared
config is not changed; no new crate is added (no `wide`: the core's
manifest and lock are shared, and the standalone manifest is generated
with rayon and rustfft only). Vectorisation is by fixed-size arrays
monomorphised on the support (ducc0's `SUPP` dispatch) and loops the
compiler vectorises.

## Inputs

1. **DF1's gate cases**: the four synthetic cases and the LUNO four-station
   slice (`outputs/df1-wgridder-20261030-01/{synthetic,slice}`), ducc0's
   outputs and reports (`ducc-synth`, `ducc-slice`), the extracted kernel
   table (`kerneldb/rows.txt`).
2. **K six arms** (`outputs/p2-gridder-20261030-01/inputs-k`, 192 rows ×
   2048 channels, 117 k gridded visibilities per arm, 512² at 8″).
3. **K `original` × 41** (`--tile 41`, 4.8 M gridded): DF1's largest case.
   `np.tile` repeats identical uvw 41 times, so locality gains measured on
   it are optimistic; it is kept for continuity with DF1.
4. **Whole-array synthetic** (`bench_df2.py synth`, seed 2030): the real
   MeerKAT antenna positions (ITRF `POSITION` of
   `outputs/luno-solve-20261029-02/inputs/ANTENNA`, decoded by the core's
   blosc reader), the first 53 stations (1,378 baselines, as the L1 array
   campaign's 53 stations with data), 30 integrations of 8 s on PKS
   1934−638 (declination −63.71°, hour angle −0.5 h start), 640 channels
   evenly over 1070–1498 MHz: 41,340 rows × 640 = 26.5 M cells, about 10 %
   given zero weight at random, so about 23.8 M gridded. Data complex64 (a
   1 Jy source at the phase centre plus Gaussian noise), weights float32
   (0.5–1.5), imaging weights one. Image 1024² at 1.5″ (L1's whole-array
   image). LUNO chunk 0 itself (41,786 rows × 2048 channels, about 100 M
   cells) is not on the host as visibilities and would not fit the
   wrapper's DF1 copies in memory; this case has its row count, layout,
   band and image, with a quarter of its channels, inside the stated
   20–50 M range.

## Baselines (DF1's committed code, before any change)

- **Reference arrays** (`bench_df2.py refs`): with `8c1726f`'s gridder,
  every DF1 gated output (both precisions at the gated ε, both directions,
  every synthetic case and the slice dirty and PSF, exactly the calls of
  `compare_core_wgridder.py hashes`) saved as arrays; their SHA256 must
  equal `threads-final.json` (DF1's archive) before they serve as
  references. Also saved: the K six arms, K × 41 and the whole-array case
  through `fits_image` (dirty and PSF, f64 ε 1e-6, and f32 ε 1e-4 for the
  K arms).
- **Cost** (`bench_df2.py bench`, extending `bench_df1.py`'s harness and
  using its image definition unchanged: one image = dirty + PSF; core
  through `core_wgridder.fits_image`; ducc0 0.42.0 as two `vis2dirty`
  calls with `nthreads` = the thread count and its unit-visibility array):
  fresh process per (implementation, thread count, repeat), threads 1, 4
  and 16, `OMP_NUM_THREADS` unset (it caps ducc0's pool),
  `OPENBLAS_NUM_THREADS=1`, core and ducc0 interleaved in the same time
  window, three repeats (median reported, range beside it), one-minute load
  recorded before and after. Wall per image, process CPU, whole-process
  peak RSS (`ru_maxrss`) and RSS after loading the inputs.

## Optimisations, in order, each measured before the next

For each: what changes, and whether the arithmetic order is preserved.

- **(a) Kernel taps once per visibility, reused across w-planes** (only the
  w-kernel evaluated per plane). Arithmetic preserved (the same Horner
  values, multiplied by the same w factor). Memory budget: storing u and v
  taps costs `2 W sizeof(T)` per visibility (128–256 B in f64, 4–8 GB at
  30 M visibilities), which cannot meet the memory gate below. (a) is
  therefore implemented only in a bounded form (taps cached for a window
  of planes or a block of visibilities, at most a few grid sizes of extra
  memory), measured, and kept only if it is faster within the memory gate;
  otherwise recorded as a negative result.
- **(b) Vectorised kernel evaluation**: coefficients stored degree-major,
  Horner's rule across taps in fixed-size arrays per support (and the grid
  loops on fixed-size arrays). Per tap the same operations in the same
  order as DF1's scalar Horner: bit-identical. ducc0's even/odd split
  (`eval2s`, mirrored taps) or explicit `mul_add` would change tap
  rounding: if adopted, classed as order-changing.
- **(c) Visibilities sorted by grid tile, one grid per plane, planes in
  sequence, parallel within a plane**: DF1 grids w-planes in parallel, one
  full grid per task, which cannot use more threads than planes (K has
  8) and multiplies grid memory by the thread count (300–356 MB against
  ducc0's 117 MB at K, 16 threads). DF2a processes planes in order, each
  plane's visibilities in tiles of the grid, tiles in parallel under a
  fixed colouring so that concurrently processed tiles never write the
  same cells (no locks: lock order is not deterministic), colours and
  tiles in a fixed order; the FFTs and the projection of one plane in
  parallel over rows and columns; plane terms added to the image in plane
  order as before. The tile layout does not depend on the thread count, so
  outputs remain bit-identical at every thread count. The summation order
  within a grid cell changes (tile order instead of DF1's list order):
  order-changing. Degridding reads a finished grid per plane and
  accumulates each visibility's plane contributions in plane order, as
  DF1: its arithmetic is preserved if the taps are.
- **(d) PSF mode**: `fits_image` (and new entry points) grid the dirty
  image and the PSF in one pass over the data: one scan, one bucketing,
  one kernel evaluation per visibility and plane, two grids. Both images
  use the plan of the PSF's active set (`wgt · mask ≠ 0`; ducc0 and DF1
  use `|vis|² · wgt · mask ≠ 0` for the dirty call). The result is
  bit-identical to two separate calls of the same code when the two active
  sets coincide (no visibility with nonzero weight and exactly zero data;
  checked per input and reported); otherwise the dirty image differs from a
  separate call by its plan, and the gates still apply.
- **(e) No wrapper copies**: new entry points read complex64 or complex128
  data and float32 or float64 weights directly (widened inside the core,
  exact, so bit-identical to the wrapper's former casts); the unit
  visibilities of the PSF are not materialised (PSF mode); the products of
  the weights stay in the caller.
- **(f) The 1.7e-10 edge difference from ducc0** (DF1 open item 2). First
  the deciding experiment: per pixel in the border and corner, which of
  the port and ducc0 is closer to the float64 DFT, at ε 1e-5, 1e-7, 1e-9
  (synthetic `wide-0p3rad` and a corner-pixel case). If the port is not
  worse than ducc0 there, the cause is not a port defect: record and stop.
  Otherwise bisect the kernel path against ducc0's (Python-reachable
  pieces, even/odd evaluation, mirrored taps, correction table) and fix
  only a cause in the port. Time-boxed; re-measured after (b).

## Acceptance (gated)

Per optimisation and on the final code:

1. **DF1's gates with DF1's thresholds**, through
   `compare_core_wgridder.py gates` and `threads` unmodified: against the
   DFT ≤ 10 ε, against ducc0 ≤ ε (gated ε f32 1e-4, f64 1e-7), adjointness
   ≤ 1e-12, SHA256 identical at 1, 2, 4, 8 and 16 threads, kernel table
   and `(supp, nu, nv, nplanes)` equal to ducc0's report.
2. **Agreement with DF1's reference arrays** (L∞ / max|reference| per
   output): bit-identical where the optimisation preserves the arithmetic
   order ((a), (b), (e); degridding under (c)); where the summation order
   legitimately changes ((c) gridding, (d) if its plan differs, any
   even/odd evaluation), ≤ 1e-13 in f64 and ≤ 1e-5 in f32 (the f32
   accumulation level between DF1 and ducc0). Thread identity of PSF mode
   and of the new entry points: SHA256 equal at 1 and 16 threads on the K
   arms, K × 41 and the whole-array case.
3. **Speed** (f64, ε 1e-6, per image, medians of three repeats): on K × 41
   and the whole-array case, wall per image within 1.5× of ducc0's on one
   thread and within 2× at 16 threads; at 4 threads reported. The K six
   arms (117 k visibilities, FFT-dominated) are reported against the same
   factors, not gated. PSF mode adds no second pass over the data (by
   construction; its cost against two calls is reported). f32 ε 1e-4
   reported.
4. **Memory**: whole-process peak RSS in the same harness at 1, 4 and 16
   threads, on each input set, at most 1.2 × ducc0's. The harness is DF1's
   (ducc0's path allocates its complex128 casts and unit-visibility array,
   which counts against ducc0); the RSS increase over the loaded inputs is
   reported beside it for both.

Failures are recorded as frozen; anything decided after this commit is
labelled post hoc.
