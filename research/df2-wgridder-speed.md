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

**Status now: implemented and measured** ([Measured results](#measured-results-2026-10-30-post-freeze-runs-as-frozen)).
Per image (dirty + PSF, f64, ε 1e-6) the exact gridder is within
1.06–1.07× of ducc0 0.42 on the 23.8 M-visibility whole-array case at 1
and 16 threads (DF1: 3.6× and 6.9×) and 1.13× / 1.37× on K × 41 at 1 /
16 threads (clean repeat; the frozen run 1, taken while sibling jobs
halved ducc0's own speed, gave 1.39× / 0.80×), with the same or less
memory (1.01–1.07× ducc0's peak on the array case, 0.68× on K × 41);
outputs bit-identical at 1–16 threads and at every SIMD level. The gated
speed and memory criteria pass (array case and K × 41); DF1's five gates
pass with their thresholds. **Not gated: the four-station K arms (117 k
visibilities each) stay at 1.46× ducc0 on one thread and 2.27× at 16
threads** (fixed per-plane overhead; open item 1), outside the 2× figure
at 16 threads. Criterion 2's agreement bound with DF1's outputs (1e-13 in
f64, 1e-5 in f32) fails as frozen on the 0.3 rad cases (1.1e-10), the
slice (6e-12) and the f32 K images (3.9e-5). Same mechanism as the edge
difference from ducc0: permuting the input rows alone moves `wide-0p3rad`
by 1.7e-11 at the border; DF2a changes every rounding stage (tile sums,
FMA, even/odd taps) and moves it by 1.0e-10, which divided by the
correction factor is as large at the border as inside (1.8e-14 both).
The f32 images are now closer to the f64 ones than DF1's. The 1.7e-10
edge difference from ducc0 (DF1 open item 2) is rounding amplified by the
correction function (up to 3 × 10⁵ in the corners of a 0.3 rad field),
not a port defect.

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

## What was built (post-freeze, branch `df2-wgridder-speed`)

Commits after the protocol (`aec10bb`) and the harness (`347d5e9`):

- `7d7d8d1` (c)+(b): planes in sequence; the visibilities sorted once by
  (grid tile, first plane, row, channel) with a counting sort over fixed row
  chunks; each plane gridded tile by tile into per-task tile buffers (real
  and imaginary parts apart, as ducc0), tasks of at most 2,048 visibilities
  (fixed, so heavy tiles split the same way at any thread count), the tasks
  of one parity class of tiles in parallel and their buffers added to the
  grid in task order; wrapping tiles (tile coordinates are shifted by half
  the grid so that the wrap seam lies at the longest baselines, not at
  u = 0) last and in order; v transforms of the touched rows and u
  transforms of the image columns in parallel; the loops monomorphised on
  the support (4..16) with Horner's rule across taps; degridding by the
  same tasks reading a finished grid, each visibility's plane terms added in
  plane order.
- `7d73dc0` (b), (d), (e): fused multiply-add in the kernel evaluation,
  the accumulation and the degridding sums, with the hot loops compiled
  for AVX-512 and for AVX2 and chosen at run time (`RANG_WGRIDDER_SIMD`
  caps the level); the PSF in the same pass (`vis2dirty_multi`,
  `dirty_psf`): one scan, one sort, one kernel evaluation per visibility
  and plane, two grids; the unit value `phase * weight` stored per
  visibility (16 B) and the data value `vis * (phase * weight)` formed per
  plane; new additive entry points `rang_core_wgridder_vis2dirty_ex_{f64,f32}`
  and `rang_core_wgridder_dirty2vis_ex_{f64,f32}` reading complex64 or
  complex128 data and float32 or float64 weights in place;
  `core_wgridder` passes NumPy buffers without copies and `fits_image`
  uses one pass.
- `d485fed` (b): ducc0's even/odd kernel evaluation (`TemplateKernel`):
  `p(x) = Pe(x^2) + x Po(x^2)`, the first `ceil(W/2)` taps evaluated and the
  others mirrored.
- `3cc4123` (a) bounded: optional plane groups (`RANG_WGRIDDER_PLANE_GROUP`,
  default one): the u and v taps evaluated once per visibility for a group
  of planes held in memory; the products are the same as per plane, so the
  result does not depend on the group size. Per-pixel tables in parallel;
  only the written rows are zeroed between planes.
- `af320fc`: the edge experiment (`bench_df2.py edge`), tests, clippy.

Order of work (post hoc, labelled): the protocol listed (a), (b), (c);
after measuring the 16-thread and memory limits of DF1's planes-in-parallel
structure (advisor review, before code), (c)'s structure was built first,
since (a) and (b) plug into it; its loops were monomorphised from the
start, which the protocol had listed under (b). FMA, the AVX-512/AVX2
dispatch and the even/odd evaluation were added under (b) after the
per-phase measurements below; all three change tap rounding (order-changing
class of the protocol).

## Measured results (2026-10-30, post-freeze runs as frozen)

Run directories: `outputs/df2-20261030-01` (reference arrays, DF1
baselines, per-step measurements, gates per step, the edge experiment,
the plane-group experiment, the f32 probe) and `outputs/df2-20261030-02`
(final benchmarks, final gates and comparisons). Compact result:
`research/results/df2-wgridder-speed.json`. Host: WSL2, Ryzen 7 7700X
(8 cores, 16 threads, AVX-512), 30 GiB; one-minute load 1–8 from sibling
tasks throughout (recorded per run).

### Reference arrays (DF1's committed code)

`bench_df2.py refs` (`ref/`, 55 arrays): the 20 gated outputs hash-equal
DF1's `threads-final.json` (no mismatch, none missing), plus `fits_image`
on the K arms (f64 ε 1e-6 and f32 ε 1e-4), K × 41 and the array case. No
input has a visibility with nonzero weight and zero data, so the PSF
mode's plan equals the separate calls' on every benchmark input.

The whole-array case: 41,340 rows × 640 channels, 23,811,985 gridded.

### Baselines: DF1's committed code against ducc0 (`bench-df1-*`)

Per image (dirty + PSF), f64 ε 1e-6, median of three interleaved repeats
(range of the per-repeat totals in the archive), whole-process peak RSS;
load 1.7–6.4.

| Input (visibilities per image) | Threads | DF1 | ducc0 0.42 | DF1 / ducc0 | RSS DF1 / ducc0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| K six arms (117 k each) | 1 | 0.301 s | 0.086 s | 3.50 | 122 / 121 MB |
| | 4 | 0.114 s | 0.036 s | 3.17 | 174 / 122 MB |
| | 16 | 0.100 s | 0.041 s | 2.46 | 318 / 129 MB |
| K × 41 (4.82 M) | 1 | 6.90 s | 1.79 s | 3.85 | 1221 / 771 MB |
| | 4 | 2.93 s | 0.57 s | 5.12 | 1291 / 756 MB |
| | 16 | 2.15 s | 0.32 s | 6.68 | 1250 / 775 MB |
| whole-array synthetic (23.8 M) | 1 | 36.1 s | 10.1 s | 3.59 | 3549 / 1355 MB |
| | 4 | 15.5 s | 3.0 s | 5.16 | 3599 / 1356 MB |
| | 16 | 10.96 s | 1.60 s | 6.85 | 3639 / 1364 MB |

The array case: grid 2376², support 7, 7 w-planes (K × 41: 1188², 7, 7;
one K arm: 900², 8, 8).

### Per step (`quick-*`, core only, one repeat, labelled)

Wall of the whole set (K: six images; K × 41 and array: one image), peak
RSS, one-minute load at the start. Loads differ between rows (1–8), so
neighbouring rows compare only roughly; the final table is interleaved
with ducc0.

| Step | K, 1 / 16 threads | K × 41, 1 / 4 / 16 | array, 1 / 4 / 16 | array RSS | load |
| --- | --- | --- | --- | ---: | ---: |
| DF1 (baseline medians) | 1.81 / 0.60 s | 6.90 / 2.93 / 2.15 s | 36.1 / 15.5 / 11.0 s | 3549 MB | 1.7–6 |
| (c) planes in sequence, tiles, scalar taps | 1.83 / 1.69 | 6.58 / 6.46 / 6.33 | 35.1 / 11.1 / 7.7 | 1948 | 0.9 |
| (c) + fixed-size chunks (heavy tiles split) | 2.06 / 0.80 | 8.05 / 2.82 / 1.67 | 39.0 / 13.1 / 6.6 | 1948 | 5–8 |
| (b) Horner across taps | 1.55 / 0.66 | 5.16 / 1.62 / 1.02 | 25.7 / 7.5 / 4.1 | 1948 | 6–7 |
| (b) real and imaginary loops apart (vectorised) | 1.24 / 0.59 | 4.87 / 1.49 / 0.89 | 21.6 / 6.8 / 3.1 | 1948 | 1.7–3 |
| (b) FMA, AVX-512 / AVX2 dispatch | 1.15 / 0.60 | 4.34 / 1.73 / 1.20 | 19.8 / 6.1 / 3.8 | 1948 | 5–6 |
| (d)+(e) PSF in one pass, inputs in place | 0.90 / 0.58 | 2.47 / 0.77 / 0.50 | 12.2 / 3.8 / 2.1 | 1812 | 3–4 |
| (d) unit values stored, data values per plane | 0.90 / 0.74 | 2.49 / 0.79 / 0.57 | 11.9 / 3.5 / 1.9 | 1358 | 4 |
| (b) even/odd evaluation, mirrored taps | 1.03 / 0.65 | 2.36 / 0.81 / 0.54 | 10.5 / 3.4 / 2.0 | 1358 | 6 |

Phase timing (`RANG_WGRIDDER_TIMING`, one `vis2dirty` on the array case,
one thread): at (c) the gridding loop took 14.0 s of 15.4 s (FFTs 0.2 s,
sort 0.65 s, values 0.44 s); at the end 8.2 s of 10.3 s for dirty and PSF
together (FFTs 0.5 s, sort 0.9 s, values 0.4 s). Scratch experiments on K
× 41 (labelled, copies of the code built outside the tree): the gridding
loop split into kernel evaluation (~0.9 s) and accumulation (~1.3 s) of
2.3 s, the per-visibility bookkeeping 0.16 s; the accumulation was not
vectorised (the real and imaginary buffers updated in one loop, so the
compiler kept scalar code: found in the assembly), hence the split loops;
FMA alone −8 to −16 %, AVX-512 alone −10 %, both −20 %; even/odd
evaluation −24 % of the loop.

### Final (`outputs/df2-20261030-02`, code `af320fc`)

Per image, f64 ε 1e-6, three interleaved repeats, medians. Run 1 is the
frozen measurement; K and K × 41 were rerun once more three minutes later
(labelled repeat), because sibling jobs had loaded the host during run 1
(ducc0 itself ran at half its baseline speed on K × 41 then).

| Input | Threads | core | ducc0 | core / ducc0 | target | RSS core / ducc0 (≤ 1.2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| whole-array (23.8 M) | 1 | 11.35 s | 10.68 s | **1.06** | ≤ 1.5 pass | 1358 / 1349 MB (1.01) |
| | 4 | 3.54 s | 3.27 s | 1.08 | – | 1377 / 1351 MB (1.02) |
| | 16 | 1.93 s | 1.81 s | **1.07** | ≤ 2 pass | 1459 / 1359 MB (1.07) |
| K × 41 (4.82 M), run 1 | 1 | 4.87 s | 3.51 s | **1.39** | ≤ 1.5 pass | 524 / 766 MB (0.68) |
| | 4 | 1.41 s | 1.53 s | 0.92 | – | 527 / 767 MB |
| | 16 | 1.07 s | 1.34 s | **0.80** | ≤ 2 pass | 533 / 769 MB |
| K × 41, repeat (labelled) | 1 | 2.18 s | 1.94 s | 1.13 | ≤ 1.5 pass | 524 / 750 MB |
| | 4 | 0.73 s | 0.63 s | 1.16 | – | 526 / 751 MB |
| | 16 | 0.52 s | 0.38 s | 1.37 | ≤ 2 pass | 528 / 770 MB |
| K six arms (reported), run 1 | 1 / 4 / 16 | 0.280 / 0.126 / 0.188 s | 0.186 / 0.096 / 0.102 s | 1.51 / 1.32 / 1.85 | not gated | 118–121 / 116–121 MB |
| K six arms, repeat | 1 / 4 / 16 | 0.143 / 0.065 / 0.097 s | 0.098 / 0.039 / 0.043 s | 1.46 / 1.65 / 2.27 | not gated | 118–121 / 116–124 MB |
| K six arms, f32 ε 1e-4 | 1 / 4 / 16 | 0.082 / 0.046 / 0.067 s | 0.063 / 0.026 / 0.038 s | 1.30 / 1.82 / 1.74 | reported | 103 / 100–102 MB |

Per visibility on the array case: 477 / 149 / 81 ns per image at 1 / 4 /
16 threads against ducc0's 448 / 137 / 76 ns (DF1: 1517 / 651 / 460 ns).
RSS over the loaded inputs: core 508–609 MB, ducc0 499–508 MB (the core
keeps 24 B per gridded visibility: row and channel, and the unit value;
ducc0's harness holds its complex128 casts and unit visibilities). The
K arms (117 k visibilities, 900² grids, 8 planes) remain 1.3–2.3× ducc0:
fixed per-plane costs (thread-pool rounds per tile class, FFT planning,
first-touch of two grids) dominate there (open item).

**Speed gates: pass** (array and K × 41, both runs). **Memory gate: pass**
(every set and thread count, 0.68–1.07× ducc0). **PSF mode: no second
pass** over the data by construction (one scan, one sort, one kernel
evaluation per visibility and plane for both images); against two calls
of the same code it saved 38–58 % of the wall on K × 41 and the array case
(rows "(b) FMA" → "(d)+(e)", loads 3–6).

Outputs identical across repeats and thread counts in every benchmark
(`hashes_identical_across_runs`: core true, ducc0 false).

### Gates (`gates-final`, `threads-final.json`, as frozen)

| # | Criterion | Result | Worst figure (limit) |
| --- | --- | --- | --- |
| 1 | Against the DFT, ≤ 10 ε | **pass** | f32 1e-4: 4.0e-5 (1e-3); f64 1e-7: 4.1e-8 (1e-6) |
| 2 | Against ducc0, ≤ ε | **pass** | f32 1e-4: 1.4e-5 (1e-4), slice PSF; f64 1e-7: 1.5e-10 (1e-7), `wide-0p3rad` |
| 3 | Adjointness ≤ 1e-12 | **pass** | 5.7e-13 (`wide-0p3rad-rect`) |
| 4 | SHA256 at 1, 2, 4, 8, 16 threads | **pass**, 20 outputs identical | – |
| 5 | Kernel table and choice | **pass**: table equal, `(supp, nu, nv, nplanes)` equal to ducc0's in all runs | – |

Single visibilities at 40 sub-cell offsets: 1.8e-12 (w = 0) and 1.9e-12
(w ≠ 0) of ducc0's peak. The gates passed at every step where they were run
(`gates-b-split`, `gates-de`, `gates-eo`, `gates-final`), and thread
identity likewise. SIMD levels: DF1's 20 gated outputs hash-equal under
`RANG_WGRIDDER_SIMD` = `avx512`, `avx2` and `baseline` (`simd-*`). PSF mode
against two separate calls: bit-identical on the K arms, K × 41 and the
array case (post-hoc check script, and `test_psf_mode_and_borrowed_inputs_match_separate_calls`);
borrowed complex64 / float32 inputs equal their casts bit for bit; plane
groups G = 1, 2, 4, 8 give identical outputs.

### Agreement with DF1's outputs (criterion 2 of this protocol): fails as frozen

`compare-final.json` (L∞ over the reference peak):

- **Gridding, f64**: K arms 2–6e-14, K × 41 1.1e-13 (dirty) / 8.1e-14
  (PSF), array 1.0e-15, `small-8arcmin` 5.7e-16, `mid-2deg` 3.9e-14 — but
  the slice 6.2e-12 and the 0.3 rad cases 1.0–1.1e-10, above the frozen
  1e-13. **Fail.**
- **Gridding, f32**: synthetic cases ≤ 2.1e-7, slice 1.2e-5, K arms
  3.3–3.9e-5, above the frozen 1e-5. **Fail.**
- **Degridding**: bit-identical to DF1 on all eight outputs through
  `7d7d8d1` (tiles, chunks, vectorised Horner: arithmetic preserved as
  the protocol predicted); after FMA and the even/odd evaluation, f64 ≤
  5.4e-14 and f32 ≤ 2.5e-7 (pass).

Why the bound fails (measured, post hoc): the frozen 1e-13 assumed that a
legitimate reordering of the sums moves an image by a few ulp of its peak.
On these images it does not: permuting only the input rows of the port
(same code, `edge.json`) moves `wide-0p3rad` by 1.7e-11 at the border, and
DF1 itself differs from ducc0 by 1.7e-10. DF2a against DF1 (1.0e-10 and
1.1e-10 at the border, 1e-13 and 2e-14 inside) is the same mechanism with
more changed stages (tile partial sums, FMA, even/odd taps): divided by the
correction factor (3.1e5 and 1.9e5 at the border) the difference is
1.8e-14 at the border against 1.8e-14 inside on `wide-0p3rad`, and 5.2e-15
against 4.3e-14 on `wide-0p3rad-rect` (`outputs/df2-20261030-02/df2-vs-df1-correction.json`,
post-hoc probe): no excess at the edge once the amplification is removed.
The slice (7,377 visibilities of
four stations, sky-wide sidelobes) carries 1e-12 relative cancellation
noise in its interior as well (DF1 against ducc0: 1.3e-12 eight pixels
in). The f32 differences are DF1's own accumulation error: against the
f64 image of the same input, DF2a's f32 images are off by 2.2e-5 of the
peak and DF1's by 3.9–4.4e-5 (`f32-probe.json`, below). No bit-identity
was claimed for gridding; the arithmetic-preserving steps (degridding
through `7d7d8d1`) were bit-identical as predicted.

### (a) Kernel taps reused across planes (bounded form): kept as an option, off

Plane groups of G planes (`a-groups/`, one image per run, load 3.6–4.7;
all outputs identical for every G):

| Input, threads | G = 1 | G = 2 | G = 4 | G = 8 |
| --- | --- | --- | --- | --- |
| K six arms, 1 | 0.88 s, 117 MB | 0.90 s, 144 MB | 1.00 s, 192 MB | 1.30 s, 295 MB |
| K six arms, 16 | 0.58 s, 119 MB | 0.61 s, 144 MB | 0.73 s, 194 MB | 1.01 s, 297 MB |
| K × 41, 1 | 2.16 s, 523 MB | 1.93 s, 583 MB | 1.93 s, 700 MB | 2.01 s, 879 MB |
| K × 41, 16 | 0.47 s, 526 MB | 0.45 s, 586 MB | 0.53 s, 705 MB | 0.52 s, 882 MB |
| array, 1 | 10.57 s, 1358 MB | 9.88 s, 1577 MB | 9.67 s, 2016 MB | 9.21 s, 2674 MB |
| array, 16 | 1.82 s, 1454 MB | 1.69 s, 1642 MB | 1.79 s, 2046 MB | 2.10 s, 2697 MB |

Once the kernel is evaluated by vectorised even/odd Horner, it is no
longer the dominant cost: reusing the u and v taps saves at most 6–13 %
on one thread, nothing at 16 threads, costs time on the FFT-dominated K
arms, and each extra plane costs one grid per output (220 MB on the array
case at G = 2, which then exceeds the memory gate at 16 threads). Recorded
as a negative result: the default stays G = 1 (per plane, as ducc0);
`RANG_WGRIDDER_PLANE_GROUP` remains for memory-rich runs. Storing the taps
per visibility (the unbounded form) was not built: 128 B per visibility in
f64 at W = 8 (3 GB on the array case).

### (f) The edge-pixel difference from ducc0: rounding amplified by the correction, not a port defect

`bench_df2.py edge` (`edge.json`, f64, the two 0.3 rad cases, ε 1e-5 to
1e-11): the port and ducc0 0.42 (nthreads 1) against the float64 DFT, against
each other, and each against itself with the input rows permuted (same
code, only the summation order changed); border = outer two pixels,
interior = eight pixels in; L∞ over the DFT peak.

| `wide-0p3rad`, ε | port − DFT, border | ducc0 − DFT, border | port − ducc0, border / interior | port − port permuted, border | ducc0 − ducc0 permuted, border | max correction factor, border | (port − ducc0) / correction, border / interior |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1e-5 | 2.0e-7 | 2.0e-7 | 4.6e-11 / 6.6e-13 | 9.3e-13 | 9.4e-13 | 1.2e5 | 1.7e-14 / 7.8e-13 |
| 1e-7 | 1.2e-9 | 1.2e-9 | 1.5e-10 / 7.6e-13 | 1.7e-11 | 9.8e-12 | 3.1e5 | 1.5e-14 / 9.7e-13 |
| 1e-9 | 6.1e-12 | 5.9e-12 | 1.2e-12 / 2.1e-13 | 1.1e-13 | 6.0e-14 | 1.8e4 | 7.3e-15 / 2.1e-13 |
| 1e-11 | 6.0e-14 | 6.7e-14 | 2.6e-14 / 3.0e-14 | 4.9e-16 | 6.6e-16 | 4.6e2 | 6.2e-15 / 3.5e-14 |

(`wide-0p3rad-rect` alike: port − ducc0 at the border 2.9e-11, 4.1e-11,
1.7e-12, 1.6e-14.)

- The port is not worse than ducc0 at the edge: both are equally far from
  the DFT there (1.2e-9 each at ε 1e-7), and the port is the closer of the
  two in 42–55 % of the border pixels.
- The difference follows the correction factor (the product of the u, v
  and w correction functions, 3.1e5 in the corner at ε 1e-7), not ε:
  divided by the correction it is no larger at the border than inside
  (1.5e-14 against 9.7e-13 of the peak), and the non-monotonic ε pattern
  DF1 reported (2.8e-9, 8.9e-9, 1.1e-10, 5.8e-13 at the corner for ε 1e-5 …
  1e-11) is the pattern of the correction factor (1.2e5, 3.1e5, 1.8e4,
  4.6e2), which depends on each ε's kernel (support, oversampling) — about
  2–5 × 10⁻¹⁶ of the correction factor, i.e. rounding.
- Each code differs from itself by 1e-11 at the border at ε 1e-7 when only
  the order of the input rows changes; the port and ducc0 differ in every
  floating-point stage (FFT, w-screen phases, kernel evaluation, grid
  summation order), so their difference is about ten times that.
- DF2a's own changes move the border by the same amount: against DF1's
  outputs 1.0e-10 on `wide-0p3rad` (L∞ over the peak, outer pixels), and
  the port − ducc0 border figure stayed at 1.2–1.5e-10 through every step
  (scalar, FMA, even/odd evaluation), while the gate figure moved from
  DF1's 1.73e-10 to 1.38e-10 (tile buffers), 1.25e-10 (FMA) and 1.50e-10
  (even/odd).

Nothing to fix. The open item is closed: the 0.09 ε corner difference is
float rounding amplified by up to 3 × 10⁵ in the corners of a 0.3 rad field.

### f32 accuracy (post-hoc probe)

DF2a's f32 images differ from DF1's by up to 3.9e-5 of the peak on the K
arms (criterion 2's 1e-5 fails as frozen). Against the f64 image of the
same input (ε 1e-6) the DF2a f32 images are the more accurate ones:
2.2e-5 of the peak on every arm against DF1's 3.9–4.4e-5
(`f32-probe.json`): the tile buffers sum fewer terms per partial sum than
DF1's single accumulation per grid cell.

## For the coordinator

**STATE paragraph.** DF2a (exact gridder speed, `research/df2-wgridder-speed.md`,
branch `df2-wgridder-speed`): DF1's Rust port of ducc0's wgridder now runs
at ducc0's speed. Planes are gridded in sequence, the grid in tiles under a
fixed parity colouring with fixed-size tasks (deterministic, no locks),
the kernel evaluated by ducc0's even/odd Horner scheme with FMA, the loops
monomorphised on the support and compiled for AVX-512 and AVX2 (chosen at
run time), the dirty image and PSF in one pass, data and weights read in
place (new `_ex` entry points). Per image (f64, ε 1e-6) 1.06–1.07× ducc0
0.42 on a 23.8 M-visibility whole-array case at 1 and 16 threads (DF1 3.6×
and 6.9×), 1.13× / 1.37× on K × 41 at 1 / 16 threads (clean repeat;
frozen run 1 under sibling load 1.39× / 0.80×), memory 0.68–1.07× ducc0's
peak; outputs bit-identical at 1–16 threads and at every SIMD level; all of
DF1's gates pass. Not gated: the four-station K arms (117 k visibilities)
stay at 1.46× ducc0 on one thread and 2.27× at 16 threads (fixed
per-plane overhead), the first images DF2b wires in. The frozen agreement
bound with DF1's outputs (1e-13) failed on wide-field and f32 images: the
same rounding amplification as below (row order alone moves the border by
1.7e-11; DF2a, changing every rounding stage, by 1.0e-10, flat inside and
out once divided by the correction). DF1's open edge difference from ducc0
(1.7e-10) is rounding amplified by the correction function (up to 3 × 10⁵
in a 0.3 rad field's corners): the port and ducc0 are equally close to
the DFT there. Plane groups (u/v taps reused across planes) gained ≤ 13 %
at up to 2.7× the memory: off by default.

**Timing rows for `research/tool-timings.md`:** the table under "Tool runs"
below (all 2026-10-30).

**`ffi_wgridder` additions needing extension bindings (optional).** Four
new C entry points, additive (DF1's six unchanged):
`rang_core_wgridder_vis2dirty_ex_{f64,f32}(opts, nrow, nchan, uvw, freq,
vis, vis_kind, wgt, wgt_kind, mask, dirty, psf, info)` (`vis_kind` 0 unit,
1 complex64, 2 complex128; `wgt_kind` 0 none, 1 float32, 2 float64; `dirty`
or `psf` may be null) and `rang_core_wgridder_dirty2vis_ex_{f64,f32}(opts,
nrow, nchan, uvw, freq, dirty, wgt, wgt_kind, mask, vis, info)`; the Rust
API behind them is `wgridder::vis2dirty_multi` and `dirty2vis_multi` with
`VisData` and `Weights` (borrowed slices of either precision). `lib.rs`
already lists both modules, so the core cdylib exports them; `core_wgridder`
still loads its standalone build because the extension module has no
ctypes symbols. A PyO3 binding `wgridder_dirty_psf(uvw, freq, vis, wgt,
mask, options…) -> (dirty, psf, info)` taking NumPy arrays of either dtype
(borrowed, no copies) would let `core_wgridder` drop the standalone build
(one `hasattr(ext, …)` check, as `p5_extension`).

**What DF2b needs (the driver hook `gridder="wgrid"`).**

- Drivers: `core_imaging.image_job` (task I), `core_campaign.image_arm`
  (task K, L1) and `run_core_gridder.py` (task C) call
  `core_grid.invert(uvw, freq, data, weights, imaging_weights, width,
  height, scale, …)`. Add `gridder="wstack"|"wgrid"` (default `wstack`, the
  archive reproducer) and for `wgrid` call
  `core_wgridder.fits_image(uvw, freq, data, weights * imaging_weights,
  width, height, scale, epsilon=1e-6)`: f64, one pass for dirty and PSF,
  data and weights read in place (complex64 and float32 straight from the
  MS reader; the weight product is the one remaining copy, 4 B per cell —
  a two-weight entry point would remove it). Same FITS orientation and
  PSF-centre normalisation as `core_grid.invert`.
- Counters: `info["nvis"]` is the number of gridded visibilities
  (`weights * imaging_weights != 0`); weight sums from NumPy; keep the
  reader-pass counters as DF1 recommended.
- Threads: `RAYON_NUM_THREADS`; results are bit-identical at any thread
  count and SIMD level, so archives stay reproducible across hosts with
  AVX2 or AVX-512.
- Expected cost per image (f64, ε 1e-6) on this host, from the final table:
  K arm ≈ 0.1–0.15 s, the whole-array case (23.8 M visibilities, 1024²)
  ≈ 10 s on one thread and ≈ 1.8 s at 16 threads, ≈ 1.4 GB peak with its
  inputs. LUNO chunk 0 at all 2048 channels (≈ 4× the visibilities) would
  scale to ≈ 40 s / 7 s per image and ≈ 2.5 GB of gridder state (24 B per
  visibility) besides the inputs.
- Re-tolerancing against WSClean 3.7's wgridder (DF0/O-CASA) as DF1
  listed; the exact gridder's images agree with ducc0 to ≤ 1.5e-10 of the
  peak (edge pixels of a 0.3 rad field) and ≤ 1e-12 inside.

**Upstream observations.**

- Non-RATT, ducc0 0.42.0: (1) at the edge of wide fields its images are
  sensitive at 1e-11–1e-10 of the peak to the order of the input rows (the
  correction function multiplies rounding by up to 3 × 10⁵ in a 0.3 rad
  field's corners at ε 1e-7); with `nthreads > 1` its lock order adds the
  same nondeterminism, so bit-for-bit comparisons of wide-field images
  between runs or codes need a tolerance near 1e-9 of the peak, not 1e-13;
  (2) `vis2dirty`'s default `do_wgridding=False` (with the default
  `divide_by_n=True` and the w sign) is a second documented trap: a
  comparison script here forgot it and saw 10–60 % errors (failed run in
  the table). No bug found.
- RATT, caracal-pipeline: none.

**Evidence to keep:** `outputs/df2-20261030-01` (reference arrays `ref/`
from DF1's code, DF1 baselines `bench-df1-*`, per-step measurements
`quick-*`, gates and thread hashes per step, `edge.json`,
`f32-probe.json`, `a-groups/`, logs) and `outputs/df2-20261030-02` (final
benchmarks and the labelled repeat, `gates-final`, `threads-final.json`,
`compare-final.json`, `simd-final`, logs), each with `SHA256SUMS` (77 MB, 347 files; 0.8 MB, 138 files).
Deletable after DF2b: `quick-*/` (summarised in the result file).

**Deleted scratch:** `~/Build/tmp/20261030-ducc2` (ducc clone at
`ducc0_0_42_0`, `42ce8ab5`, read-only reference) and
`~/Build/tmp/20261030-df2-scratch` (experiment crates `exp-*`, the DF1
`perf` record, assembly listings, the pre-group source copy).

## Open items

1. K-sized images (≈ 100 k visibilities, 8 planes of 900²): 1.3–2.3× ducc0
   per image, from fixed per-plane costs at 16 threads (five rayon rounds
   per plane for the tile classes, FFT planning per call, first touch of
   two grids). A persistent plan (FFTs and grids reused across calls) or
   fewer, coarser rounds for small inputs would close it; not gated.
2. `layout` (the sort) costs 0.9 s of 10 s on one thread for the array
   case and scales 3× at 16 threads (serial offset table and block
   assembly); a parallel prefix would trim 5–10 %.
3. The weight product `weights * imaging_weights` is the one copy left in
   the drivers' path (4 B per cell); a two-weight entry point would remove
   it (DF2b).
4. Criterion 2's bound needs restating for DF2b's re-tolerancing: for
   wide-field images the noise floor of a legitimate reordering is ~1e-11
   of the peak at the border (`edge.json`), so any bit-level tolerance
   should be set from that floor, not from 1e-13.
5. Extension bindings for the `_ex` entry points (coordinator) so that
   `core_wgridder` stops building its standalone library.

## Tool runs

Host: WSL2, Ryzen 7 7700X (16 threads), 30 GiB; load 1–8 (one-minute)
from sibling tasks. Wall and peak RSS from GNU `time` unless noted.

| Date | Tool | Input | Wall | Max RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `git clone` ducc (GitLab) + checkout | `ducc0_0_42_0` | 3.2 s | – | read-only reference; deleted at the end |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin ducc0==0.42.0` | worktree | 45.2 s | 934 MB | |
| 2026-10-30 | `maturin develop --release --offline` | worktree | 43.4 s | 1.03 GB | |
| 2026-10-30 | `perf record` of DF1 (labelled) | K × 41, one thread | 7.7 s (not wrapped) | – | **inconclusive**: perf could not resolve the cdylib's symbols; replaced by scratch experiments |
| 2026-10-30 | `bench_df2.py refs` (DF1 code) | gate cases, K, K × 41, array | 19.8 s | 3.75 GB | 55 arrays; 20 gated hashes equal DF1's archive |
| 2026-10-30 | `bench_df2.py bench` DF1 baseline | K / K × 41 / array, 1/4/16, 3 repeats | 15.0 / 46.8 / 254.9 s | 0.33 / 1.32 / 3.73 GB | interleaved with ducc0 |
| 2026-10-30 | `cargo build` standalone (first, step c) | `df1-standalone` | 0.2 s | 170 MB | **failed**: 5 errors (closures capturing raw pointers); fixed |
| 2026-10-30 | `cargo build` + `cargo test` standalone (per step, 9 builds) | same | 28–41 s + 36–44 s | 0.90–0.97 GB | 7 passed each time |
| 2026-10-30 | `bench_df2.py compare` (first) | step c | 24.0 s | 2.06 GB | **failed**: summary key error in the script (zero-data counters); fixed |
| 2026-10-30 | probes (scratch scripts, labelled) | edge pixels per border width, PSF identity, K plans | seconds each | – | |
| 2026-10-30 | `bench_df2.py bench` quick (wgrid, 1 repeat) ×8 steps | K / K × 41 / array, 1/4/16 | 2.4–5.5 / 4.3–19.9 / 19.0–61.9 s | ≤ 2.0 GB | table "Per step" |
| 2026-10-30 | scratch experiment crates (labelled) ×10 | K × 41, array, one thread | 40–80 s each | ~0.9 GB | taps/accumulation split, FMA, AVX-512, store forwarding, split loops, even/odd |
| 2026-10-30 | `cargo rustc --emit asm` (scratch, labelled) | experiment crate | ~40 s ×2 | – | accumulation found unvectorised |
| 2026-10-30 | `compare_core_wgridder.py gates` ×4 | all cases | 7.0–7.4 s | 88 MB | pass every time |
| 2026-10-30 | `compare_core_wgridder.py threads` ×4 | 1, 2, 4, 8, 16 | 13.3–20.0 s | 67 MB | identical every time |
| 2026-10-30 | `bench_df2.py compare` ×6 | all reference outputs | 8.4–12.9 s | 1.48–2.06 GB | |
| 2026-10-30 | `compare_core_wgridder.py hashes` per SIMD level ×4 runs | gate cases | 2.1–2.6 s each | 65 MB | identical at every level |
| 2026-10-30 | plane-group experiment (`groups.sh`) | K / K × 41 / array, G 1–8, 1/16 | about 4 min (not wrapped) | ≤ 2.7 GB | table "(a)" |
| 2026-10-30 | `cargo clippy -D warnings` standalone (first) | same | 2.7 s | 361 MB | **failed**: 2 lints (`as_deref_mut` on a reference); fixed, clean |
| 2026-10-30 | pytest `test_core_wgridder.py test_core_grid.py` (first) | 11 tests | 39.2 s | 956 MB | **1 failed**: the new test asked for f32 at ε 1e-7 (no kernel); test fixed |
| 2026-10-30 | pytest same | 11 tests | 0.4 s | 90 MB | pass |
| 2026-10-30 | `bench_df2.py edge` (first) | 2 cases × 4 ε | 5.9 s | 77 MB | **failed**: ducc0 called with its default `do_wgridding=False`; fixed |
| 2026-10-30 | `bench_df2.py edge` | same | 6.8 s | 77 MB | table "(f)" |
| 2026-10-30 | f32 probe (labelled) | K arms | 0.9 s | 110 MB | |
| 2026-10-30 | `bench_df2.py bench` final | K / K × 41 / array / K f32, 3 repeats | 24.0 / 50.2 / 118.1 / 9.0 s | 0.12 / 0.79 / 1.49 / 0.11 GB | load 2–5 |
| 2026-10-30 | `bench_df2.py bench` repeat (labelled) | K / K × 41 | 11.4 / 22.4 s | 0.13 / 0.79 GB | load 3.8–4.1 |
| 2026-10-30 | `bench_df2.py summary` | both runs | < 1 s | – | `research/results/df2-wgridder-speed.json` |
| 2026-10-30 | DF2a against DF1 over the correction (post-hoc probe, scratch script) | 0.3 rad cases, f64 ε 1e-7 | 0.8 s | 57 MB | flat: 1.8e-14 border and inside (`df2-vs-df1-correction.json`) |
